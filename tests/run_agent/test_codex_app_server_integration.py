"""Integration test for the codex_app_server runtime path through AIAgent.

Verifies that:
  - api_mode='codex_app_server' is accepted on AIAgent construction
  - run_conversation() takes the early-return path and never enters the
    chat completions loop
  - Projected messages from a fake Codex session land in the messages list
  - tool_iterations from the codex session tick the skill nudge counter
  - Memory nudge counter ticks once per turn
  - The returned dict has the same shape as the chat_completions path
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import run_agent
from agent.codex_runtime import (
    _build_codex_recovery_context,
    _codex_app_server_launch_args,
    _load_codex_thread_id,
    _persist_codex_thread_id,
    make_codex_app_server_event_bridge,
    run_codex_app_server_turn,
)
from agent.transports.codex_app_server import CodexAppServerError
from agent.transports.codex_app_server_session import CodexAppServerSession, TurnResult
from hermes_cli.codex_models import get_codex_model_ids


@pytest.fixture
def fake_session(monkeypatch):
    """Replace CodexAppServerSession with a stub that returns a fixed
    TurnResult, so we can drive AIAgent without spawning real codex."""

    def fake_run_turn(self, user_input: str, **kwargs):
        return TurnResult(
            final_text=f"echo: {user_input}",
            projected_messages=[
                {"role": "assistant", "content": None,
                 "tool_calls": [{"id": "exec_1", "type": "function",
                                 "function": {"name": "exec_command",
                                              "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "exec_1", "content": "ok"},
                {"role": "assistant", "content": f"echo: {user_input}"},
            ],
            tool_iterations=1,
            interrupted=False,
            error=None,
            turn_id="turn-stub-1",
            thread_id="thread-stub-1",
        )

    monkeypatch.setattr(CodexAppServerSession, "run_turn", fake_run_turn)
    monkeypatch.setattr(
        CodexAppServerSession, "ensure_started", lambda self: "thread-stub-1"
    )


def _make_codex_agent(**kwargs):
    """Construct an AIAgent in codex_app_server mode without contacting any
    real provider. We pass api_mode explicitly so the constructor takes the
    fast path for direct credentials."""
    return run_agent.AIAgent(
        api_key="stub",
        base_url="https://stub.invalid",
        provider="openai",
        api_mode="codex_app_server",
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
        **kwargs,
    )


class TestApiModeAccepted:
    def test_api_mode_is_codex_app_server(self):
        agent = _make_codex_agent()
        assert agent.api_mode == "codex_app_server"


class TestRunConversationCodexPath:
    def test_run_conversation_returns_codex_shape(self, fake_session):
        agent = _make_codex_agent()
        # No background review fork during tests
        with patch.object(agent, "_spawn_background_review", return_value=None):
            result = agent.run_conversation("hello there")
        assert result["final_response"] == "echo: hello there"
        assert result["completed"] is True
        assert result["partial"] is False
        assert result["error"] is None
        assert result["api_calls"] == 1
        assert result["codex_thread_id"] == "thread-stub-1"
        assert result["codex_turn_id"] == "turn-stub-1"

    def test_codex_app_server_token_usage_updates_session_accounting(self, monkeypatch):
        def fake_run_turn(self, user_input: str, **kwargs):
            return TurnResult(
                final_text="done",
                projected_messages=[{"role": "assistant", "content": "done"}],
                turn_id="turn-usage-1",
                thread_id="thread-usage-1",
                token_usage_last={
                    "totalTokens": 130,
                    "inputTokens": 100,
                    "cachedInputTokens": 20,
                    "outputTokens": 30,
                    "reasoningOutputTokens": 5,
                },
                model_context_window=200000,
            )

        monkeypatch.setattr(CodexAppServerSession, "run_turn", fake_run_turn)
        monkeypatch.setattr(
            CodexAppServerSession, "ensure_started", lambda self: "thread-usage-1"
        )
        agent = _make_codex_agent()
        with patch.object(agent, "_spawn_background_review", return_value=None):
            result = agent.run_conversation("hello")

        assert result["api_calls"] == 1
        assert result["prompt_tokens"] == 100
        assert result["completion_tokens"] == 30
        assert result["total_tokens"] == 130
        assert result["input_tokens"] == 80
        assert result["output_tokens"] == 30
        assert result["cache_read_tokens"] == 20
        assert result["cache_write_tokens"] == 0
        assert result["reasoning_tokens"] == 5
        assert result["last_prompt_tokens"] == 100

        assert agent.session_api_calls == 1
        assert agent.session_prompt_tokens == 100
        assert agent.session_completion_tokens == 30
        assert agent.session_total_tokens == 130
        assert agent.session_input_tokens == 80
        assert agent.session_output_tokens == 30
        assert agent.session_cache_read_tokens == 20
        assert agent.session_cache_write_tokens == 0
        assert agent.session_reasoning_tokens == 5
        assert agent.context_compressor.last_prompt_tokens == 100
        assert agent.context_compressor.last_completion_tokens == 30
        assert agent.context_compressor.last_total_tokens == 130
        assert agent.context_compressor.context_length == 200000

    def test_native_codex_compaction_updates_bookkeeping(self, monkeypatch):
        def fake_run_turn(self, user_input: str, **kwargs):
            return TurnResult(
                final_text="done",
                projected_messages=[{"role": "assistant", "content": "done"}],
                turn_id="turn-compact-1",
                thread_id="thread-compact-1",
                compacted=True,
                token_usage_last={
                    "totalTokens": 300_000,
                    "inputTokens": 300_000,
                    "cachedInputTokens": 0,
                    "outputTokens": 0,
                    "reasoningOutputTokens": 0,
                },
            )

        monkeypatch.setattr(CodexAppServerSession, "run_turn", fake_run_turn)
        monkeypatch.setattr(
            CodexAppServerSession, "ensure_started", lambda self: "thread-compact-1"
        )
        events = []
        agent = _make_codex_agent(event_callback=lambda name, payload: events.append((name, payload)))

        with patch.object(agent, "_spawn_background_review", return_value=None):
            result = agent.run_conversation("hello")

        assert result["completed"] is True
        assert agent.context_compressor.compression_count == 1
        # A compacted turn with real usage is judged against that same real
        # prompt count, exactly like a normal completed compression boundary.
        assert agent.context_compressor.last_prompt_tokens == 300_000
        assert agent.context_compressor.awaiting_real_usage_after_compression is False
        assert agent.context_compressor._ineffective_compression_count == 1
        assert events == [
            (
                "session:compress",
                {
                    "platform": "",
                    "session_id": agent.session_id,
                    "old_session_id": "",
                    "in_place": False,
                    "compression_count": 1,
                    "runtime": "codex_app_server",
                    "thread_id": "thread-compact-1",
                    "turn_id": "turn-compact-1",
                },
            )
        ]

    def test_projected_messages_are_spliced(self, fake_session):
        agent = _make_codex_agent()
        with patch.object(agent, "_spawn_background_review", return_value=None):
            result = agent.run_conversation("hello")
        msgs = result["messages"]
        # User message + 3 projected (assistant tool_call + tool + assistant text)
        assert len(msgs) >= 4
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"
        # Last assistant message has the final text
        final = [m for m in msgs if m.get("role") == "assistant"
                 and m.get("content") == "echo: hello"]
        assert final, f"expected final assistant message in {msgs}"

    def test_projected_messages_are_synced_to_external_memory(self, fake_session):
        agent = _make_codex_agent()
        agent._memory_manager = MagicMock()
        agent._memory_manager.build_system_prompt.return_value = ""

        with patch.object(agent, "_spawn_background_review", return_value=None):
            result = agent.run_conversation("hello")

        agent._memory_manager.sync_all.assert_called_once()
        assert agent._memory_manager.sync_all.call_args.kwargs["messages"] == result["messages"]

    def test_nudge_counters_tick(self, fake_session):
        """The skill nudge counter must accumulate tool_iterations across
        turns. The memory nudge counter is gated on memory being configured
        (which we skip via skip_memory=True), so we don't assert on it here —
        a separate test below covers that path explicitly."""
        agent = _make_codex_agent()
        agent._iters_since_skill = 0
        agent._user_turn_count = 0
        with patch.object(agent, "_spawn_background_review", return_value=None):
            agent.run_conversation("first")
        assert agent._iters_since_skill == 1  # one tool_iteration in fake turn
        # _user_turn_count is incremented by run_conversation pre-loop, not
        # by the codex helper — confirms we delegate that to the standard flow.
        assert agent._user_turn_count == 1
        with patch.object(agent, "_spawn_background_review", return_value=None):
            agent.run_conversation("second")
        assert agent._iters_since_skill == 2
        assert agent._user_turn_count == 2

    def test_user_message_not_duplicated(self, fake_session):
        """Regression guard: the user message must appear exactly once in
        the messages list. The standard run_conversation pre-loop appends
        it, and the codex helper must NOT append again."""
        agent = _make_codex_agent()
        with patch.object(agent, "_spawn_background_review", return_value=None):
            result = agent.run_conversation("ping unique 12345")
        user_count = sum(
            1 for m in result["messages"]
            if m.get("role") == "user" and m.get("content") == "ping unique 12345"
        )
        assert user_count == 1, f"user message appeared {user_count}× in {result['messages']}"

    def test_background_review_NOT_invoked_below_threshold(self, fake_session):
        """A single turn shouldn't trigger background review — counters
        haven't reached the nudge interval (default 10)."""
        agent = _make_codex_agent()
        agent._memory_nudge_interval = 10
        agent._skill_nudge_interval = 10
        agent._iters_since_skill = 0
        with patch.object(agent, "_spawn_background_review",
                          return_value=None) as spawn:
            agent.run_conversation("ping")
        # Below threshold → review should NOT fire (was a real bug:
        # the helper was calling _spawn_background_review() with no
        # args after every turn, which would crash with TypeError).
        assert not spawn.called

    def test_background_review_skill_trigger_fires_above_threshold(
        self, monkeypatch
    ):
        """When tool iterations cross the skill nudge interval, the
        background review fires with review_skills=True and the right
        messages_snapshot signature."""
        from agent.transports.codex_app_server_session import (
            CodexAppServerSession, TurnResult,
        )
        # Make the fake session report 10 tool iterations in one turn
        # (matching the default skill threshold).
        def fake_run_turn(self, user_input: str, **kwargs):
            return TurnResult(
                final_text=f"echo: {user_input}",
                projected_messages=[
                    {"role": "assistant", "content": f"echo: {user_input}"},
                ],
                tool_iterations=10,
                turn_id="t1", thread_id="th1",
            )
        monkeypatch.setattr(CodexAppServerSession, "run_turn", fake_run_turn)
        monkeypatch.setattr(
            CodexAppServerSession, "ensure_started", lambda self: "th1"
        )

        agent = _make_codex_agent()
        agent._skill_nudge_interval = 10
        agent._iters_since_skill = 0
        # Make valid_tool_names include 'skill_manage' so the gate passes
        agent.valid_tool_names = set(getattr(agent, "valid_tool_names", set()))
        agent.valid_tool_names.add("skill_manage")

        with patch.object(agent, "_spawn_background_review",
                          return_value=None) as spawn:
            agent.run_conversation("do tool work")

        assert spawn.called, "skill threshold tripped but review didn't fire"
        # Verify the call signature matches what _spawn_background_review
        # actually expects — this is the regression guard for the original
        # bug where the codex path called it with no args at all.
        call = spawn.call_args
        assert "messages_snapshot" in call.kwargs
        assert isinstance(call.kwargs["messages_snapshot"], list)
        assert call.kwargs["review_skills"] is True
        # Counter should be reset after the review fires
        assert agent._iters_since_skill == 0

    def test_background_review_signature_never_breaks(self, fake_session):
        """Even when no trigger fires, the helper must never call
        _spawn_background_review with the wrong signature. Run a turn,
        then run another turn after manually tripping the skill counter
        and confirm the call shape is the kwargs-only form the function
        actually accepts."""
        agent = _make_codex_agent()
        agent._skill_nudge_interval = 1  # very low so any iter trips it
        agent._iters_since_skill = 0
        agent.valid_tool_names = set(getattr(agent, "valid_tool_names", set()))
        agent.valid_tool_names.add("skill_manage")

        with patch.object(agent, "_spawn_background_review",
                          return_value=None) as spawn:
            agent.run_conversation("first")
        # The fake session reports tool_iterations=1, which trips
        # _skill_nudge_interval=1. So review should fire.
        assert spawn.called
        # Critical invariant: positional args must be empty, all real
        # args must be kwargs (matching _spawn_background_review's
        # actual signature).
        call = spawn.call_args
        assert call.args == (), (
            f"expected no positional args, got {call.args!r} — "
            "would crash _spawn_background_review at runtime"
        )
        assert "messages_snapshot" in call.kwargs

    def test_chat_completions_loop_is_not_entered(self, fake_session):
        """The early-return must bypass the regular API call loop entirely.
        We confirm by patching the SDK call and asserting it's never invoked."""
        agent = _make_codex_agent()
        # The chat_completions loop calls self.client.chat.completions.create(...)
        # If our early-return works, that path is dead.
        with patch.object(agent, "client") as client_mock, patch.object(
            agent, "_spawn_background_review", return_value=None
        ):
            agent.run_conversation("hi")
        assert not client_mock.chat.completions.create.called

    def test_gateway_terminal_cwd_seeds_codex_thread_cwd(self, monkeypatch, tmp_path):
        """Gateway sessions set TERMINAL_CWD without stamping agent.session_cwd.
        Codex app-server must still start in that configured workspace instead
        of falling back to the Hermes daemon process cwd."""
        from agent.transports.codex_app_server_session import (
            CodexAppServerSession, TurnResult,
        )

        captured: dict[str, str] = {}

        def fake_init(self, **kwargs):
            captured["cwd"] = kwargs["cwd"]
            self._thread_id = "thread-stub-1"

        def fake_run_turn(self, user_input: str, **kwargs):
            return TurnResult(
                final_text="ok",
                projected_messages=[{"role": "assistant", "content": "ok"}],
                turn_id="turn-stub-1",
                thread_id="thread-stub-1",
            )

        monkeypatch.setenv("TERMINAL_CWD", str(tmp_path))
        monkeypatch.setattr(CodexAppServerSession, "__init__", fake_init)
        monkeypatch.setattr(CodexAppServerSession, "run_turn", fake_run_turn)

        agent = _make_codex_agent()
        assert not hasattr(agent, "session_cwd")
        with patch.object(agent, "_spawn_background_review", return_value=None):
            agent.run_conversation("hi")

        assert captured["cwd"] == str(tmp_path)

    def _capture_routing_agent(self, monkeypatch):
        """Build a codex agent with a CodexAppServerSession stub that captures
        the handler passed at construction and exercises it on a request.
        Bypass decisions belong to request time, not transport creation."""
        captured: dict = {}

        def fake_init(self, **kwargs):
            captured.update(kwargs)
            self._thread_id = "thread-stub-1"

        def fake_run_turn(self, user_input: str, **kwargs):
            captured["decision"] = captured["approval_callback"](
                "true", "runtime approval test", allow_permanent=False
            )
            return TurnResult(
                final_text="ok",
                projected_messages=[{"role": "assistant", "content": "ok"}],
                turn_id="turn-stub-1",
                thread_id="thread-stub-1",
            )

        monkeypatch.setattr(CodexAppServerSession, "__init__", fake_init)
        monkeypatch.setattr(CodexAppServerSession, "run_turn", fake_run_turn)
        monkeypatch.setattr(
            CodexAppServerSession, "ensure_started", lambda self: "thread-stub-1"
        )
        return captured

    def test_gateway_codex_request_has_a_live_approval_callback(self, monkeypatch):
        import tools.approval as approval
        import tools.terminal_tool as terminal

        captured = self._capture_routing_agent(monkeypatch)
        monkeypatch.setattr(terminal, "_get_approval_callback", lambda: None)
        monkeypatch.setattr(approval, "is_approval_bypass_active", lambda: False)
        key = "test:codex:telegram:approval"
        token = approval.set_current_session_key(key)
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
        approval.register_gateway_notify(key, lambda data: approval.resolve_gateway_approval(
            key, "once", request_id=data["request_id"]
        ))
        try:
            agent = _make_codex_agent()
            with patch.object(agent, "_spawn_background_review", return_value=None):
                agent.run_conversation("request approval")
            assert callable(captured["approval_callback"])
            assert captured["decision"] == "once"
        finally:
            approval.unregister_gateway_notify(key)
            approval.reset_current_session_key(token)

    def test_approvals_mode_off_auto_approves_codex_server_requests(
        self, monkeypatch
    ):
        """When the user disables Hermes approvals, codex app-server approval
        requests should not fail closed just because no interactive callback is
        wired (the typical gateway path). Codex's own sandbox permission
        profile remains the filesystem boundary."""
        captured = self._capture_routing_agent(monkeypatch)
        with patch(
            "hermes_cli.config.load_config_readonly",
            return_value={"approvals": {"mode": "off"}},
        ):
            agent = _make_codex_agent()
            with patch.object(
                agent, "_spawn_background_review", return_value=None
            ):
                agent.run_conversation("write something")
        routing = captured["request_routing"]
        assert routing.auto_approve_exec is False
        assert routing.auto_approve_apply_patch is False
        assert captured["decision"] == "once"

    def test_yaml_boolean_false_approval_mode_also_auto_approves(
        self, monkeypatch
    ):
        """YAML 1.1 parses unquoted `off` as False; match the normal approval
        subsystem's compatibility behavior for codex app-server routing too."""
        captured = self._capture_routing_agent(monkeypatch)
        with patch(
            "hermes_cli.config.load_config_readonly",
            return_value={"approvals": {"mode": False}},
        ):
            agent = _make_codex_agent()
            with patch.object(
                agent, "_spawn_background_review", return_value=None
            ):
                agent.run_conversation("write something")
        routing = captured["request_routing"]
        assert routing.auto_approve_exec is False
        assert routing.auto_approve_apply_patch is False
        assert captured["decision"] == "once"

    def test_manual_approvals_keep_codex_server_requests_fail_closed(
        self, monkeypatch
    ):
        """Manual approvals without a registered UI must fail closed."""
        captured = self._capture_routing_agent(monkeypatch)
        with patch(
            "hermes_cli.config.load_config",
            return_value={"approvals": {"mode": "manual"}},
        ):
            agent = _make_codex_agent()
            with patch.object(
                agent, "_spawn_background_review", return_value=None
            ):
                agent.run_conversation("write something")
        routing = captured["request_routing"]
        assert routing.auto_approve_exec is False
        assert routing.auto_approve_apply_patch is False
        assert captured["decision"] == "deny"

    def test_frozen_yolo_env_auto_approves_codex_server_requests(
        self, monkeypatch
    ):
        """--yolo / HERMES_YOLO_MODE (frozen into _YOLO_MODE_FROZEN at import
        time — a prompt-injection-safe process-scoped bypass) should flow
        through to codex app-server routing so gateway/cron contexts do not
        fail closed when the user launched with yolo mode."""
        import tools.approval as _approval

        captured = self._capture_routing_agent(monkeypatch)
        monkeypatch.setattr(_approval, "_YOLO_MODE_FROZEN", True)
        with patch(
            "hermes_cli.config.load_config",
            return_value={"approvals": {"mode": "manual"}},
        ):
            agent = _make_codex_agent()
            with patch.object(
                agent, "_spawn_background_review", return_value=None
            ):
                agent.run_conversation("write something")
        routing = captured["request_routing"]
        assert routing.auto_approve_exec is False
        assert routing.auto_approve_apply_patch is False
        assert captured["decision"] == "once"

    def test_session_yolo_auto_approves_codex_server_requests(
        self, monkeypatch
    ):
        """The /yolo session toggle should be honored when the runtime request
        is handled, independent of the startup-time approvals config."""
        captured = self._capture_routing_agent(monkeypatch)
        with patch(
            "hermes_cli.config.load_config",
            return_value={"approvals": {"mode": "manual"}},
        ):
            agent = _make_codex_agent()
            with patch(
                "tools.approval.is_approval_bypass_active_for_session",
                return_value=True,
            ), patch.object(
                agent, "_spawn_background_review", return_value=None
            ):
                agent.run_conversation("write something")
        routing = captured["request_routing"]
        assert routing.auto_approve_exec is False
        assert routing.auto_approve_apply_patch is False
        assert captured["decision"] == "once"


