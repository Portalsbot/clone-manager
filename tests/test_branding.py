import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from clone_manager import branding

def test_branded_sender_adds_only_locked_close_button(monkeypatch,tmp_path):
    photo=tmp_path/"branding.jpg"; photo.write_bytes(b"fake-image")
    monkeypatch.setattr(branding,"IMAGE_PATH",photo)
    bot=SimpleNamespace(send_photo=AsyncMock(return_value=SimpleNamespace(message_id=1)))
    custom=InlineKeyboardMarkup([[InlineKeyboardButton("ABOUT",callback_data="page:about")]])
    asyncio.run(branding.send_branded(bot,123,"Hello",image_url="https://example.com/image.jpg",
        reply_markup=custom,small_caps=True,footer_message=""))
    markup=bot.send_photo.await_args.kwargs["reply_markup"]
    buttons=[button for row in markup.inline_keyboard for button in row]
    assert len([b for b in buttons if b.callback_data==branding.CLOSE_CALLBACK_DATA])==1
    assert not any(button.url for button in buttons)
    assert any(button.callback_data=="page:about" for button in buttons)
