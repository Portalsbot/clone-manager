"""Owner/admin command menus and persistent settings for Clone Manager."""
from __future__ import annotations

import json
import time
import asyncio
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from .branding import send_branded
from .formatting import render_text

FOOTER_DEFAULT = '(LINK url="https://t.me/just_astha")ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ᴄʜᴀᴛ ᴡɪᴛʜ ᴍᴇ(/LINK)'
IMAGE_DEFAULT = "https://i.ibb.co/PGpMYwYY/Gemini-Generated-Image-a7tjlia7tjlia7tj.png"
MENU_TEXT = {
    "about": "ᴍʏ ɴᴀᴍᴇ ɪs {botname}\n\nɪ ᴀᴍ ᴀ ᴘʀɪᴠᴀᴛᴇ ᴄʟᴏɴɪɴɢ ʙᴏᴛ ᴅᴇsɪɢɴᴇᴅ ᴛᴏ ᴍᴀᴋᴇ ʙᴏᴛ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ᴀɴᴅ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ sɪᴍᴘʟᴇ, ғᴀsᴛ ᴀɴᴅ ʀᴇʟɪᴀʙʟᴇ.\n\n◈ ᴏᴡɴᴇʀ: {owner}\n◈ ᴅᴇᴠᴇʟᴏᴘᴇʀ: @Just_Astha\n◈ ᴅᴀᴛᴀʙᴀsᴇ: MongoDB-compatible interface / PostgreSQL storage",
    "help": "ʜᴇʏ {mention}! ɪғ ʏᴏᴜ ɴᴇᴇᴅ ʜᴇʟᴘ, ᴄᴏɴᴛᴀᴄᴛ ᴛʜᴇ ᴀᴅᴍɪɴ: @Just_astha",
    "commands": "ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ ᴄᴏᴍᴍᴀɴᴅs\n\n/start · /clone · /commands · /settings\n/about · /help · /broadcast · /users\n/stats · /logs · /ping · /restart\n/maintenance · /setmaintenance\n/setstart · /setabout · /sethelp\n/setimage · /setbuttons · /setfooter\n/setquote · /setname · /clones\n/stopclone · /restartclone · /cloneedit\n/cloneinfo · /texts · /edittext",
    "settings": "╭───────────────⍟\n├➤ ʙᴏᴛ sᴇᴛᴛɪɴɢs\n├➤ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ʙᴏᴛ ᴘʀᴇғᴇʀᴇɴᴄᴇs ʙᴇʟᴏᴡ.\n╰───────────────⍟",
    "broadcast": "ʙʀᴏᴀᴅᴄᴀsᴛ ᴀɴᴅ ᴘʀᴏᴍᴏᴛᴇ ʏᴏᴜʀ ᴄʜᴀɴɴᴇʟ {owner} sᴇɴᴘᴀɪ",
    "users": "ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ᴜsᴇʀs sᴇɴᴘᴀɪ",
    "stats": "ʜᴇʀᴇ ɪs ʏᴏᴜʀ sᴛᴀᴛs sᴇɴᴘᴀɪ",
    "logs": "ʟᴇᴛ's ᴄʜᴇᴄᴋ ᴡʜᴀᴛ's ʜᴀᴘᴘᴇɴɪɴɢ ɪɴ ʏᴏᴜʀ ʙᴏᴛ, sᴇɴᴘᴀɪ! ♡",
    "maintenance": "ᴏᴏᴘsɪᴇ! ᴛʜᴇ ʙᴏᴛ ɪs ᴛᴀᴋɪɴɢ ᴀ ʟɪᴛᴛʟᴇ ʙʀᴇᴀᴋ, sᴇɴᴘᴀɪ! ♡\n\nᴅᴏɴ'ᴛ ᴡᴏʀʀʏ, ᴡᴇ'ʟʟ ʙᴇ ʙᴀᴄᴋ sᴏᴏɴ! ✨",
    "setmaintenance": "ᴜᴡᴜ~! ᴍʏ ʟɪᴛᴛʟᴇ sᴇʀᴠᴇʀ ɴᴇᴇᴅs sᴏᴍᴇ ʙᴇᴀᴜᴛʏ sʟᴇᴇᴘ! 🎀\n\nɪ'ᴍ ᴏɴ ᴀ ᴛɪɴʏ ʙʀᴇᴀᴋ, sᴇɴᴘᴀɪ! ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ᴀ ʟɪᴛᴛʟᴇ! ♡",
    "setstart": "ᴇᴇᴇ~! ʟᴇᴛ's ᴍᴀᴋᴇ ᴍʏ ᴡᴇʟᴄᴏᴍᴇ ᴍᴇssᴀɢᴇ ᴘʀᴇᴛᴛɪᴇʀ, sᴇɴᴘᴀɪ! ♡",
    "setabout": "ᴏʜʜ~! ᴡᴀɴɴᴀ ᴋɴᴏᴡ ᴀ ʟɪᴛᴛʟᴇ ᴍᴏʀᴇ ᴀʙᴏᴜᴛ ᴍᴇ, sᴇɴᴘᴀɪ? 🎀\n\nʜᴇʜᴇ~! ʟᴇᴛ ᴍᴇ ɪɴᴛʀᴏᴅᴜᴄᴇ ᴍʏsᴇʟғ! ♡",
    "sethelp": "ᴀɴᴏᴏ~! ɴᴇᴇᴅ sᴏᴍᴇ ʜᴇʟᴘ, sᴇɴᴘᴀɪ? 🥺\n\nʏᴏᴜʀ ʟɪᴛᴛʟᴇ ʙᴏᴛ ɢɪʀʟ ɪs ʜᴇʀᴇ ғᴏʀ ʏᴏᴜ! ♡",
    "setimage": "ᴇᴇᴇ~! ᴛɪᴍᴇ ᴛᴏ ɢɪᴠᴇ ᴍᴇ ᴀ ɴᴇᴡ ʟᴏᴏᴋ, sᴇɴᴘᴀɪ! 🎀\n\n sᴇɴᴅ ᴍᴇ ᴛʜᴇ ɴᴇᴡ ɪᴍᴀɢᴇ ʟɪɴᴋ! ♡",
    "setbuttons": "ᴏᴏʜ~! ᴛɪᴍᴇ ᴛᴏ ᴅʀᴇss ᴜᴘ ᴍʏ ʙᴜᴛᴛᴏɴs, sᴇɴᴘᴀɪ! 🎀\n\nʟᴇᴛ's ᴍᴀᴋᴇ ᴛʜᴇᴍ ᴄᴜᴛᴇʀ ᴀɴᴅ ᴍᴏʀᴇ ᴜsᴇғᴜʟ! ♡",
    "setfooter": "ᴇʜᴇ~! ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ ᴍʏ ʟɪᴛᴛʟᴇ sɪɢɴᴀᴛᴜʀᴇ, sᴇɴᴘᴀɪ? ♡\n\nᴄᴜsᴛᴏᴍɪᴢᴇ ᴍʏ ғᴏᴏᴛᴇʀ ᴛᴇxᴛ ᴀɴᴅ ʟɪɴᴋ ʜᴇʀᴇ! 🎀",
    "setquote": "ᴇʜᴇ~! ᴡᴀɴᴛ ᴛᴏ ᴍᴀᴋᴇ ᴍʏ ᴍᴇssᴀɢᴇs ʟᴏᴏᴋ ᴍᴏʀᴇ ᴇʟᴇɢᴀɴᴛ, sᴇɴᴘᴀɪ? 🎀\n\nʟᴇᴛ's ᴘʟᴀʏ ᴡɪᴛʜ ǫᴜᴏᴛᴇ sᴛʏʟᴇs! ♡",
    "setname": "ᴡᴀɪᴛ~! ᴡʜᴀᴛ sʜᴏᴜʟᴅ ɪ ᴄᴀʟʟ ᴍʏsᴇʟғ, sᴇɴᴘᴀɪ? 🎀\n\nɢɪᴠᴇ ᴍᴇ ᴀ ᴄᴜᴛᴇ ɴᴇᴡ ɴᴀᴍᴇ! ♡",
}
EDITABLE = {
    "setstart": ("message.start", "ᴇᴅɪᴛ ᴍʏ ᴡᴇʟᴄᴏᴍᴇ ᴛᴇxᴛ"),
    "setabout": ("message.about", "ᴇᴅɪᴛ ᴍʏ ᴀʙᴏᴜᴛ ᴛᴇxᴛ"),
    "sethelp": ("message.help", "ᴇᴅɪᴛ ᴍʏ ʜᴇʟᴘ ᴛᴇxᴛ"),
    "setimage": ("branding.image_url", "ᴄʜᴀɴɢᴇ ɪᴍᴀɢᴇ"),
    "setfooter": ("branding.footer", "ᴇᴅɪᴛ ғᴏᴏᴛᴇʀ"),
    "setname": ("branding.name", "ᴇᴅɪᴛ ɴᴀᴍᴇ"),
    "setquote": ("branding.quote_enabled", "ᴇᴅɪᴛ ǫᴜᴏᴛᴇ ʀᴜʟᴇ"),
    "setbuttons": ("branding.buttons_json", "ᴇᴅɪᴛ ʙᴜᴛᴛᴏɴs ᴊsᴏɴ"),
}
SETTINGS_ROWS = [
    [("· ʙᴏᴛ ɪɴғᴏ ·","admin:botinfo"),("· ᴍᴇssᴀɢᴇs ·","admin:messages")],
    [("· ʙʀᴀɴᴅɪɴɢ ·","admin:branding"),("· ʙᴜᴛᴛᴏɴs ·","admin:buttons")],
    [("· ᴀᴄᴄᴇss ·","admin:access"),("· ʟᴏɢs ·","admin:logs")],
    [("· ʙᴀᴄᴋ ·","admin:back")],
]
def _is_owner(user_id, context):
    return user_id == context.application.bot_data["owner_id"]