class TestReviewForkApiModeDowngrade:
    """When the parent agent runs on codex_app_server, the background
    review fork must downgrade to codex_responses — otherwise the fork
    can't dispatch agent-loop tools (memory, skill_manage) which is the
    whole point of the review."""

    def test_codex_app_server_parent_downgrades_review_fork(self):
        """Live test against the real _spawn_background_review code path:
        verify the review_agent gets api_mode=codex_responses when the
        parent is codex_app_server."""
        from unittest.mock import MagicMock, patch as _patch
        agent = _make_codex_agent()
        # Pretend memory + skills are configured so the review fork
        # reaches the AIAgent constructor.
        agent._memory_store = MagicMock()
        agent._memory_enabled = True
        agent._user_profile_enabled = True
        # Mock _current_main_runtime to return the parent's codex_app_server
        # state so we can confirm the helper detects + downgrades it.
        agent._current_main_runtime = lambda: {
            "api_mode": "codex_app_server",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_key": "stub-token",
        }
        # Capture what AIAgent gets constructed with inside the helper.
        captured = {}

        def _capture_init(self, **kwargs):
            captured.update(kwargs)
            # Set bare attributes the rest of the spawn function reads
            # so it can finish without exploding.
            self.api_mode = kwargs.get("api_mode")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")
            self._memory_write_origin = None
            self._memory_write_context = None
            self._memory_store = None
            self._memory_enabled = False
            self._user_profile_enabled = False
            self._memory_nudge_interval = 0
            self._skill_nudge_interval = 0
            self.suppress_status_output = False
            self._session_messages = []

            def _no_op_run_conv(*a, **kw):
                return {"final_response": "", "messages": []}
            self.run_conversation = _no_op_run_conv

            def _no_op_close(*a, **kw):
                return None
            self.close = _no_op_close

        with _patch("run_agent.AIAgent.__init__", _capture_init):
            agent._spawn_background_review(
                messages_snapshot=[{"role": "user", "content": "x"}],
                review_memory=True,
                review_skills=False,
            )
            # Wait for the spawned thread to actually execute
            import time
            for _ in range(30):
                if "api_mode" in captured:
                    break
                time.sleep(0.1)

        assert captured.get("api_mode") == "codex_responses", (
            f"review fork should be downgraded to codex_responses when "
            f"parent is codex_app_server; got {captured.get('api_mode')!r}"
        )


