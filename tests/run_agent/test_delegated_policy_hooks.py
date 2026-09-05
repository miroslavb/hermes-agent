"""Real plugin discovery and AIAgent dispatch; only the external transport is fake."""
import json
from unittest.mock import patch

import pytest

from hermes_cli.plugins import PluginManager
from agent.transports.codex_app_server_session import CodexAppServerSession, TurnResult
from tests.run_agent.test_codex_app_server_integration import _make_codex_agent
from tests.run_agent.test_verification_continuation_budget import agent, _response


@pytest.fixture
def policy_plugin(tmp_path, monkeypatch):
    home = tmp_path / "home"
    plugin = home / "plugins" / "completion-policy"
    plugin.mkdir(parents=True)
    (home / "config.yaml").write_text("plugins:\n  enabled: [completion-policy]\n")
    (plugin / "plugin.yaml").write_text("name: completion-policy\nversion: 0.1.0\ndescription: test\n")
    log = tmp_path / "events.jsonl"
    (plugin / "__init__.py").write_text(
        "import json\n"
        f"LOG = {str(log)!r}\n"
        "def observe(event, kw):\n"
        "    with open(LOG, 'a') as f: f.write(json.dumps({'event':event, **kw}, default=str)+'\\n')\n"
        "def register(ctx):\n"
        "    ctx.register_hook('pre_llm_call', lambda **kw: {'context':'<policy>keep sources current</policy>'})\n"
        "    ctx.register_hook('pre_api_request', lambda **kw: observe('request', kw))\n"
        "    ctx.register_hook('post_llm_call', lambda **kw: observe('completed', kw))\n"
        "    ctx.register_hook('pre_turn_complete', lambda **kw: {'action':'continue','message':'Verify the source or leave a scoped handoff.'} if str(kw.get('user_message','')).startswith('Change') else None)\n"
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    mgr = PluginManager()
    mgr.discover_and_load()
    monkeypatch.setattr("hermes_cli.plugins.get_plugin_manager", lambda: mgr)
    return mgr, log


def test_codex_receives_policy_and_emits_one_completion(policy_plugin, monkeypatch):
    inputs = []
    def run(self, user_input, **kw):
        inputs.append(user_input)
        if kw.get("on_dispatch"):
            kw["on_dispatch"]({"threadId":"thread-1", "input":[{"type":"text", "text":user_input}]})
        return TurnResult(final_text="done", projected_messages=[{"role":"assistant", "content":"done"}], thread_id="thread-1", turn_id="turn-1")
    monkeypatch.setattr(CodexAppServerSession, "run_turn", run)
    agent = _make_codex_agent()
    with patch.object(agent, "_spawn_background_review"):
        result = agent.run_conversation("Record the revised project constraint")
    assert "<policy>keep sources current</policy>" in inputs[0]
    user = next(m for m in result["messages"] if m["role"] == "user")
    assert user["content"] == "Record the revised project constraint"
    assert user["api_content"] == inputs[0]
    events = [json.loads(x) for x in policy_plugin[1].read_text().splitlines()]
    assert [e["event"] for e in events] == ["request", "completed"]
    assert events[0]["request_scope"] == "runtime_turn"
    assert events[0]["request_messages"][-1]["content"] == inputs[0]
    assert events[0]["turn_id"] == events[1]["turn_id"]
    assert result["completed"] is True


def test_non_code_completion_is_bounded_and_finalized_once(policy_plugin, monkeypatch):
    inputs = []
    def run(self, user_input, **kw):
        inputs.append(user_input)
        return TurnResult(final_text=f"answer {len(inputs)}", projected_messages=[{"role":"assistant", "content":f"answer {len(inputs)}"}], thread_id="same-thread", turn_id=str(len(inputs)))
    monkeypatch.setattr(CodexAppServerSession, "run_turn", run)
    agent = _make_codex_agent()
    with patch.object(agent, "_spawn_background_review"), patch.object(agent, "_sync_external_memory_for_turn") as sync:
        result = agent.run_conversation("Change the project constraint without editing code")
    assert len(inputs) == 2
    assert "Verify the source" in inputs[1]
    assert result["final_response"] == "answer 2"
    assert result["api_calls"] == 2
    assert agent.session_api_calls == 2
    assert sync.call_count == 1
    events = [json.loads(x) for x in policy_plugin[1].read_text().splitlines()]
    assert [e["event"] for e in events] == ["completed"]
    assert [m["content"] for m in result["messages"] if m["role"] == "assistant"] == ["answer 1", "answer 2"]


@pytest.mark.parametrize("interrupted,error", [(True, None), (False, "transport failed")])
def test_partial_turn_never_claims_completion(policy_plugin, monkeypatch, interrupted, error):
    calls = []
    def run(self, user_input, **kw):
        calls.append(user_input)
        return TurnResult(final_text="partial", interrupted=interrupted, error=error, thread_id="thread-1")
    monkeypatch.setattr(CodexAppServerSession, "run_turn", run)
    agent = _make_codex_agent()
    with patch.object(agent, "_spawn_background_review"):
        result = agent.run_conversation("Change the constraint")
    assert len(calls) == 1
    assert result["completed"] is False
    assert not policy_plugin[1].exists()


def test_native_no_code_completion_uses_discovered_plugin(agent, policy_plugin, monkeypatch):
    calls = []
    agent.max_iterations = 3
    monkeypatch.setenv("HERMES_VERIFY_ON_STOP", "0")
    def response(kwargs):
        calls.append(kwargs)
        return _response(f"native answer {len(calls)}")
    agent._interruptible_api_call = response
    result = agent.run_conversation("Change the decision without editing files")
    assert len(calls) == 2
    assert result["final_response"] == "native answer 2"
    assert not agent._turn_file_mutation_paths
    assert not any(m.get("_pre_verify_synthetic") for m in result["messages"])
    events = [json.loads(x) for x in policy_plugin[1].read_text().splitlines()]
    assert sum(e["event"] == "completed" for e in events) == 1
