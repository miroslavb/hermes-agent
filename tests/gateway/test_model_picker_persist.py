"""Regression tests for gateway inline-keyboard model-picker persistence.

#49066 made the typed ``/model <name>`` command persist the selected model to
``config.yaml`` by default. But the inline-keyboard picker callback
(``_on_model_selected`` in ``gateway/slash_commands.py``) was left session-only:
it hard-coded ``is_global=False`` and never wrote ``config.yaml``, so *tapping* a
model in the Telegram/Discord picker silently reverted on the next launch while
*typing* the same model persisted — a contradiction the same PR introduced.

After the fix (#49176), the picker callback honors the resolved
``persist_global`` (defaults to ``True``, still respects ``--session``) and runs
the same read-modify-write block the text path uses, so a tapped model survives
across sessions like a typed one.

These tests drive the real ``_handle_model_command`` with a fake picker-capable
adapter that captures the ``on_model_selected`` callback, then invoke that
callback and assert ``config.yaml`` is (or isn't) updated — exercising the exact
closure the PR changed, against a real temp ``HERMES_HOME``.
"""

import types

import yaml
import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource


class _FakePickerAdapter:
    """Minimal adapter that looks picker-capable and captures the callback.

    ``_handle_model_command`` gates the picker path on
    ``getattr(type(adapter), "send_model_picker", None) is not None``, so the
    method must exist on the class, not just the instance.
    """

    def __init__(self):
        self.captured_callback = None

    async def send_model_picker(self, *, on_model_selected, **kwargs):
        # Stash the closure the handler built so the test can fire a "tap".
        self.captured_callback = on_model_selected
        return types.SimpleNamespace(success=True)


def _make_runner(adapter):
    runner = object.__new__(GatewayRunner)
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner._voice_mode = {}
    runner._session_model_overrides = {}
    runner._running_agents = {}
    return runner


def _make_event(text):
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=SessionSource(platform=Platform.TELEGRAM, chat_id="12345", chat_type="dm"),
    )


def _fake_switch_result():
    """A successful ModelSwitchResult that bypasses real provider resolution."""
    from hermes_cli.model_switch import ModelSwitchResult

    return ModelSwitchResult(
        success=True,
        new_model="gpt-5.5",
        target_provider="openrouter",
        provider_changed=True,
        api_key="sk-test",
        base_url="https://openrouter.ai/api/v1",
        api_mode="chat_completions",
        provider_label="OpenRouter",
        is_global=True,
    )


def _setup_isolated_home(tmp_path, monkeypatch, model_yaml_value):
    """Write a config.yaml with the given ``model:`` value and stub heavy bits."""
    import gateway.run as gateway_run

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    cfg_path = hermes_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"model": model_yaml_value, "providers": {}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(gateway_run, "_hermes_home", hermes_home)
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    # The picker-setup path calls list_picker_providers, which otherwise hits
    # the network (OpenRouter model catalog). Stub it to a minimal list — these
    # tests capture and fire the on_model_selected callback and don't assert on
    # picker contents. The handler imports it as a local alias at call time, so
    # patching the source-module attribute takes effect.
    monkeypatch.setattr(
        "hermes_cli.model_switch.list_picker_providers",
        lambda **kw: [{"slug": "openrouter", "name": "OpenRouter", "models": ["gpt-5.5"]}],
    )
    # switch_model is imported as a local alias inside the handler
    # (`from hermes_cli.model_switch import switch_model as _switch_model`),
    # so patching the source-module attribute takes effect at call time.
    monkeypatch.setattr(
        "hermes_cli.model_switch.switch_model",
        lambda **kw: _fake_switch_result(),
    )
    # The confirmation builder resolves context length for display, which
    # otherwise makes real outbound HTTP calls (Ollama /api/show + the
    # OpenRouter models catalog). Stub it — these tests don't assert on the
    # displayed context, and the closure imports it lazily from this module.
    monkeypatch.setattr(
        "hermes_cli.model_switch.resolve_display_context_length",
        lambda *a, **k: 272000,
    )
    # save_config writes to ``get_hermes_home() / config.yaml`` — point it here.
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: hermes_home)
    monkeypatch.setattr("hermes_cli.config.get_hermes_home", lambda: hermes_home)
    return cfg_path


async def _drive_picker(runner, event):
    """Run the handler (which sends the picker) then fire the captured tap."""
    sent = await runner._handle_model_command(event)
    # Bare /model returns None (picker sent); the adapter captured the callback.
    assert sent is None
    adapter = runner.adapters[Platform.TELEGRAM]
    assert adapter.captured_callback is not None, "picker callback was not wired"
    # Simulate the user tapping "gpt-5.5" under the openrouter provider.
    return await adapter.captured_callback("12345", "gpt-5.5", "openrouter")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "seed_model",
    [
        # Already-nested dict (common case).
        {
            "default": "old-model",
            "provider": "custom",
            "base_url": "https://api.custom.example/v1",
            "api_key": "sk-stale",
            "api_mode": "anthropic_messages",
        },
        # Flat-string model: must be coerced to a nested dict on a tap (same
        # scalar-``model:`` guard the text path has) instead of raising
        # ``TypeError`` on assignment.
        "deepseek-v4-flash",
    ],
    ids=["nested-dict", "flat-string"],
)
async def test_picker_tap_persists_by_default(tmp_path, monkeypatch, seed_model):
    """Tapping a model in the picker (bare /model) persists to config.yaml,
    matching the typed ``/model`` default — this is the #49176 fix. The written
    ``model:`` must always end up a nested dict regardless of the seed shape."""
    adapter = _FakePickerAdapter()
    cfg_path = _setup_isolated_home(tmp_path, monkeypatch, seed_model)

    confirmation = await _drive_picker(_make_runner(adapter), _make_event("/model"))

    assert confirmation is not None
    assert "gpt-5.5" in confirmation
    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert isinstance(written["model"], dict), (
        "model: should be coerced to a dict, got %r" % (written["model"],)
    )
    assert written["model"]["default"] == "gpt-5.5"
    assert written["model"]["provider"] == "openrouter"
    assert "base_url" not in written["model"]
    assert "api_key" not in written["model"]
    assert "api_mode" not in written["model"]