def _is_admin(user_id, context):
    return _is_owner(user_id, context) or user_id in context.application.bot_data.get("admins", set())
def _image(context):
    return context.application.bot_data.get("image_url") or IMAGE_DEFAULT
async def _send(context, chat_id, body, markup=None, *, parse_mode="HTML"):
    db=context.application.bot_data["db"]
    footer=await db.get_setting("branding.footer", FOOTER_DEFAULT)
    if footer:
        body=f"{body}\n\n{footer}"
    return await send_branded(context.bot, chat_id, body, image_url=_image(context),
        image_path=context.application.bot_data.get("image_path"),
        small_caps=context.application.bot_data.get("small_caps", True),
        reply_markup=markup, footer_message="")
def _markup(rows):
    keyboard=[]
    for row in rows:
        keyboard.append([InlineKeyboardButton(text,callback_data=data) for text,data in row])
    return InlineKeyboardMarkup(keyboard)
def _edit_markup(prefix):
    return _markup([
        [("· ᴘʀᴇᴠɪᴇᴡ ·",f"{prefix}:preview"),("· ᴇᴅɪᴛ ·",f"{prefix}:edit")],
        [("· sᴀᴠᴇ ·",f"{prefix}:save"),("· ᴄᴀɴᴄᴇʟ ·",f"{prefix}:cancel")],
    ])