class TestErrorHandling:
    def test_session_exception_returns_partial_with_error(self, monkeypatch):
        def boom_run_turn(self, user_input, **kwargs):
            raise RuntimeError("subprocess died")

        monkeypatch.setattr(CodexAppServerSession, "ensure_started",
                            lambda self: "t1")
        monkeypatch.setattr(CodexAppServerSession, "run_turn", boom_run_turn)

        agent = _make_codex_agent()
        with patch.object(agent, "_spawn_background_review", return_value=None):
            result = agent.run_conversation("hi")
        assert result["completed"] is False
        assert result["partial"] is True
        assert "subprocess died" in result["error"]
        assert "codex-runtime auto" in result["final_response"]

    def test_interrupted_turn_marked_partial(self, monkeypatch):
        def interrupted_turn(self, user_input, **kwargs):
            return TurnResult(
                final_text="",
                projected_messages=[],
                tool_iterations=0,
                interrupted=True,
                error="user interrupted",
                turn_id="t",
                thread_id="th",
            )
        monkeypatch.setattr(CodexAppServerSession, "ensure_started",
                            lambda self: "th")
        monkeypatch.setattr(CodexAppServerSession, "run_turn", interrupted_turn)

        agent = _make_codex_agent()
        with patch.object(agent, "_spawn_background_review", return_value=None):
            result = agent.run_conversation("hi")
        assert result["completed"] is False
        assert result["partial"] is True
        assert result["error"] == "user interrupted"


