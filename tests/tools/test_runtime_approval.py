"""Runtime requests use real queues/protocol; config is an in-memory test stub."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import threading
import pytest
from tools import approval, approval_context, terminal_tool
from agent.transports.codex_app_server_session import CodexAppServerSession


def policy(monkeypatch, mode):
    # No config setter: this test never writes a real or temporary profile.
    monkeypatch.setattr(approval_context, "_get_approval_config", lambda: {"mode": mode})


@pytest.fixture
def ui(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
    monkeypatch.setattr(approval, "_YOLO_MODE_FROZEN", False)
    monkeypatch.setattr(approval_context, "_get_approval_timeout", lambda: 0.08)
    monkeypatch.setattr(terminal_tool, "_get_approval_callback", lambda: None)
    policy(monkeypatch, "manual")
    key = "runtime-approval-test"
    token = approval_context.set_current_session_key(key)
    approval.clear_session(key)
    yield key
    approval.unregister_gateway_notify(key)
    approval.clear_session(key)
    approval_context.reset_current_session_key(token)


def resolve(key, choice, seen):
    def notify(data):
        seen.append(data)
        assert approval.resolve_gateway_approval(key, choice, request_id=data["request_id"]) == 1
    approval.register_gateway_notify(key, notify)


@pytest.mark.parametrize("method", ["item/commandExecution/requestApproval", "item/fileChange/requestApproval"])
@pytest.mark.parametrize("choice,expected", [("once", "accept"), ("deny", "decline"), ("session", "decline"), ("always", "decline"), ("garbage", "decline")])
def test_protocol_queue_round_trip(ui, method, choice, expected):
    seen, responses = [], []
    resolve(ui, choice, seen)
    session = CodexAppServerSession(cwd="/tmp", approval_callback=approval.request_runtime_approval)
    session._client = SimpleNamespace(respond=lambda rid, data: responses.append((rid, data)))
    session._track_pending_file_change({"method": "item/started", "params": {"item": {
        "type": "fileChange", "id": "patch-1", "changes": [{"path": "/tmp/demo.txt", "kind": {"type": "update"}, "diff": "+example"}]}}})
    session._handle_server_request({"id": "rpc-1", "method": method, "params": {
        "command": "printf approval-test", "cwd": "/tmp", "itemId": "patch-1", "reason": "test request", "grantRoot": "/tmp"}})
    assert responses == [("rpc-1", {"decision": expected})]
    assert len(seen) == 1
    assert seen[0]["allow_permanent"] is False and seen[0]["allow_session"] is False
    assert "test request" in seen[0]["description"]
    if "fileChange" in method: assert "demo.txt" in seen[0]["command"]
    assert not approval.list_gateway_approvals(ui)
    assert not approval._session_approved.get(ui)
    session._client = None


def test_reused_session_rechecks_policy_and_listener(ui, monkeypatch):
    seen, responses = [], []
    session = CodexAppServerSession(cwd="/tmp", approval_callback=approval.request_runtime_approval)
    session._client = SimpleNamespace(respond=lambda rid, data: responses.append(data["decision"]))
    req = {"id": 1, "method": "item/commandExecution/requestApproval", "params": {"command": "true"}}
    policy(monkeypatch, "off")
    session._handle_server_request(req)
    policy(monkeypatch, "manual")
    resolve(ui, "deny", seen)
    session._handle_server_request(req)
    resolve(ui, "once", seen)
    session._handle_server_request(req)
    approval.unregister_gateway_notify(ui)
    session._handle_server_request(req)
    assert responses == ["accept", "decline", "accept", "decline"]
    assert len(seen) == 2
    session._client = None


@pytest.mark.parametrize("mode", ["manual", "smart"])
def test_missing_gateway_listener_never_falls_back_to_cli(ui, monkeypatch, mode):
    policy(monkeypatch, mode)
    monkeypatch.setattr(terminal_tool, "_get_approval_callback", lambda: pytest.fail("must not use CLI"))
    assert approval.request_runtime_approval("true", "reason") == "deny"


def test_timeout_and_stale_button(ui):
    seen = []
    approval.register_gateway_notify(ui, seen.append)
    assert approval.request_runtime_approval("true", "reason") == "deny"
    assert not approval.list_gateway_approvals(ui)
    stale = seen[0]["request_id"]
    def notify(data):
        assert approval.resolve_gateway_approval(ui, "once", request_id=stale) == 0
        assert approval.resolve_gateway_approval(ui, "deny", request_id=data["request_id"]) == 1
    approval.register_gateway_notify(ui, notify)
    assert approval.request_runtime_approval("true", "reason") == "deny"


def test_send_failure_cleans_queue(ui):
    def broken(data): raise RuntimeError("simulated delivery failure")
    approval.register_gateway_notify(ui, broken)
    assert approval.request_runtime_approval("true", "reason") == "deny"
    assert not approval.list_gateway_approvals(ui)


def test_interrupt_cancels(ui):
    from tools.interrupt import set_interrupt
    approval.register_gateway_notify(ui, lambda data: set_interrupt(True))
    try:
        assert approval.request_runtime_approval("true", "reason") == "deny"
        assert not approval.list_gateway_approvals(ui)
    finally: set_interrupt(False)


def test_unregister_cancels(ui):
    approval.register_gateway_notify(ui, lambda data: approval.unregister_gateway_notify(ui))
    assert approval.request_runtime_approval("true", "reason") == "deny"


@pytest.mark.parametrize("marker", ["HERMES_CRON_SESSION", "HERMES_SINGLE_QUERY_SESSION"])
def test_unattended_does_not_use_gateway_address(ui, monkeypatch, marker):
    monkeypatch.setenv(marker, "1")
    approval.register_gateway_notify(ui, lambda data: pytest.fail("unattended prompt"))
    assert approval.request_runtime_approval("true", "reason") == "deny"


def test_concurrent_sessions_cannot_consume_other_answer(ui, monkeypatch):
    monkeypatch.setattr(approval_context, "_get_approval_timeout", lambda: 3)
    keys = ["runtime:a", "runtime:b"]
    arrived = {key: threading.Event() for key in keys}; cards = {}
    for key in keys:
        def notify(data, key=key):
            cards[key] = data; arrived[key].set()
        approval.register_gateway_notify(key, notify)
    def request(key):
        token = approval_context.set_current_session_key(key)
        try: return approval.request_runtime_approval("true", "same command")
        finally: approval_context.reset_current_session_key(token)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(request, key) for key in keys]
            assert all(event.wait(2) for event in arrived.values())
            assert approval.resolve_gateway_approval(keys[1], "once", request_id=cards[keys[0]]["request_id"]) == 0
            approval.resolve_gateway_approval(keys[0], "once", request_id=cards[keys[0]]["request_id"])
            approval.resolve_gateway_approval(keys[1], "deny", request_id=cards[keys[1]]["request_id"])
            assert [f.result(2) for f in futures] == ["once", "deny"]
    finally:
        for key in keys:
            approval.unregister_gateway_notify(key); approval.clear_session(key)


def test_cli_callback_is_fresh_and_once_only(ui, monkeypatch):
    monkeypatch.setattr(approval, "_is_gateway_approval_context", lambda: False)
    calls = []
    def callback(command, description, **kwargs):
        calls.append(kwargs); return "once"
    monkeypatch.setattr(terminal_tool, "_get_approval_callback", lambda: callback)
    assert approval.request_runtime_approval("true", "reason") == "once"
    assert calls == [{"allow_permanent": False, "allow_session": False}]
    monkeypatch.setattr(terminal_tool, "_get_approval_callback", lambda: None)
    assert approval.request_runtime_approval("true", "reason") == "deny"
