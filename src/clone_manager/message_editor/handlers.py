"""Telegram-native message and inline-button editor."""
from __future__ import annotations
import json
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from ..branding import send_branded, keyboard_from_buttons

SETTING_KEYS = {"manager.start":"message.start","manager.about":"message.about","manager.help":"message.help"}


def allowed(update: Update, owner_id: int, admins: set[int]) -> bool:
    user = update.effective_user
    return bool(user and (user.id == owner_id or user.id in admins))

async def texts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context.application.bot_data["owner_id"], context.application.bot_data["admins"]):
        return
    keys=sorted(context.application.bot_data["defaults"].keys())
    listing="(Quote start) ᴍʏ ᴍᴇssᴀɢᴇ ᴇᴅɪᴛᴏʀ 🎀 (Quote end)\n\nᴄʜᴏᴏsᴇ ᴀ ᴛᴇxᴛ ᴛᴏ ᴇᴅɪᴛ."
    buttons=[InlineKeyboardButton(key,callback_data=f"textedit:{key}") for key in keys]
    keyboard=[buttons[i:i+2] for i in range(0,len(buttons),2)]
    await send_branded(context.bot,update.effective_chat.id,listing,
        image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
        small_caps=context.application.bot_data["small_caps"],reply_markup=InlineKeyboardMarkup(keyboard),
        footer_message=await context.application.bot_data["db"].get_setting("branding.footer",""))

def _text_editor_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("· ᴘʀᴇᴠɪᴇᴡ ·",callback_data="textaction:preview"),InlineKeyboardButton("· ᴇᴅɪᴛ ᴛᴇxᴛ ·",callback_data="textaction:edit")],
        [InlineKeyboardButton("· sᴀᴠᴇ ·",callback_data="textaction:save"),InlineKeyboardButton("· ᴄᴀɴᴄᴇʟ ·",callback_data="textaction:cancel")],
    ])

async def _begin_template_edit(update,context,key,chat_id=None):
    for state in ("pending_setting","user_action","pending_clone_edit","pending_clone_product",
                  "editing_text_key","editing_clone_id","broadcast_mode","pending_broadcast","awaiting_broadcast_time"):
        context.user_data.pop(state,None)
    defaults=context.application.bot_data["defaults"]
    if key not in defaults:
        await send_branded(context.bot,chat_id or update.effective_chat.id,"ᴜɴᴋɴᴏᴡɴ ᴍᴇssᴀɢᴇ ᴋᴇʏ. ᴜsᴇ /texts.",
            image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
            small_caps=context.application.bot_data["small_caps"])
        return
    setting_key=SETTING_KEYS.get(key)
    clone_id=context.application.bot_data["clone_id"]
    if setting_key:
        current=await context.application.bot_data["db"].get_setting(setting_key,defaults[key])
    else:
        current=await context.application.bot_data["db"].get_text(clone_id,key,defaults[key])
    context.user_data["pending_text_editor"]={"key":key,"setting_key":setting_key,"clone_id":clone_id,"current":current}
    await send_branded(context.bot,chat_id or update.effective_chat.id,
        f"(Quote start) ᴇᴅɪᴛɪɴɢ {key} (Quote end)\n\nᴄᴜʀʀᴇɴᴛ ᴛᴇxᴛ:\n{current}\n\nᴄʜᴏᴏsᴇ ᴀɴ ᴀᴄᴛɪᴏɴ ʙᴇʟᴏᴡ.",
        image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
        small_caps=context.application.bot_data["small_caps"],reply_markup=_text_editor_markup(),
        footer_message=await context.application.bot_data["db"].get_setting("branding.footer",""))

async def select_template_callback(update,context):
    q=update.callback_query
    if not allowed(update,context.application.bot_data["owner_id"],context.application.bot_data["admins"]):
        await q.answer("Owner / Admin only.",show_alert=True); return
    await q.answer()
    await _begin_template_edit(update,context,q.data.split(":",1)[1],chat_id=q.message.chat_id)