class TestSessionRetirementOnRunAgent:
    """run_agent.py side: when run_turn returns should_retire=True, the
    AIAgent must close + null _codex_session so the next turn respawns."""

    def test_should_retire_drops_session(self, monkeypatch):
        closes = {"count": 0}

        def fake_run_turn(self, user_input, **kwargs):
            return TurnResult(
                final_text="",
                projected_messages=[],
                tool_iterations=0,
                interrupted=True,
                error="turn timed out after 600.0s",
                turn_id="tu1",
                thread_id="th1",
                should_retire=True,
            )

        def fake_close(self):
            closes["count"] += 1

        monkeypatch.setattr(CodexAppServerSession, "ensure_started",
                            lambda self: "th1")
        monkeypatch.setattr(CodexAppServerSession, "run_turn", fake_run_turn)
        monkeypatch.setattr(CodexAppServerSession, "close", fake_close)

        agent = _make_codex_agent()
        with patch.object(agent, "_spawn_background_review", return_value=None):
            result = agent.run_conversation("hi")

        # The session was closed and cleared
        assert closes["count"] == 1
        assert getattr(agent, "_codex_session", "MISSING") is None
        # Partial result was still returned (caller still sees the error)
        assert result["partial"] is True
        assert result["error"] == "turn timed out after 600.0s"

    def test_normal_turn_keeps_session(self, fake_session):
        """fake_session fixture returns should_retire=False (default).
        The session must stay attached for the next turn to reuse."""
        agent = _make_codex_agent()
        with patch.object(agent, "_spawn_background_review", return_value=None):
            agent.run_conversation("hi")
        # Session was lazily created and still attached.
        assert getattr(agent, "_codex_session", None) is not None

    def test_exception_path_also_drops_session(self, monkeypatch):
        """Even if run_turn raises (not just sets should_retire), we must
        drop the session — a thrown exception is the strongest possible
        signal the process is dead."""
        closes = {"count": 0}

        def boom_run_turn(self, user_input, **kwargs):
            raise RuntimeError("codex segfaulted")

        def fake_close(self):
            closes["count"] += 1

        monkeypatch.setattr(CodexAppServerSession, "ensure_started",
                            lambda self: "th1")
        monkeypatch.setattr(CodexAppServerSession, "run_turn", boom_run_turn)
        monkeypatch.setattr(CodexAppServerSession, "close", fake_close)

        agent = _make_codex_agent()
        with patch.object(agent, "_spawn_background_review", return_value=None):
            result = agent.run_conversation("hi")

        assert closes["count"] == 1
        assert agent._codex_session is None
        assert result["completed"] is False
        assert "codex segfaulted" in result["error"]