async def _owner_admin(update, context):
    if not _is_admin(update.effective_user.id, context):
        await _send(context, update.effective_chat.id, "ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ.")
        return False
    if await context.application.bot_data["db"].get_setting("system.maintenance", "false") == "true" and not _is_owner(update.effective_user.id, context):
        return False
    return True
async def simple_menu(update, context, key, rows=None):
    if not await _owner_admin(update,context): return
    body=MENU_TEXT.get(key, key)
    if key=="about":
        me=await context.bot.get_me()
        body=body.format(botname=me.first_name,owner=context.application.bot_data["owner_id"])
    elif key=="help":
        body=body.format(mention=update.effective_user.mention_html())
    elif key=="broadcast":
        body=body.format(owner=context.application.bot_data["owner_id"])
    await _send(context,update.effective_chat.id,body,_markup(rows or [[("· ʙᴀᴄᴋ ·","admin:back")]]))
async def about(update,context):
    if not await _owner_admin(update,context): return
    me=await context.bot.get_me()
    body=await context.application.bot_data["db"].get_setting("message.about",MENU_TEXT["about"])
    await _send(context,update.effective_chat.id,body.format(botname=me.first_name,owner=context.application.bot_data["owner_id"]),_markup([[("· ʙᴀᴄᴋ ·","admin:back")]]))
async def help_command(update,context):
    if not await _owner_admin(update,context): return
    body=await context.application.bot_data["db"].get_setting("message.help",MENU_TEXT["help"])
    body=body.format(mention=update.effective_user.mention_html())
    await _send(context,update.effective_chat.id,body,_markup([[("· ᴀʙᴏᴜᴛ ·","admin:about"),("· ᴄʜᴀɴɴᴇʟ ·","admin:channel")],[("· ᴄᴏᴍᴍᴀɴᴅs ·","admin:commands")]]))
async def commands(update,context):
    await simple_menu(update,context,"commands")
async def settings(update,context):
    await simple_menu(update,context,"settings",SETTINGS_ROWS)
async def broadcast(update,context):
    await simple_menu(update,context,"broadcast",[
        [("· ᴛᴇxᴛ ʙʀᴏᴀᴅᴄᴀsᴛ ·","broadcast:text"),("· ᴍᴇᴅɪᴀ ʙʀᴏᴀᴅᴄᴀsᴛ ·","broadcast:media")],
        [("· ᴀʟʟ ᴜsᴇʀs ·","broadcast:all"),("· sᴄʜᴇᴅᴜʟᴇ ·","broadcast:schedule")],
        [("· ʀᴇᴘᴏʀᴛ ·","broadcast:report"),("· ʙᴀᴄᴋ ·","admin:back")],
    ])
async def users(update,context):
    await simple_menu(update,context,"users",[
        [("· ᴛᴏᴛᴀʟ ᴜsᴇʀs ·","users:total"),("· sᴇᴀʀᴄʜ ᴜsᴇʀ ·","users:search")],
        [("· ᴜsᴇʀ ɪɴғᴏ ·","users:info"),("· ʙʟᴏᴄᴋ ᴜsᴇʀ ·","users:block")],
        [("· ᴜɴʙʟᴏᴄᴋ ᴜsᴇʀ ·","users:unblock"),("· ᴀᴄᴛɪᴠɪᴛʏ ·","users:activity")],
        [("· ʙᴀᴄᴋ ·","admin:back")],
    ])
async def stats(update,context):
    await simple_menu(update,context,"stats",[
        [("· ᴛᴏᴛᴀʟ ᴜsᴇʀs ·","stats:users"),("· ᴀᴄᴛɪᴠᴇ ᴜsᴇʀs ·","stats:active")],
        [("· ᴛᴏᴛᴀʟ ᴄʟᴏɴᴇs ·","stats:clones"),("· ꜰɪʟᴇ ʙᴏᴛs ·","stats:file")],
        [("· ʟɪɴᴋ ʙᴏᴛs ·","stats:link"),("· ᴅᴀɪʟʏ / ᴡᴇᴇᴋʟʏ / ᴍᴏɴᴛʜʟʏ ·","stats:period")],
        [("· ᴜᴘᴛɪᴍᴇ & sʏsᴛᴇᴍ ʜᴇᴀʟᴛʜ ·","stats:health"),("· ʙᴀᴄᴋ ·","admin:back")],
    ])