@pytest.mark.asyncio
async def test_picker_tap_session_flag_does_not_persist(tmp_path, monkeypatch):
    """``/model --session`` then a picker tap stays in-memory only — config
    untouched, but the in-memory session override must still be applied (the
    switch worked, it just wasn't persisted)."""
    adapter = _FakePickerAdapter()
    cfg_path = _setup_isolated_home(
        tmp_path, monkeypatch, {"default": "old-model", "provider": "openai-codex"}
    )
    runner = _make_runner(adapter)

    confirmation = await _drive_picker(runner, _make_event("/model --session"))

    assert confirmation is not None
    assert "gpt-5.5" in confirmation
    # The session override IS applied in-memory (proves the path didn't no-op).
    assert runner._session_model_overrides, "session override should be set"
    assert any(
        ov.get("model") == "gpt-5.5"
        for ov in runner._session_model_overrides.values()
    )
    # But config.yaml is untouched — the override is in-memory only.
    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert written["model"]["default"] == "old-model"
    assert written["model"]["provider"] == "openai-codex"


@pytest.mark.asyncio
async def test_picker_callback_reenters_profile_scope_for_delayed_tap(
    tmp_path, monkeypatch
):
    """A delayed picker tap must resolve credentials from the routed profile.

    The picker callback fires after the original ``/model`` turn has left its
    multiplex runtime scope.  Credential resolution inside that callback (and
    its worker thread) must still see the same profile's ``.env`` rather than
    failing closed or inheriting another profile's key.
    """
    from agent import secret_scope as ss
    from gateway.run import _profile_runtime_scope

    adapter = _FakePickerAdapter()
    cfg_path = _setup_isolated_home(
        tmp_path,
        monkeypatch,
        {"default": "old-model", "provider": "openrouter"},
    )
    profile_home = cfg_path.parent
    (profile_home / ".env").write_text(
        "OPENAI_API_KEY=sk-profile-openai\n",
        encoding="utf-8",
    )

    seen = {}

    def scoped_switch(**kwargs):
        seen["openai_key"] = ss.get_secret("OPENAI_API_KEY")
        seen["home"] = str(profile_home)
        return _fake_switch_result()

    monkeypatch.setattr("hermes_cli.model_switch.switch_model", scoped_switch)
    runner = _make_runner(adapter)
    event = _make_event("/model")

    ss.set_multiplex_active(True)
    try:
        with _profile_runtime_scope(profile_home):
            sent = await runner._handle_model_command(event)
        assert sent is None
        assert adapter.captured_callback is not None
        assert ss.current_secret_scope() is None

        confirmation = await adapter.captured_callback(
            "12345", "gpt-5.5", "openrouter"
        )
    finally:
        ss.set_multiplex_active(False)

    assert "gpt-5.5" in confirmation
    assert seen == {
        "openai_key": "sk-profile-openai",
        "home": str(profile_home),
    }
    assert ss.current_secret_scope() is None


@pytest.mark.asyncio
async def test_picker_callback_persists_to_routed_profile_config(
    tmp_path, monkeypatch
):
    """A multiplex picker tap must read and write the routed profile config."""
    import gateway.run as gateway_run
    from agent import secret_scope as ss
    from gateway.run import _profile_runtime_scope

    adapter = _FakePickerAdapter()
    profile_cfg_path = _setup_isolated_home(
        tmp_path,
        monkeypatch,
        {"default": "profile-old", "provider": "openrouter"},
    )
    profile_home = profile_cfg_path.parent
    profile_cfg = yaml.safe_load(profile_cfg_path.read_text(encoding="utf-8"))
    profile_cfg["profile_marker"] = "routed-profile"
    profile_cfg_path.write_text(yaml.safe_dump(profile_cfg), encoding="utf-8")

    gateway_home = tmp_path / "gateway-root"
    gateway_home.mkdir()
    gateway_cfg_path = gateway_home / "config.yaml"
    gateway_cfg_path.write_text(
        yaml.safe_dump(
            {
                "model": {"default": "gateway-old", "provider": "nous"},
                "profile_marker": "gateway-root",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(gateway_run, "_hermes_home", gateway_home)

    runner = _make_runner(adapter)
    ss.set_multiplex_active(True)
    try:
        with _profile_runtime_scope(profile_home):
            sent = await runner._handle_model_command(_make_event("/model"))
        assert sent is None
        assert adapter.captured_callback is not None
        await adapter.captured_callback("12345", "gpt-5.5", "openrouter")
    finally:
        ss.set_multiplex_active(False)

    routed = yaml.safe_load(profile_cfg_path.read_text(encoding="utf-8"))
    gateway = yaml.safe_load(gateway_cfg_path.read_text(encoding="utf-8"))
    assert routed["profile_marker"] == "routed-profile"
    assert routed["model"]["default"] == "gpt-5.5"
    assert gateway["profile_marker"] == "gateway-root"
    assert gateway["model"]["default"] == "gateway-old"