async def textaction_callback(update,context):
    q=update.callback_query
    if not allowed(update,context.application.bot_data["owner_id"],context.application.bot_data["admins"]):
        await q.answer("Owner / Admin only.",show_alert=True); return
    await q.answer()
    pending=context.user_data.get("pending_text_editor")
    if not pending:
        await q.answer("This editing session has expired.",show_alert=True); return
    action=q.data.split(":",1)[1]
    if action=="edit":
        context.user_data["awaiting_text_draft"]=True
        await send_branded(context.bot,q.message.chat_id,
            "sᴇɴᴅ ᴛʜᴇ ᴄᴏᴍᴘʟᴇᴛᴇ ɴᴇᴡ ᴍᴇssᴀɢᴇ ᴛᴇxᴛ. ɪᴛ ᴡɪʟʟ ɴᴏᴛ ʙᴇ sᴀᴠᴇᴅ ᴜɴᴛɪʟ ʏᴏᴜ ᴘʀᴇss sᴀᴠᴇ.",
            image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
            small_caps=context.application.bot_data["small_caps"])
    elif action=="preview":
        await send_branded(context.bot,q.message.chat_id,pending.get("draft",pending["current"]),
            image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
            small_caps=context.application.bot_data["small_caps"],
            footer_message=await context.application.bot_data["db"].get_setting("branding.footer",""))
    elif action=="save":
        if "draft" not in pending:
            await q.answer("No draft is ready to save.",show_alert=True); return
        if pending["setting_key"]:
            await context.application.bot_data["db"].set_setting(pending["setting_key"],pending["draft"])
            if pending["key"]=="manager.start":
                context.application.bot_data["defaults"]["manager.start"]=pending["draft"]
        else:
            await context.application.bot_data["db"].set_text(pending["clone_id"],pending["key"],pending["draft"])
        context.user_data.pop("pending_text_editor",None)
        context.user_data.pop("awaiting_text_draft",None)
        await send_branded(context.bot,q.message.chat_id,"ᴍᴇssᴀɢᴇ sᴀᴠᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ! ♡",
            image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
            small_caps=context.application.bot_data["small_caps"])
    elif action=="cancel":
        context.user_data.pop("pending_text_editor",None)
        context.user_data.pop("awaiting_text_draft",None)
        await send_branded(context.bot,q.message.chat_id,"ᴄᴀɴᴄᴇʟʟᴇᴅ. ᴛʜᴇ ᴏʟᴅ ᴍᴇssᴀɢᴇ ʀᴇᴍᴀɪɴs ᴜɴᴄʜᴀɴɢᴇᴅ.",
            image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
            small_caps=context.application.bot_data["small_caps"])

async def edittext(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context.application.bot_data["owner_id"], context.application.bot_data["admins"]):
        return
    if not context.args:
        return await texts(update,context)
    await _begin_template_edit(update,context,context.args[0])

async def previewtext(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context.application.bot_data["owner_id"], context.application.bot_data["admins"]):
        return
    if not context.args:
        body = "Usage: `/previewtext TEMPLATE_KEY`"
        markup = None
    else:
        key = context.args[0]
        defaults = context.application.bot_data["defaults"]
        if key not in defaults:
            body, markup = "Unknown template key. Use /texts.", None
        else:
            if key in SETTING_KEYS:
                body=await context.application.bot_data["db"].get_setting(SETTING_KEYS[key],defaults[key])
            else:
                body = await context.application.bot_data["db"].get_text(
                    context.application.bot_data["clone_id"], key, defaults[key]
                )
            rows = await context.application.bot_data["db"].get_buttons(
                context.application.bot_data["clone_id"], key
            )
            markup = keyboard_from_buttons(rows)
    await send_branded(context.bot, update.effective_chat.id, body,
                       image_url=context.application.bot_data["image_url"],
                       image_path=context.application.bot_data["image_path"],
                       small_caps=context.application.bot_data["small_caps"], reply_markup=markup,
                       footer_message=await context.application.bot_data["db"].get_setting("branding.footer",""))

