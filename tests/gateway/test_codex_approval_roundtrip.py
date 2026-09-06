"""Codex -> real approval queue -> Telegram card/callback, with network stubbed."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from gateway.config import PlatformConfig
from plugins.platforms.telegram.adapter import TelegramAdapter
from tools import approval
from agent.transports.codex_app_server_session import CodexAppServerSession


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["once", "deny", "stale", "restart", "wrong_chat", "wrong_message", "unoffered_choice", "unauthorized"])
async def test_telegram_response_is_bound_to_codex_request(monkeypatch, case):
    stale = case in {"stale", "restart"}
    monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
    monkeypatch.setattr(approval, "_get_approval_config", lambda: {"mode": "manual"})
    monkeypatch.setattr(approval, "_get_approval_timeout", lambda: 0.15 if stale else 3)
    monkeypatch.setattr(approval, "_YOLO_MODE_FROZEN", False)
    # The repository's Telegram SDK test shim uses mock constructors. Keep
    # concrete card payloads while the real adapter and callback logic run.
    monkeypatch.setattr("plugins.platforms.telegram.adapter.InlineKeyboardButton",
        lambda text, callback_data: SimpleNamespace(text=text, callback_data=callback_data))
    monkeypatch.setattr("plugins.platforms.telegram.adapter.InlineKeyboardMarkup",
        lambda rows: SimpleNamespace(inline_keyboard=rows))
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="test-only"))
    adapter._bot = SimpleNamespace(send_message=AsyncMock(side_effect=[SimpleNamespace(message_id=41), SimpleNamespace(message_id=42)]))
    monkeypatch.setattr(adapter, "_is_callback_user_authorized", lambda *a, **k: True)
    key = "agent:main:telegram:dm:12345"
    token = approval.set_current_session_key(key)
    loop = asyncio.get_running_loop()
    sent = asyncio.Queue()
    async def send(data):
        result = await adapter.send_exec_approval(
            chat_id="12345", command=data["command"], description=data["description"],
            session_key=key, allow_permanent=data["allow_permanent"], allow_session=data["allow_session"],
            metadata={"approval_request_id": data["request_id"]},
        )
        assert result.success
        kwargs = adapter._bot.send_message.call_args.kwargs
        buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
        assert [b.text for b in buttons] == ["✅ Allow Once", "❌ Deny"]
        await sent.put((buttons[0].callback_data, int(result.message_id)))
    def notify(data):
        asyncio.run_coroutine_threadsafe(send(data), loop).result(2)
    approval.register_gateway_notify(key, notify)
    replies = []
    session = CodexAppServerSession(cwd="/tmp", approval_callback=approval.request_runtime_approval)
    session._client = SimpleNamespace(respond=lambda rid, data: replies.append((rid, data["decision"])))
    def request(rid):
        session._handle_server_request({"id": rid, "method": "item/commandExecution/requestApproval", "params": {"command": "printf test", "cwd": "/tmp"}})
    async def click(card, attempt="once"):
        data, mid = card
        if attempt in {"deny", "unoffered_choice"}:
            data = data.replace("ea:once:", "ea:deny:" if attempt == "deny" else "ea:always:")
        if attempt == "wrong_message": mid += 100
        monkeypatch.setattr(adapter, "_is_callback_user_authorized", lambda *a, **k: attempt != "unauthorized")
        query = SimpleNamespace(data=data, message=SimpleNamespace(chat_id=12346 if attempt == "wrong_chat" else 12345, message_id=mid, message_thread_id=None, chat=SimpleNamespace(type="private")),
            from_user=SimpleNamespace(id=12345, first_name="Operator"), answer=AsyncMock(), edit_message_text=AsyncMock())
        await adapter._handle_callback_query(SimpleNamespace(callback_query=query), SimpleNamespace())
        return query
    try:
        first = asyncio.create_task(asyncio.to_thread(request, "first"))
        card1 = await asyncio.wait_for(sent.get(), 2)
        if stale:
            await asyncio.wait_for(first, 2)
            assert replies == [("first", "decline")]
            monkeypatch.setattr(approval, "_get_approval_timeout", lambda: 3)
            if case == "restart":
                import itertools
                adapter._approval_counter = itertools.count(1)
            second = asyncio.create_task(asyncio.to_thread(request, "second"))
            card2 = await asyncio.wait_for(sent.get(), 2)
            await click(card1)
            assert approval.has_blocking_approval(key), "stale Telegram card resolved the NEW command"
            await click(card2)
            await asyncio.wait_for(second, 2)
            assert replies == [("first", "decline"), ("second", "accept")]
        else:
            if case not in {"once", "deny"}:
                await click(card1, case)
                assert approval.has_blocking_approval(key)
            await click(card1, "deny" if case == "deny" else "once")
            await asyncio.wait_for(first, 2)
            assert replies == [("first", "decline" if case == "deny" else "accept")]
    finally:
        approval.unregister_gateway_notify(key)
        approval.clear_session(key)
        approval.reset_current_session_key(token)
        session._client = None