async def logs(update,context):
    await simple_menu(update,context,"logs",[
        [("· ᴜsᴇʀ ᴀᴄᴛɪᴠɪᴛʏ ·","logs:users"),("· ᴄʟᴏɴᴇ ʜɪsᴛᴏʀʏ ·","logs:clones")],
        [("· ʙʀᴏᴀᴅᴄᴀsᴛ ʜɪsᴛᴏʀʏ ·","logs:broadcast"),("· ᴇʀʀᴏʀ ʟᴏɢs ·","logs:errors")],
        [("· ᴀᴅᴍɪɴ ᴀᴄᴛɪᴠɪᴛʏ ·","logs:admins"),("· ᴄʟᴇᴀʀ ʟᴏɢs ·","logs:clear")],
        [("· ʙᴀᴄᴋ ·","admin:back")],
    ])
async def maintenance(update,context):
    await simple_menu(update,context,"maintenance",[
        [("· ᴇɴᴀʙʟᴇ ·","maintenance:on"),("· ᴅɪsᴀʙʟᴇ ·","maintenance:off")],
        [("· sᴛᴀᴛᴜs ·","maintenance:status"),("· ʙᴀᴄᴋ ·","admin:back")],
    ])
async def setmaintenance(update,context):
    if not await _owner_admin(update,context): return
    await _send(context,update.effective_chat.id,MENU_TEXT["setmaintenance"],_markup([]))
async def ping(update,context):
    started=time.perf_counter()
    msg=await _send(context,update.effective_chat.id,"ᴘᴏɴɢ! ᴘᴏɴɢ: ᴍᴇᴀsᴜʀɪɴɢ... | sᴛᴀᴛᴜs: ᴏɴʟɪɴᴇ")
    latency=(time.perf_counter()-started)*1000
    try: await msg.edit_caption(caption=f"ᴘᴏɴɢ! ᴘᴏɴɢ: {latency:.0f}ms | sᴛᴀᴛᴜs: ᴏɴʟɪɴᴇ",parse_mode="HTML")
    except Exception: pass
async def _edit_command(update,context,command):
    if not await _owner_admin(update,context): return
    key,label=EDITABLE[command]
    current=await context.application.bot_data["db"].get_setting(key, FOOTER_DEFAULT if command=="setfooter" else (_image(context) if command=="setimage" else MENU_TEXT.get(command,"")))
    context.user_data["pending_setting"]={"key":key,"value":current,"command":command}
    await _send(context,update.effective_chat.id,MENU_TEXT[command],_edit_markup("editsetting"))
async def _save_input(update,context):
    pending=context.user_data.get("pending_setting")
    if not pending or not update.effective_message or not update.effective_message.text: return
    if not _is_admin(update.effective_user.id,context): context.user_data.pop("pending_setting",None); return
    value=update.effective_message.text.strip()
    if pending["key"]=="branding.image_url":
        p=urlparse(value)
        if p.scheme not in {"http","https"} or not p.netloc:
            await _send(context,update.effective_chat.id,"ɪɴᴠᴀʟɪᴅ ɪᴍᴀɢᴇ ᴜʀʟ. ᴏʟᴅ ɪᴍᴀɢᴇ ʀᴇᴍᴀɪɴs ᴜɴᴄʜᴀɴɢᴇᴅ.")
            return
    pending["draft"]=value
    await _send(context,update.effective_chat.id,"ᴅʀᴀғᴛ ʀᴇᴄᴇɪᴠᴇᴅ. ᴘʀᴇᴠɪᴇᴡ ɪᴛ ᴏʀ sᴀᴠᴇ ᴛᴏ ᴀᴘᴘʟʏ.",_edit_markup("editsetting"))