async def resettext(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context.application.bot_data["owner_id"], context.application.bot_data["admins"]):
        return
    if not context.args:
        body = "Usage: `/resettext TEMPLATE_KEY`"
    else:
        key = context.args[0]
        if key not in context.application.bot_data["defaults"]:
            body = "Unknown template key. Use /texts."
        else:
            if key in SETTING_KEYS:
                await context.application.bot_data["db"].delete_setting(SETTING_KEYS[key])
            else:
                await context.application.bot_data["db"].reset_text(context.application.bot_data["clone_id"], key)
            body = f"Default template restored: `{key}`"
    await send_branded(context.bot, update.effective_chat.id, body,
                       image_url=context.application.bot_data["image_url"],
                       image_path=context.application.bot_data["image_path"],
                       small_caps=context.application.bot_data["small_caps"],
                       footer_message=await context.application.bot_data["db"].get_setting("branding.footer",""))


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context.application.bot_data["owner_id"], context.application.bot_data["admins"]):
        return
    if not context.args:
        body = "Usage: `/buttons TEMPLATE_KEY`"
    else:
        key = context.args[0]
        if key not in context.application.bot_data["defaults"]:
            body = "Unknown template key."
        else:
            rows = await context.application.bot_data["db"].get_buttons(context.application.bot_data["clone_id"], key)
            body = f"Buttons for `{key}`:\n```json\n{json.dumps(rows, ensure_ascii=False, indent=2)}\n```\n\nUse `/addbutton {key} | LABEL | URL` or `/delbutton {key} | BUTTON_INDEX`."
    await send_branded(context.bot, update.effective_chat.id, body,
                       image_url=context.application.bot_data["image_url"],
                       image_path=context.application.bot_data["image_path"],
                       small_caps=context.application.bot_data["small_caps"],
                       footer_message=await context.application.bot_data["db"].get_setting("branding.footer",""))

async def addbutton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context.application.bot_data["owner_id"], context.application.bot_data["admins"]): return
    raw = update.effective_message.text.partition(" ")[2]
    parts = [x.strip() for x in raw.split("|", 2)]
    if len(parts) != 3:
        body = "Usage: `/addbutton TEMPLATE_KEY | BUTTON LABEL | https://example.com`"
    else:
        key, label, url = parts
        if key not in context.application.bot_data["defaults"] or not url.startswith(("https://", "http://")):
            body = "Invalid template key or URL. Only HTTP(S) URLs are accepted."
        else:
            rows = await context.application.bot_data["db"].get_buttons(context.application.bot_data["clone_id"], key)
            rows.append([{"text": label[:64], "url": url}])
            await context.application.bot_data["db"].set_buttons(context.application.bot_data["clone_id"], key, rows)
            body = f"Button added to `{key}`. Preview with /previewtext {key}."
    await send_branded(context.bot, update.effective_chat.id, body,
                       image_url=context.application.bot_data["image_url"],
                       image_path=context.application.bot_data["image_path"],
                       small_caps=context.application.bot_data["small_caps"])

async def delbutton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context.application.bot_data["owner_id"], context.application.bot_data["admins"]): return
    raw = update.effective_message.text.partition(" ")[2]
    parts = [x.strip() for x in raw.split("|", 1)]
    if len(parts) != 2:
        body = "Usage: `/delbutton TEMPLATE_KEY | BUTTON_INDEX` (1-based)"
    else:
        key, index_text = parts
        try: index = int(index_text) - 1
        except ValueError: index = -1
        if key not in context.application.bot_data["defaults"] or index < 0:
            body = "Invalid template key or button index."
        else:
            rows = await context.application.bot_data["db"].get_buttons(context.application.bot_data["clone_id"], key)
            flat = [b for row in rows for b in row]
            if index >= len(flat):
                body = "Button index not found."
            else:
                del flat[index]
                rows = [[b] for b in flat]
                await context.application.bot_data["db"].set_buttons(context.application.bot_data["clone_id"], key, rows)
                body = f"Button removed from `{key}`."
    await send_branded(context.bot, update.effective_chat.id, body,
                       image_url=context.application.bot_data["image_url"],
                       image_path=context.application.bot_data["image_path"],
                       small_caps=context.application.bot_data["small_caps"])