class TestCodexToolProgressBridge:
    """#38835 / #33200: Codex app-server item notifications must surface as
    Hermes tool-progress so gateways show verbose breadcrumbs on this route.
    The original item/started-only mapper was superseded by the full event
    bridge (make_codex_app_server_event_bridge); these tests pin the same
    mapping contract against the bridge helpers."""

    def test_mapper_command_execution(self):
        from agent.codex_runtime import (
            _codex_item_to_args,
            _codex_item_to_preview,
            _codex_item_to_tool_name,
        )
        item = {"type": "commandExecution", "command": "ls -la", "cwd": "/tmp"}
        assert _codex_item_to_tool_name(item) == "exec_command"
        assert _codex_item_to_preview(item) == "ls -la"
        assert _codex_item_to_args(item) == {"command": "ls -la", "cwd": "/tmp"}

    def test_mapper_file_change(self):
        from agent.codex_runtime import (
            _codex_item_to_preview,
            _codex_item_to_tool_name,
        )
        item = {
            "type": "fileChange",
            "changes": [{"path": "a.py"}, {"path": "b.py"}],
        }
        assert _codex_item_to_tool_name(item) == "apply_patch"
        assert _codex_item_to_preview(item) == "a.py, b.py"

    def test_mapper_mcp_and_dynamic_tool_calls(self):
        from agent.codex_runtime import (
            _codex_item_to_args,
            _codex_item_to_tool_name,
        )
        mcp = {"type": "mcpToolCall", "server": "fs", "tool": "read", "arguments": {"p": 1}}
        assert _codex_item_to_tool_name(mcp) == "mcp.fs.read"
        assert _codex_item_to_args(mcp) == {"p": 1}

        dyn = {"type": "dynamicToolCall", "tool": "web_search", "arguments": {"q": "x"}}
        assert _codex_item_to_tool_name(dyn) == "web_search"

    def test_bridge_ignores_non_tool_items_and_other_methods(self):
        from agent.codex_runtime import make_codex_app_server_event_bridge
        events = []
        agent = SimpleNamespace(
            tool_progress_callback=lambda *a, **kw: events.append(a),
            _fire_stream_delta=None,
            _fire_reasoning_delta=None,
            _emit_interim_assistant_message=None,
        )
        on_event = make_codex_app_server_event_bridge(agent)
        # agentMessage started items are not tool-shaped
        on_event({"method": "item/started", "params": {
            "item": {"type": "agentMessage", "text": "hi"}}})
        # malformed / empty notes
        on_event({"method": "item/completed", "params": {}})
        on_event({})
        assert events == []

    def test_session_wired_with_on_event_that_fires_tool_progress(self, monkeypatch):
        """The session is constructed with an on_event hook that, when fed an
        item/started note, calls the agent's tool_progress_callback."""
        captured_init = {}
        events = []

        def fake_init(self, **kwargs):
            captured_init.update(kwargs)
            # minimal attrs so the rest of run_turn stubs work
            self._client = None

        def fake_run_turn(self, user_input, **kwargs):
            # Exercise the wired on_event hook with a real item/started note.
            on_event = captured_init.get("on_event")
            if on_event:
                on_event({"method": "item/started", "params": {"item": {
                    "type": "commandExecution", "command": "pytest", "cwd": "/repo"}}})
            return TurnResult(final_text="done", projected_messages=[
                {"role": "assistant", "content": "done"}], turn_id="t1", thread_id="th1")

        monkeypatch.setattr(CodexAppServerSession, "__init__", fake_init)
        monkeypatch.setattr(CodexAppServerSession, "ensure_started", lambda self: "th1")
        monkeypatch.setattr(CodexAppServerSession, "run_turn", fake_run_turn)

        agent = _make_codex_agent()
        agent.tool_progress_callback = lambda kind, name, preview, args: events.append(
            (kind, name, preview))
        with patch.object(agent, "_spawn_background_review", return_value=None):
            agent.run_conversation("run the tests")

        assert "on_event" in captured_init and captured_init["on_event"] is not None
        assert ("tool.started", "exec_command", "pytest") in events