async def editsetting_callback(update,context):
    q=update.callback_query; await q.answer()
    pending=context.user_data.get("pending_setting")
    if not pending: return
    action=q.data.split(":")[-1]
    if action=="edit":
        command=pending.get("command")
        prompts={
            "setimage":"sᴇɴᴅ ᴏɴʟʏ ᴛʜᴇ ɴᴇᴡ ɪᴍᴀɢᴇ ᴜʀʟ.",
            "setbuttons":'sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ JSON ᴀʀʀᴀʏ ᴏғ ʙᴜᴛᴛᴏɴ ʀᴏᴡs. ᴇxᴀᴍᴘʟᴇ: [[{"text":"· ᴀʙᴏᴜᴛ ·","callback_data":"admin:about"},{"text":"· ᴄʜᴀɴɴᴇʟ ·","callback_data":"admin:channel"}]]',
            "setquote":"sᴇɴᴅ ᴏɴ ᴏʀ ᴏғғ.",
            "setfooter":'sᴇɴᴅ ᴛʜᴇ ғᴏᴏᴛᴇʀ ᴛᴇxᴛ. ᴜsᴇ (LINK url="https://...")ᴛᴇxᴛ(/LINK) ғᴏʀ ᴀ ᴄʟɪᴄᴋᴀʙʟᴇ ʟɪɴᴋ.',
        }
        await _send(context,q.message.chat_id,prompts.get(command,"sᴇɴᴅ ᴛʜᴇ ɴᴇᴡ ᴠᴀʟᴜᴇ ɴᴏᴡ. ɪ'ʟʟ ᴋᴇᴇᴘ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ᴠᴀʟᴜᴇ ᴜɴᴛɪʟ ʏᴏᴜ sᴀᴠᴇ."))
    elif action=="preview":
        value=pending.get("draft",pending["value"])
        if pending["key"]=="branding.image_url":
            try:
                await context.bot.send_photo(q.message.chat_id,photo=value,caption="ɪᴍᴀɢᴇ ᴘʀᴇᴠɪᴇᴡ")
                pending["previewed"]=True
            except Exception:
                pending["previewed"]=False
                await q.answer("Image URL could not be loaded by Telegram. The current image is unchanged.",show_alert=True)
                return
        elif pending["key"]=="branding.buttons_json":
            try:
                from .branding import keyboard_from_buttons
                markup=keyboard_from_buttons(json.loads(value),small_caps=True)
                if not markup: raise ValueError("empty layout")
                await _send(context,q.message.chat_id,"ʙᴜᴛᴛᴏɴ ʟᴀʏᴏᴜᴛ ᴘʀᴇᴠɪᴇᴡ",markup)
                pending["previewed"]=True
            except Exception:
                pending["previewed"]=False
                await q.answer("Invalid button layout JSON.",show_alert=True)
                return
        else:
            await _send(context,q.message.chat_id,value)
            pending["previewed"]=True
    elif action=="save":
        if "draft" not in pending:
            await q.answer("No new value to save.",show_alert=True); return
        if pending["key"] in {"branding.image_url","branding.buttons_json"} and not pending.get("previewed"):
            await q.answer("Preview the new value successfully before saving.",show_alert=True); return
        value=pending["draft"]
        if pending["key"]=="branding.buttons_json":
            try:
                parsed=json.loads(value)
                if not isinstance(parsed,list): raise ValueError()
            except Exception:
                await q.answer("Buttons must be a valid JSON array.",show_alert=True); return
        if pending["key"]=="branding.quote_enabled" and value.lower() not in {"on","off","true","false"}:
            await q.answer("Use on or off.",show_alert=True); return
        await context.application.bot_data["db"].set_setting(pending["key"],value)
        if pending["key"]=="branding.image_url": context.application.bot_data["image_url"]=value
        if pending["key"]=="branding.quote_enabled":
            from .formatting import set_quote_enabled
            set_quote_enabled(value.lower() in {"on","true"})
        if pending["key"]=="branding.name":
            await context.bot.set_my_name(value[:64])
        context.user_data.pop("pending_setting",None)
        await _send(context,q.message.chat_id,"sᴇᴛᴛɪɴɢ sᴀᴠᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ! ♡")
    elif action=="cancel":
        context.user_data.pop("pending_setting",None)
        await _send(context,q.message.chat_id,"ᴄᴀɴᴄᴇʟʟᴇᴅ. ᴏʟᴅ sᴇᴛᴛɪɴɢs ʀᴇᴍᴀɪɴ ᴜɴᴄʜᴀɴɢᴇᴅ.")