async def editbutton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context.application.bot_data["owner_id"], context.application.bot_data["admins"]): return
    raw = update.effective_message.text.partition(" ")[2]
    parts = [x.strip() for x in raw.split("|", 3)]
    if len(parts) != 4:
        body = "Usage: `/editbutton TEMPLATE_KEY | BUTTON_INDEX | LABEL | URL` (1-based)"
    else:
        key, index_text, label, url = parts
        try: index = int(index_text) - 1
        except ValueError: index = -1
        if key not in context.application.bot_data["defaults"] or index < 0 or not url.startswith(("https://", "http://")):
            body = "Invalid template key, index or HTTP(S) URL."
        else:
            rows = await context.application.bot_data["db"].get_buttons(context.application.bot_data["clone_id"], key)
            flat = [b for row in rows for b in row]
            if index >= len(flat): body = "Button index not found."
            else:
                flat[index] = {"text": label[:64], "url": url}
                await context.application.bot_data["db"].set_buttons(context.application.bot_data["clone_id"], key, [[b] for b in flat])
                body = f"Button updated for `{key}`. Preview with /previewtext {key}."
    await send_branded(context.bot, update.effective_chat.id, body,
                       image_url=context.application.bot_data["image_url"],
                       image_path=context.application.bot_data["image_path"],
                       small_caps=context.application.bot_data["small_caps"])

async def capture_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.text:
        return
    if not allowed(update, context.application.bot_data["owner_id"], context.application.bot_data["admins"]):
        context.user_data.pop("editing_text_key", None)
        context.user_data.pop("pending_text_editor", None)
        return
    pending=context.user_data.get("pending_text_editor")
    if pending and context.user_data.get("awaiting_text_draft"):
        pending["draft"]=update.effective_message.text
        context.user_data["awaiting_text_draft"]=False
        await send_branded(context.bot,update.effective_chat.id,
            "ᴅʀᴀғᴛ ʀᴇᴄᴇɪᴠᴇᴅ! ᴘʀᴇᴠɪᴇᴡ ɪᴛ ᴏʀ sᴀᴠᴇ ᴛᴏ ᴀᴘᴘʟʏ ᴛʜᴇ ᴄʜᴀɴɢᴇ.",
            image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
            small_caps=context.application.bot_data["small_caps"],reply_markup=_text_editor_markup(),
            footer_message=await context.application.bot_data["db"].get_setting("branding.footer",""))
        return
    key=context.user_data.get("editing_text_key")
    if not key:
        return
    setting_key=context.user_data.pop("editing_setting_key",None)
    if setting_key:
        await context.application.bot_data["db"].set_setting(setting_key,update.effective_message.text)
        if setting_key=="message.start":
            context.application.bot_data["defaults"]["manager.start"]=update.effective_message.text
    else:
        target_clone=context.user_data.pop("editing_clone_id",context.application.bot_data["clone_id"])
        await context.application.bot_data["db"].set_text(target_clone,key,update.effective_message.text)
    context.user_data.pop("editing_text_key",None)
    await send_branded(context.bot,update.effective_chat.id,f"Saved {key} successfully.",
        image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
        small_caps=context.application.bot_data["small_caps"])

def add_editor_handlers(app):
    app.add_handler(CommandHandler("texts", texts))
    app.add_handler(CallbackQueryHandler(select_template_callback,pattern=r"^textedit:"))
    app.add_handler(CallbackQueryHandler(textaction_callback,pattern=r"^textaction:"))
    app.add_handler(CommandHandler("edittext", edittext))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, capture_edit), group=-1)