class _ContinuityFakeClient:
    def __init__(self, *, resume_fails: bool = False) -> None:
        self.resume_fails = resume_fails
        self.requests: list[tuple[str, dict]] = []
        self.notifications: list[dict] = []
        self.closed = False

    def initialize(self, **_kwargs):
        return {}

    def request(self, method, params=None, timeout=30):
        del timeout
        params = params or {}
        self.requests.append((method, params))
        if method == "thread/resume":
            if self.resume_fails:
                raise CodexAppServerError(code=-32602, message="rollout missing")
            return {"thread": {"id": params["threadId"]}}
        if method == "thread/start":
            return {"thread": {"id": "thread-recovered"}}
        if method == "turn/start":
            thread_id = params["threadId"]
            self.notifications.extend(
                [
                    {
                        "method": "item/completed",
                        "params": {
                            "threadId": thread_id,
                            "turnId": "turn-1",
                            "item": {
                                "type": "agentMessage",
                                "id": "message-1",
                                "text": "continued",
                            },
                        },
                    },
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": thread_id,
                            "turn": {
                                "id": "turn-1",
                                "status": "completed",
                                "error": None,
                            },
                        },
                    },
                ]
            )
            return {"turn": {"id": "turn-1"}}
        return {}

    def take_notification(self, timeout=0):
        del timeout
        return self.notifications.pop(0) if self.notifications else None

    def take_server_request(self, timeout=0):
        del timeout
        return None

    def is_alive(self):
        return not self.closed

    def stderr_tail(self, _count=20):
        return []

    def close(self):
        self.closed = True