async def callback_router(update,context):
    q=update.callback_query
    if not q: return
    data=q.data
    if data not in {"admin:about","admin:channel"} and not _is_admin(q.from_user.id,context):
        await q.answer("Owner / Admin only.",show_alert=True)
        return
    await q.answer()
    if data.startswith("admin:"):
        key=data.split(":")[1]
        if key=="back": await _send(context,q.message.chat_id,MENU_TEXT["settings"],_markup(SETTINGS_ROWS))
        elif key=="commands": await _send(context,q.message.chat_id,MENU_TEXT["commands"],_markup([[("· ʙᴀᴄᴋ ·","admin:back")]]))
        elif key=="about":
            me=await context.bot.get_me()
            body=await context.application.bot_data["db"].get_setting("message.about",MENU_TEXT["about"])
            await _send(context,q.message.chat_id,body.format(botname=me.first_name,owner=context.application.bot_data["owner_id"]),_markup([[("· ʙᴀᴄᴋ ·","admin:back")]]))
        elif key=="channel":
            body="╭───────────────⍟\\n├➽ Dᴇᴠᴇʟᴏᴩᴇʀ : @Just_astha\\n├➽ Oᴡɴᴇʀ : @Just_astha\\n├➽ Aɴɪᴍᴇ Iɴᴅᴇx : @Master_Index\\n├➽ Fɪɴɪsʜᴇᴅ Aɴɪᴍᴇ : @anime_portals\\n├➽ Oɴɢᴏɪɴɢ Aɴɪᴍᴇ : @ongoing_portals\\n├➽ Mᴀɴʜᴡᴀ / Mᴀɴɢᴀ: @Manga_Portals\\n├➽ Nᴇᴛᴡᴏʀᴋ : @Anime_Gateway\\n├➽ Rᴇǫ/Cʜᴀᴛ : https://t.me/+lB05vD5bGyszMzg1\\n╰───────────────⍟"
            await _send(context,q.message.chat_id,body,_markup([[("· ʙᴀᴄᴋ ·","admin:back")]]))
        else: await _send(context,q.message.chat_id,f"{key.title()} settings",_markup([[("· ʙᴀᴄᴋ ·","admin:back")]]))
    elif data.startswith("maintenance:"):
        action=data.split(":")[1]; db=context.application.bot_data["db"]
        if action in {"on","off"}:
            await db.set_setting("system.maintenance","true" if action=="on" else "false")
            body="ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴇɴᴀʙʟᴇᴅ." if action=="on" else "ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴅɪsᴀʙʟᴇᴅ."
        else: body="ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ: "+("ᴏɴ" if await db.get_setting("system.maintenance","false")=="true" else "ᴏғғ")
        await _send(context,q.message.chat_id,body)
    elif data.startswith("editsetting:"):
        await editsetting_callback(update,context); return
    elif data.startswith("stats:"):
        db=context.application.bot_data["db"]; action=data.split(":")[1]
        if action in {"users","active"}:
            sql="SELECT COUNT(*) FROM bot_users"
            if action=="active": sql+=" WHERE last_seen > NOW() - INTERVAL '7 days'"
            value=await db.require().fetchval(sql); body=f"{action.title()}: {value}"
        elif action in {"clones","file","link"}:
            sql="SELECT COUNT(*) FROM clone_instances"+(" WHERE product=$1" if action in {"file","link"} else "")
            value=await db.require().fetchval(sql,action) if action in {"file","link"} else await db.require().fetchval(sql)
            body=f"{action.title()} clones: {value}"
        elif action=="period":
            day=await db.require().fetchval("SELECT COUNT(*) FROM clone_instances WHERE created_at>NOW()-INTERVAL '1 day'")
            week=await db.require().fetchval("SELECT COUNT(*) FROM clone_instances WHERE created_at>NOW()-INTERVAL '7 days'")
            month=await db.require().fetchval("SELECT COUNT(*) FROM clone_instances WHERE created_at>NOW()-INTERVAL '30 days'")
            body=f"ᴄʟᴏɴᴇs ᴄʀᴇᴀᴛᴇᴅ\\nᴅᴀɪʟʏ: {day}\\nᴡᴇᴇᴋʟʏ: {week}\\nᴍᴏɴᴛʜʟʏ: {month}"
        elif action=="health":
            try:
                context.application.bot_data["db"].require()
                context.application.bot_data["provisioner"].client.ping()
                body="ᴅᴀᴛᴀʙᴀsᴇ: ᴄᴏɴɴᴇᴄᴛᴇᴅ\\nᴅᴏᴄᴋᴇʀ: ᴄᴏɴɴᴇᴄᴛᴇᴅ\\nᴍᴀɴᴀɢᴇʀ: ᴏɴʟɪɴᴇ"
            except Exception:
                body="ᴅᴀᴛᴀʙᴀsᴇ / ᴅᴏᴄᴋᴇʀ ᴄᴏɴɴᴇᴄᴛɪᴏɴ ᴘʀᴏʙʟᴇᴍ."
        else: body="ᴜɴᴋɴᴏᴡɴ sᴛᴀᴛs ᴄᴀᴛᴇɢᴏʀʏ."
        await _send(context,q.message.chat_id,body)
    elif data.startswith("users:"):
        action=data.split(":")[1]
        db=context.application.bot_data["db"]
        if action=="total":
            value=await db.require().fetchval("SELECT COUNT(DISTINCT user_id) FROM bot_users")
            await _send(context,q.message.chat_id,f"ᴛᴏᴛᴀʟ ʀᴇɢɪsᴛᴇʀᴇᴅ ᴜsᴇʀs: {value}")
        elif action=="activity":
            value=await db.require().fetchval("SELECT COUNT(DISTINCT user_id) FROM bot_users WHERE last_seen>NOW()-INTERVAL '7 days'")
            await _send(context,q.message.chat_id,f"ᴀᴄᴛɪᴠᴇ ᴜsᴇʀs ɪɴ 7 ᴅᴀʏs: {value}")
        elif action in {"search","info","block","unblock"}:
            context.user_data["user_action"]=action
            await _send(context,q.message.chat_id,"sᴇɴᴅ ᴛʜᴇ ᴛᴇʟᴇɢʀᴀᴍ ᴜsᴇʀ ɪᴅ.")
        else:
            await _send(context,q.message.chat_id,"ᴜsᴇʀ ᴀᴄᴛɪᴏɴ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.")
    elif data.startswith("broadcast:"):
        if data=="broadcast:report":
            rows=await context.application.bot_data["db"].require().fetch("SELECT created_at,details FROM manager_activity WHERE action='broadcast' ORDER BY created_at DESC LIMIT 10")
            report="ʙʀᴏᴀᴅᴄᴀsᴛ ʜɪsᴛᴏʀʏ\\n\\n"+("\\n".join(f"{r['created_at']} · {r['details']}" for r in rows) if rows else "ɴᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ʀᴇᴄᴏʀᴅs.")
            await _send(context,q.message.chat_id,report)
        elif data=="broadcast:schedule":
            await _send(context,q.message.chat_id,"sᴄʜᴇᴅᴜʟᴇᴅ ʙʀᴏᴀᴅᴄᴀsᴛ ɪs ɴᴏᴛ ᴇɴᴀʙʟᴇᴅ ʏᴇᴛ. ᴜsᴇ ᴛᴇxᴛ ᴏʀ ᴍᴇᴅɪᴀ ʙʀᴏᴀᴅᴄᴀsᴛ ғᴏʀ ɪᴍᴍᴇᴅɪᴀᴛᴇ ᴅᴇʟɪᴠᴇʀʏ.")
        else:
            context.user_data["broadcast_mode"]=data.split(":")[1]
            await _send(context,q.message.chat_id,"sᴇɴᴅ ᴛʜᴇ ᴍᴇssᴀɢᴇ ᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ. ᴛʜɪs ᴡɪʟʟ ɢᴏ ᴛᴏ ᴀʟʟ ᴜsᴇʀs ᴡʜᴏ sᴛᴀʀᴛᴇᴅ ᴀ ᴄʟᴏɴᴇ.")
    elif data.startswith("logs:"):
        action=data.split(":")[1]
        db=context.application.bot_data["db"]
        if action=="clear":
            markup=_markup([[("· ʏᴇs, ᴄʟᴇᴀʀ ·","logs:clear-confirm"),("· ᴄᴀɴᴄᴇʟ ·","admin:back")]])
            await _send(context,q.message.chat_id,"ᴀʀᴇ ʏᴏᴜ sᴜʀᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʟᴇᴀʀ ᴀʟʟ ᴀᴄᴛɪᴠɪᴛʏ ʟᴏɢs?",markup)
            return
        if action=="clear-confirm":
            await db.require().execute("DELETE FROM manager_activity")
            await _send(context,q.message.chat_id,"ᴀᴄᴛɪᴠɪᴛʏ ʟᴏɢs ᴄʟᴇᴀʀᴇᴅ.")
            return
        mapping={"users":"user","clones":"clone","broadcast":"broadcast","errors":"error","admins":"admin"}
        category=mapping.get(action)
        if not category:
            await _send(context,q.message.chat_id,"ᴜɴᴋɴᴏᴡɴ ʟᴏɢ ᴄᴀᴛᴇɢᴏʀʏ."); return
        rows=await db.require().fetch("SELECT actor_id,action,details,level,created_at FROM manager_activity WHERE action ILIKE $1 ORDER BY created_at DESC LIMIT 25",f"%{category}%")
        body="(Quote start) ʟᴀsᴛ 25 ʟᴏɢ ᴇɴᴛʀɪᴇs (Quote end)\\n\\n"
        body+="\\n".join(f"{r['created_at']} · {r['action']} · {r['details']}" for r in rows) if rows else "ɴᴏ ʟᴏɢ ᴇɴᴛʀɪᴇs ғᴏᴜɴᴅ."
        await _send(context,q.message.chat_id,body)
