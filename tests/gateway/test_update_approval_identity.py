"""Exercise the actual moved gateway approval notifier, not a facade source scan."""
import asyncio
from concurrent.futures import Future
from types import SimpleNamespace
import pytest
from gateway.run_turn_runner import TurnRunner

@pytest.mark.parametrize("metadata", [None, {"thread_id": "77"}])
def test_request_identity_survives_moved_gateway_notifier(monkeypatch, metadata):
    sent = []
    class Adapter:
        def pause_typing_for_chat(self, chat_id):
            pass
        async def send_exec_approval(self, **kwargs):
            sent.append(kwargs)
            return SimpleNamespace(success=True)
    ctx = SimpleNamespace(_status_adapter=Adapter(), _status_chat_id="12345",
                          session_key="test:telegram:notify", _status_thread_metadata=metadata)
    turn = TurnRunner(SimpleNamespace(), ctx)
    monkeypatch.setattr(turn, "_close_native_stream_boundary", lambda *_: None)
    def schedule(coro, *_):
        f = Future()
        f.set_result(asyncio.run(coro))
        return f
    monkeypatch.setattr(turn, "_schedule", schedule)
    turn._approval_notify_sync({"request_id": "exact-request", "command": "printf test",
                                "allow_permanent": False, "allow_session": False})
    assert len(sent) == 1
    assert sent[0]["metadata"] == {**(metadata or {}), "approval_request_id": "exact-request"}
    assert sent[0]["session_key"] == "test:telegram:notify"
    assert sent[0]["allow_permanent"] is False and sent[0]["allow_session"] is False
    assert metadata is None or metadata == {"thread_id": "77"}