class _ThreadStateDB:
    def __init__(self, state=None) -> None:
        self.state = state
        self.patches: list[tuple[str, dict]] = []

    def get_session_model_config_value(self, session_id, key, default=None):
        del session_id, key
        return self.state if self.state is not None else default

    def patch_session_model_config(self, session_id, patch):
        self.patches.append((session_id, patch))


def _continuity_agent(**overrides):
    values = {
        "session_api_calls": 0,
        "session_prompt_tokens": 0,
        "session_completion_tokens": 0,
        "session_total_tokens": 0,
        "session_input_tokens": 0,
        "session_output_tokens": 0,
        "session_cache_read_tokens": 0,
        "session_cache_write_tokens": 0,
        "session_reasoning_tokens": 0,
        "session_estimated_cost_usd": 0.0,
        "session_cost_status": "unknown",
        "session_cost_source": "unknown",
        "model": "gpt-5.6-sol",
        "provider": "openai-codex",
        "base_url": "https://chatgpt.com/backend-api/codex",
        "api_key": "",
        "session_id": "session-1",
        "_session_db": None,
        "_session_db_created": True,
        "context_compressor": SimpleNamespace(
            update_from_response=MagicMock(),
            context_length=272_000,
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TestCodexContextContinuity:
    """Regression contour for context lost after app-server retirement."""

    def test_large_context_profile_is_forwarded_to_app_server(self):
        assert _codex_app_server_launch_args("gpt-6-astra", 1_000_000) == [
            "-c",
            'model="gpt-6-astra"',
            "-c",
            "model_context_window=1000000",
            "-c",
            "model_auto_compact_token_limit=900000",
        ]
        assert _codex_app_server_launch_args("gpt-5.6-sol", 1_000_000) == [
            "-c",
            'model="gpt-5.6-sol"',
            "-c",
            "model_context_window=900000",
            "-c",
            "model_auto_compact_token_limit=810000",
        ]
        assert _codex_app_server_launch_args("gpt-5.6-sol", 272_000) == []
        assert "model_context_window=900000" in _codex_app_server_launch_args(
            "gpt-5.6-sol-900k", 272_000
        )

    def test_explicit_profile_context_collapses_fake_picker_aliases(
        self, tmp_path, monkeypatch
    ):
        hermes_home = tmp_path / ".hermes"
        hermes_home.mkdir()
        (hermes_home / "config.yaml").write_text(
            "model:\n  context_length: 1000000\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("HERMES_HOME", str(hermes_home))

        models = get_codex_model_ids()

        assert "gpt-5.6-sol" in models
        assert not any(model.endswith("-900k") for model in models)
        assert len(models) == len(set(models))

    def test_session_resumes_thread_without_replaying_recovery_context(self):
        client = _ContinuityFakeClient()
        session = CodexAppServerSession(
            cwd="/tmp",
            resume_thread_id="thread-old",
            recovery_context="<user>old task</user>",
            client_factory=lambda **_kwargs: client,
        )

        result = session.run_turn(
            "Status?", turn_timeout=1, notification_poll_timeout=0
        )

        assert result.thread_id == "thread-old"
        assert session.resumable_thread_id == "thread-old"
        assert client.requests[0][0] == "thread/resume"
        turn_input = next(
            params for method, params in client.requests if method == "turn/start"
        )
        assert turn_input["input"][0]["text"] == "Status?"

    def test_missing_rollout_starts_new_thread_with_canonical_recovery(self):
        client = _ContinuityFakeClient(resume_fails=True)
        session = CodexAppServerSession(
            cwd="/tmp",
            resume_thread_id="thread-pruned",
            recovery_context=(
                "<user>Build Pearl Hopper</user>\n"
                "<assistant>Working</assistant>"
            ),
            client_factory=lambda **_kwargs: client,
        )

        result = session.run_turn(
            "Status?", turn_timeout=1, notification_poll_timeout=0
        )

        assert result.thread_id == "thread-recovered"
        assert session.resumable_thread_id == "thread-recovered"
        assert [method for method, _params in client.requests[:2]] == [
            "thread/resume",
            "thread/start",
        ]
        turn_input = next(
            params for method, params in client.requests if method == "turn/start"
        )
        text = turn_input["input"][0]["text"]
        assert "Build Pearl Hopper" in text
        assert "[Current user turn]\nStatus?" in text

    def test_recovery_context_excludes_current_user_turn(self):
        context = _build_codex_recovery_context(
            [
                {"role": "user", "content": "Build Pearl Hopper"},
                {"role": "assistant", "content": "I am working on it"},
                {"role": "user", "content": "Status?"},
            ],
            272_000,
        )

        assert context is not None
        assert "Build Pearl Hopper" in context
        assert "I am working on it" in context
        assert "Status?" not in context

    def test_thread_binding_is_model_scoped_and_durable(self):
        db = _ThreadStateDB(
            {"thread_id": "thread-old", "model": "gpt-5.6-sol"}
        )
        agent = SimpleNamespace(
            _session_db=db,
            _session_db_created=True,
            session_id="session-1",
            model="gpt-5.6-sol-900k",
        )

        assert _load_codex_thread_id(agent) == "thread-old"
        _persist_codex_thread_id(agent, "thread-new")

        assert db.patches == [
            (
                "session-1",
                {
                    "_codex_app_server_thread": {
                        "thread_id": "thread-new",
                        "model": "gpt-5.6-sol",
                    }
                },
            )
        ]

    def test_live_usage_refreshes_effective_context_window(self):
        agent = _continuity_agent()
        bridge = make_codex_app_server_event_bridge(agent)

        bridge(
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "tokenUsage": {
                        "last": {
                            "inputTokens": 100,
                            "cachedInputTokens": 80,
                            "outputTokens": 30,
                            "totalTokens": 130,
                        },
                        "modelContextWindow": 828_400,
                    }
                },
            }
        )

        assert agent.context_compressor.last_prompt_tokens == 100
        assert agent.context_compressor.last_completion_tokens == 30
        assert agent.context_compressor.last_total_tokens == 130
        assert agent.context_compressor.context_length == 828_400

    def test_runtime_wires_resume_recovery_launch_policy_and_persists(
        self, monkeypatch
    ):
        captured = {}

        class _Session:
            def __init__(self, **kwargs):
                captured.update(kwargs)
                self.thread_id = kwargs.get("resume_thread_id")

            def run_turn(self, user_input, **kwargs):
                captured["user_input"] = user_input
                return TurnResult(
                    final_text="continued",
                    thread_id="thread-old",
                    turn_id="turn-1",
                )

            def close(self):
                pass

        monkeypatch.setattr(
            "agent.transports.codex_app_server_session.CodexAppServerSession",
            _Session,
        )
        db = _ThreadStateDB(
            {"thread_id": "thread-old", "model": "gpt-6-astra"}
        )
        agent = _continuity_agent(
            model="gpt-6-astra",
            _session_db=db,
            _codex_session=None,
            _config_context_length=1_000_000,
            session_cwd="/tmp",
            compression_checkpoint_required=False,
            _interrupt_requested=False,
            _interrupt_message=None,
            _iters_since_skill=0,
            _skill_nudge_interval=0,
            valid_tool_names=[],
            _usage_anchor=None,
            _sync_external_memory_for_turn=lambda **_kwargs: None,
        )
        # The live effective window is smaller than the requested launch
        # window. A replacement process must re-apply profile policy, not feed
        # Codex's discounted runtime figure back as the next launch override.
        agent.context_compressor.context_length = 828_400
        messages = [
            {"role": "user", "content": "Build Pearl Hopper"},
            {"role": "assistant", "content": "Working"},
            {"role": "user", "content": "Status?"},
        ]

        result = run_codex_app_server_turn(
            agent,
            user_message="Status?",
            original_user_message="Status?",
            messages=messages,
            effective_task_id="task-1",
        )

        assert result["final_response"] == "continued"
        assert captured["resume_thread_id"] == "thread-old"
        assert "Build Pearl Hopper" in captured["recovery_context"]
        assert "model_context_window=1000000" in captured["codex_extra_args"]
        assert captured["user_input"] == "Status?"
        thread_state = db.patches[-1][1]["_codex_app_server_thread"]
        assert thread_state["thread_id"] == "thread-old"