async def capture_broadcast(update,context):
    mode=context.user_data.pop("broadcast_mode",None)
    if not mode or not update.effective_message: return
    if not _is_admin(update.effective_user.id,context): return
    rows=await context.application.bot_data["db"].require().fetch("SELECT user_id FROM bot_users")
    sent=failed=0
    for row in rows:
        try:
            if update.effective_message.text:
                await send_branded(context.bot,row["user_id"],update.effective_message.text,
                    image_url=_image(context),image_path=context.application.bot_data.get("image_path"),
                    small_caps=context.application.bot_data.get("small_caps",True),
                    footer_message=await context.application.bot_data["db"].get_setting("branding.footer",FOOTER_DEFAULT))
            elif update.effective_message.photo:
                await send_branded(context.bot,row["user_id"],update.effective_message.caption or " ",
                    image_url=_image(context),image_path=context.application.bot_data.get("image_path"),
                    small_caps=context.application.bot_data.get("small_caps",True),
                    footer_message=await context.application.bot_data["db"].get_setting("branding.footer",FOOTER_DEFAULT))
            sent+=1
        except Exception: failed+=1
    await context.application.bot_data["db"].require().execute("INSERT INTO manager_activity(actor_id,action,details,level) VALUES($1,$2,$3,$4)",update.effective_user.id,"broadcast","sent="+str(sent)+", failed="+str(failed),"info")
    await _send(context,update.effective_chat.id,f"ʙʀᴏᴀᴅᴄᴀsᴛ ғɪɴɪsʜᴇᴅ. sᴇɴᴛ: {sent} · ғᴀɪʟᴇᴅ: {failed}")
async def restart(update,context):
    if not await _owner_admin(update,context): return
    markup=_markup([[("· ʀᴇsᴛᴀʀᴛ ᴀɢᴀɪɴ ·","restart:again"),("· sᴛᴏᴘ ·","restart:stop")]])
    await _send(context,update.effective_chat.id,"ʀᴇsᴛᴀʀᴛɪɴɢ ʙᴏᴛ, sᴇɴᴘᴀɪ...",markup)

async def restart_callback(update,context):
    q=update.callback_query
    if not _is_admin(q.from_user.id,context):
        await q.answer("Owner / Admin only.",show_alert=True); return
    await q.answer()
    action=q.data.split(":")[1]
    if action=="again":
        await _send(context,q.message.chat_id,"ʙᴏᴛ ɪs ʀᴇsᴛᴀʀᴛɪɴɢ ɴᴏᴡ...")
        await asyncio.sleep(1)
        os.execv(sys.executable,[sys.executable,*sys.argv])
    db=context.application.bot_data["db"]
    who=q.from_user.first_name or str(q.from_user.id)
    notice=f"ʙᴏᴛ sᴛᴏᴘᴘᴇᴅ ʙʏ {who} sᴏ, ʙᴇ ᴘᴀᴛɪᴇɴᴛ ᴀɴᴅ ᴡᴇ'ʟʟ ᴄᴏᴍᴇ ʙᴀᴄᴋ sᴏᴏɴ."
    recipients=await db.require().fetch("SELECT DISTINCT user_id FROM bot_users")
    for row in recipients:
        try:
            await send_branded(context.bot,row["user_id"],notice,image_url=_image(context),
                image_path=context.application.bot_data.get("image_path"),
                small_caps=context.application.bot_data.get("small_caps",True),
                footer_message=await db.get_setting("branding.footer",FOOTER_DEFAULT))
        except Exception:
            pass
    await _send(context,q.message.chat_id,"sᴛᴏᴘ ɴᴏᴛɪᴄᴇ ᴅᴇʟɪᴠᴇʀᴇᴅ.")
    if _is_owner(q.from_user.id,context):
        await asyncio.sleep(1)
        os._exit(0)
    await db.set_setting("system.maintenance","true")
    await _send(context,q.message.chat_id,"ᴀᴅᴍɪɴ sᴛᴏᴘ ᴀᴄᴛɪᴠᴀᴛᴇᴅ. ᴛʜᴇ ʙᴏᴛ ɪs ɴᴏᴡ ʀᴇsᴛʀɪᴄᴛᴇᴅ ғᴏʀ ᴀᴅᴍɪɴs ᴀɴᴅ ᴜsᴇʀs; ᴏᴡɴᴇʀ ᴀᴄᴄᴇss ʀᴇᴍᴀɪɴs.")
