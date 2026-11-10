from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.ext import ApplicationHandlerStop

from clone_manager.main import callback_access_gate, message_access_gate


def fake_context(owner_id=1, maintenance="true"):
    db = SimpleNamespace(get_setting=AsyncMock(return_value=maintenance))
    application = SimpleNamespace(bot_data={"owner_id": owner_id, "db": db})
    return SimpleNamespace(application=application, user_data={})


@pytest.mark.asyncio
async def test_maintenance_blocks_admin_callbacks():
    query = SimpleNamespace(
        data="admin:settings",
        from_user=SimpleNamespace(id=2),
        answer=AsyncMock(),
    )
    update = SimpleNamespace(callback_query=query)
    context = fake_context()

    with pytest.raises(ApplicationHandlerStop):
        await callback_access_gate(update, context)

    query.answer.assert_awaited_once_with("Maintenance mode is enabled.", show_alert=True)


@pytest.mark.asyncio
async def test_close_callback_remains_available_during_maintenance():
    query = SimpleNamespace(data="branding:close", from_user=SimpleNamespace(id=2), answer=AsyncMock())
    update = SimpleNamespace(callback_query=query)
    context = fake_context()

    await callback_access_gate(update, context)

    query.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_maintenance_clears_pending_admin_message_actions():
    user_data = {
        "broadcast_mode": "text",
        "pending_broadcast": {"payload": {"kind": "text", "text": "draft"}},
        "pending_clone_edit": {"clone_id": "file-1", "field": "token"},
    }
    context = fake_context()
    context.user_data = user_data
    update = SimpleNamespace(effective_user=SimpleNamespace(id=2))

    with pytest.raises(ApplicationHandlerStop):
        await message_access_gate(update, context)

    assert context.user_data == {}