async def _register_edit(update,context,command):
    await _edit_command(update,context,command)
async def capture_user_action(update,context):
    action=context.user_data.pop("user_action",None)
    if not action or not update.effective_message or not update.effective_message.text: return
    if not _is_admin(update.effective_user.id,context): return
    try: target=int(update.effective_message.text.strip())
    except ValueError:
        await _send(context,update.effective_chat.id,"ɪɴᴠᴀʟɪᴅ ᴜsᴇʀ ɪᴅ. ᴜsᴇ ɴᴜᴍᴇʀɪᴄ ᴛᴇʟᴇɢʀᴀᴍ ɪᴅ.")
        return
    db=context.application.bot_data["db"]
    clone_id=context.application.bot_data["clone_id"]
    if action in {"block","unblock"}:
        banned=action=="block"
        await db.require().execute("""INSERT INTO bot_users(clone_id,user_id,is_banned) VALUES($1,$2,$3)
            ON CONFLICT(clone_id,user_id) DO UPDATE SET is_banned=EXCLUDED.is_banned""",clone_id,target,banned)
        result_word="ʙʟᴏᴄᴋᴇᴅ" if banned else "ᴜɴʙʟᴏᴄᴋᴇᴅ"
        await _send(context,update.effective_chat.id,f"ᴜsᴇʀ {target} ʜᴀs ʙᴇᴇɴ {result_word}.")
    else:
        rows=await db.require().fetch("SELECT clone_id,first_seen,last_seen,is_banned FROM bot_users WHERE user_id=$1 ORDER BY last_seen DESC LIMIT 20",target)
        if not rows:
            await _send(context,update.effective_chat.id,"ɴᴏ ʀᴇᴄᴏʀᴅ ғᴏᴜɴᴅ ғᴏʀ ᴛʜɪs ᴜsᴇʀ.")
        else:
            body=f"ᴜsᴇʀ ɪᴅ: {target}\\n" + "\\n".join(f"{r['clone_id']} · first: {r['first_seen']} · last: {r['last_seen']} · blocked: {r['is_banned']}" for r in rows)
            await _send(context,update.effective_chat.id,body)

async def command_access_gate(update,context):
    user=update.effective_user
    if not user or not update.effective_message: return
    command=(update.effective_message.text or "").split()[0].split("@",1)[0].lower()
    if _is_owner(user.id,context): 
        await context.application.bot_data["db"].require().execute("INSERT INTO manager_activity(actor_id,action,details) VALUES($1,$2,$3)",user.id,"admin_command",command)
        return
    if await context.application.bot_data["db"].get_setting("system.maintenance","false")=="true":
        from telegram.ext import ApplicationHandlerStop
        raise ApplicationHandlerStop
    if command=="/start": return
    if _is_admin(user.id,context):
        await context.application.bot_data["db"].require().execute("INSERT INTO manager_activity(actor_id,action,details) VALUES($1,$2,$3)",user.id,"admin_command",command)
    if not _is_admin(user.id,context):
        await _send(context,update.effective_chat.id,"ᴘʟᴇᴀsᴇ ᴜsᴇ /start ᴏɴʟʏ. ᴛʜɪs ʙᴏᴛ ɪs ᴘʀɪᴠᴀᴛᴇ.")
        from telegram.ext import ApplicationHandlerStop
        raise ApplicationHandlerStop

def add_admin_handlers(app):
    for name,func in [("about",about),("help",help_command),("commands",commands),("settings",settings),
        ("broadcast",broadcast),("users",users),("stats",stats),("logs",logs),("ping",ping),
        ("restart",restart),("maintenance",maintenance),("setmaintenance",setmaintenance)]:
        app.add_handler(CommandHandler(name,func))
    for name in EDITABLE:
        async def handler(update,context,n=name): await _register_edit(update,context,n)
        app.add_handler(CommandHandler(name,handler))
    app.add_handler(CallbackQueryHandler(callback_router,pattern=r"^(admin:|maintenance:|stats:|users:|broadcast:|logs:)"))
    app.add_handler(CallbackQueryHandler(restart_callback,pattern=r"^restart:(again|stop)$"))
    app.add_handler(CallbackQueryHandler(editsetting_callback,pattern=r"^editsetting:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, capture_user_action),group=-5)
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, capture_broadcast),group=-4)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _save_input),group=-3)
