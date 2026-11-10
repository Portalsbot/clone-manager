from __future__ import annotations
import asyncio, logging, secrets, re, json
from pathlib import Path
from cryptography.fernet import Fernet
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from ..branding import send_branded, keyboard_from_buttons
from ..provisioner import DockerProvisioner

log=logging.getLogger(__name__)

async def _send(update,context,body,markup=None):
    return await send_branded(context.bot,update.effective_chat.id,body,
        image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
        small_caps=context.application.bot_data["small_caps"],reply_markup=markup,
        footer_message=await context.application.bot_data["db"].get_setting("branding.footer",""))

def _allowed(user_id:int, context)->bool:
    return user_id in context.application.bot_data["allowed_users"]

async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    db=context.application.bot_data["db"]
    clone_id=context.application.bot_data["clone_id"]
    user_id=update.effective_user.id
    existing=await db.require().fetchrow("SELECT is_banned FROM bot_users WHERE clone_id=$1 AND user_id=$2",clone_id,user_id)
    if existing and existing["is_banned"]:
        await _send(update,context,"ʏᴏᴜ ᴄᴀɴɴᴏᴛ ᴜsᴇ ᴛʜɪs ʙᴏᴛ. ᴄᴏɴᴛᴀᴄᴛ ᴛʜᴇ ᴀᴅᴍɪɴ.")
        return
    await db.require().execute("""INSERT INTO bot_users(clone_id,user_id) VALUES($1,$2)
        ON CONFLICT(clone_id,user_id) DO UPDATE SET last_seen=NOW()""",clone_id,user_id)
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("· ᴀʙᴏᴜᴛ ·",callback_data="admin:about"),InlineKeyboardButton("· ᴄʜᴀɴɴᴇʟ ·",callback_data="admin:channel")],
        [InlineKeyboardButton("· ᴄᴏᴍᴍᴀɴᴅs ·",callback_data="admin:commands")]
    ])
    saved_buttons=await context.application.bot_data["db"].get_setting("branding.buttons_json","")
    if saved_buttons:
        try:
            custom=keyboard_from_buttons(json.loads(saved_buttons),small_caps=context.application.bot_data["small_caps"])
            if custom: markup=custom
        except (ValueError,TypeError):
            log.warning("Ignoring invalid persisted start-button layout")
    default_text=f"(Quote start) ʙᴏᴛ-ʟɪᴠᴇ, HI {update.effective_user.mention_html()} ~ (Quote end)\n\n(Quote start) **Pʀɪᴠᴀᴛᴇ Cloning ʙᴏᴛ: Clone ᴀɴᴅ Mᴀɴᴀɢᴇ ʙᴏᴛs sɪᴍᴘʟʏ, ǫᴜɪᴄᴋʟʏ, ᴀɴᴅ ᴇғғᴏʀᴛʟᴇssʟʏ. (Quote end)"
    body=await context.application.bot_data["db"].get_setting("message.start",default_text)
    await _send(update,context,body,markup)

async def clone(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context):
        await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ.")
        return
    markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("ғɪʟᴇ sʜᴀʀɪɴɢ ʙᴏᴛ",callback_data="clone:select:file")],
        [InlineKeyboardButton("ʟɪɴᴋ sʜᴀʀɪɴɢ ʙᴏᴛ",callback_data="clone:select:link")],
    ])
    await _send(update,context,context.application.bot_data["defaults"]["cloner.select"],markup)

async def select_product(update:Update,context:ContextTypes.DEFAULT_TYPE):
    query=update.callback_query; await query.answer()
    if not _allowed(query.from_user.id,context): return
    product=query.data.rsplit(":",1)[-1]
    if product not in {"file","link"}: return
    context.user_data["pending_clone_product"]=product
    await send_branded(context.bot,query.message.chat_id,
        context.application.bot_data["defaults"]["cloner.token"],
        image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
        small_caps=context.application.bot_data["small_caps"],
        footer_message=await context.application.bot_data["db"].get_setting("branding.footer",""))

async def receive_token(update:Update,context:ContextTypes.DEFAULT_TYPE):
    product=context.user_data.get("pending_clone_product")
    if not product or not update.effective_message or not update.effective_message.text: return
    if not _allowed(update.effective_user.id,context):
        context.user_data.pop("pending_clone_product",None); return
    token=update.effective_message.text.strip()
    # Delete the incoming token message as soon as possible. Deletion is best-effort.
    try: await update.effective_message.delete()
    except Exception: log.warning("Could not delete submitted token message")
    context.user_data.pop("pending_clone_product",None)
    try:
        candidate=Bot(token=token)
        await candidate.initialize()
        try: me=await candidate.get_me()
        finally: await candidate.shutdown()
        if not me.is_bot: raise ValueError("Token did not resolve to a bot account")
    except Exception:
        await _send(update,context,"ɪɴᴠᴀʟɪᴅ ᴏʀ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ ʙᴏᴛ ᴛᴏᴋᴇɴ. ɢᴇɴᴇʀᴀᴛᴇ ᴀ ɴᴇᴡ ᴛᴏᴋᴇɴ ɪɴ @BotFather ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.")
        return
    # Encrypt token at rest. Never log or echo the plaintext token.
    cipher=Fernet(context.application.bot_data["encryption_key"])
    encrypted=cipher.encrypt(token.encode()).decode()
    clone_id=f"{product}-{me.id}"
    db=context.application.bot_data["db"]
    existing=await db.require().fetchrow("SELECT clone_id FROM clone_instances WHERE bot_id=$1",me.id)
    if existing:
        await _send(update,context,"ᴛʜɪs ʙᴏᴛ ᴛᴏᴋᴇɴ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴇɢɪsᴛᴇʀᴇᴅ. ᴜsᴇ /clones ᴛᴏ ᴠɪᴇᴡ ʏᴏᴜʀ ɪɴsᴛᴀɴᴄᴇs.")
        return
    await db.require().execute(
        "INSERT INTO clone_instances(clone_id,owner_id,product,bot_id,bot_username,encrypted_token,status) VALUES($1,$2,$3,$4,$5,$6,'provisioning')",
        clone_id,update.effective_user.id,product,me.id,me.username or str(me.id),encrypted)
    try:
        provisioner=context.application.bot_data["provisioner"]
        container_id=await provisioner.create(product,clone_id,token,update.effective_user.id)
        await db.require().execute("UPDATE clone_instances SET container_id=$1,status='running',updated_at=NOW() WHERE clone_id=$2",container_id,clone_id)
        await _send(update,context,f"✅ ᴄʟᴏɴᴇ ᴅᴇᴘʟᴏʏᴇᴅ: @{me.username}\nhttps://t.me/{me.username}\nProduct: {product.title()}\nID: `{clone_id}`")
    except Exception as exc:
        log.exception("Clone provisioning failed (%s)",type(exc).__name__)
        await db.require().execute("UPDATE clone_instances SET status='failed',error_code=$1,updated_at=NOW() WHERE clone_id=$2",type(exc).__name__,clone_id)
        await _send(update,context,f"ᴛᴏᴋᴇɴ ᴠᴀʟɪᴅᴀᴛᴇᴅ ғᴏʀ @{me.username}, ʙᴜᴛ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ғᴀɪʟᴇᴅ. ᴇʀʀᴏʀ: {type(exc).__name__}. ᴄᴏɴᴛᴀᴄᴛ ᴘʟᴀᴛғᴏʀᴍ ᴏᴡɴᴇʀ.")

async def clones(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context):
        await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ.")
        return
    db=context.application.bot_data["db"]
    rows=await db.require().fetch(
        "SELECT clone_id,product,bot_username,status,created_at,container_id FROM clone_instances WHERE owner_id=$1 ORDER BY created_at DESC LIMIT 50",
        context.application.bot_data["owner_id"])
    statuses={}
    for row in rows:
        live=await context.application.bot_data["provisioner"].status(row["container_id"]) if row["container_id"] else "unknown"
        statuses[row["clone_id"]]=live
        if live!=row["status"]:
            await db.require().execute("UPDATE clone_instances SET status=$1,updated_at=NOW() WHERE clone_id=$2",live,row["clone_id"])
    running=sum(status=="running" for status in statuses.values())
    stopped=sum(status=="stopped" for status in statuses.values())
    body=f"(Quote start) ʏᴏᴜʀ ᴄʟᴏɴᴇ ᴅᴀsʜʙᴏᴀʀᴅ ♡\\n\\nᴛᴏᴛᴀʟ: {len(rows)} · ʀᴜɴɴɪɴɢ: {running} · sᴛᴏᴘᴘᴇᴅ: {stopped} (Quote end)"
    bot_buttons=[]
    for row in rows:
        status=statuses[row["clone_id"]]
        icon="🟢" if status=="running" else "🔴" if status=="stopped" else "⚪"
        bot_buttons.append(InlineKeyboardButton(f"{icon} @{row['bot_username']}",callback_data=f"clone:detail:{row['clone_id']}"))
    keyboard=[bot_buttons[i:i+2] for i in range(0,len(bot_buttons),2)]
    keyboard.append([InlineKeyboardButton("· ʙᴀᴄᴋ ·",callback_data="admin:back")])
    await _send(update,context,body,InlineKeyboardMarkup(keyboard) if rows else None)

async def clone_detail_callback(update,context):
    q=update.callback_query
    if not _allowed(q.from_user.id,context):
        await q.answer("Owner / Admin only.",show_alert=True); return
    await q.answer()
    clone_id=q.data.split(":",2)[2]
    row=await context.application.bot_data["db"].require().fetchrow(
        "SELECT * FROM clone_instances WHERE clone_id=$1 AND owner_id=$2",clone_id,context.application.bot_data["owner_id"])
    if not row:
        await _send(update,context,"ᴄʟᴏɴᴇ ɴᴏᴛ ғᴏᴜɴᴅ."); return
    icon="🟢" if row["status"]=="running" else "🔴" if row["status"]=="stopped" else "⚪"
    body=f"(Quote start) ᴄʟᴏɴᴇ ɪɴғᴏʀᴍᴀᴛɪᴏɴ ♡ (Quote end)\n\nɴᴀᴍᴇ: @{row['bot_username']}\nɪᴅ: {row['clone_id']}\nᴛʏᴘᴇ: {row['product']}\nsᴛᴀᴛᴜs: {icon} {row['status']}\nᴄʀᴇᴀᴛᴇᴅ: {row['created_at']}\nʙᴏᴛ ɪᴅ: {row['bot_id']}\nᴄᴏɴᴛᴀɪɴᴇʀ: {row['container_id'] or 'not assigned'}\nʟᴀsᴛ ᴇʀʀᴏʀ: {row['error_code'] or 'none'}"
    markup=InlineKeyboardMarkup([[InlineKeyboardButton("· sᴛᴏᴘ ·",callback_data=f"clone:stop:{clone_id}"),InlineKeyboardButton("· ʀᴇsᴛᴀʀᴛ ·",callback_data=f"clone:restart:{clone_id}")]])
    await _send(update,context,body,markup)

async def clone_manage_callback(update,context):
    q=update.callback_query
    if not _allowed(q.from_user.id,context):
        await q.answer("Owner / Admin only.",show_alert=True); return
    await q.answer()
    _,action,clone_id=q.data.split(":",2)
    db=context.application.bot_data["db"]
    row=await db.require().fetchrow("SELECT * FROM clone_instances WHERE clone_id=$1 AND owner_id=$2",clone_id,context.application.bot_data["owner_id"])
    if not row:
        await _send(update,context,"ᴄʟᴏɴᴇ ɴᴏᴛ ғᴏᴜɴᴅ."); return
    if action in {"stop","restart"}:
        verb="sᴛᴏᴘ" if action=="stop" else "ʀᴇsᴛᴀʀᴛ"
        markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"· ʏᴇs, {verb} ·",callback_data=f"clone:confirm-{action}:{clone_id}"),InlineKeyboardButton("· ᴄᴀɴᴄᴇʟ ·",callback_data="admin:back")]])
        await _send(update,context,f"(Quote start) ᴀʀᴇ ʏᴏᴜ sᴜʀᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ {verb} @{row['bot_username']}? (Quote end)",markup)
        return
    if action.startswith("confirm-"):
        operation=action.split("-",1)[1]
        if operation=="stop":
            await context.application.bot_data["provisioner"].stop(row["container_id"]); status="stopped"
        else:
            await context.application.bot_data["provisioner"].restart(row["container_id"]); status="running"
        await db.require().execute("UPDATE clone_instances SET status=$1,updated_at=NOW() WHERE clone_id=$2",status,clone_id)
        await _send(update,context,f"ᴄʟᴏɴᴇ @{row['bot_username']} ɪs ɴᴏᴡ {status.upper()}.")

async def _clone_action_menu(update,context,action):
    if not _allowed(update.effective_user.id,context):
        await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ."); return
    rows=await context.application.bot_data["db"].require().fetch(
        "SELECT clone_id,bot_username,status FROM clone_instances WHERE owner_id=$1 ORDER BY created_at DESC LIMIT 100",context.application.bot_data["owner_id"])
    if not rows:
        await _send(update,context,"ɴᴏ ᴄʟᴏɴᴇs ᴀʀᴇ ʀᴇɢɪsᴛᴇʀᴇᴅ ʏᴇᴛ."); return
    buttons=[InlineKeyboardButton(("🟢 " if row["status"]=="running" else "🔴 " if row["status"]=="stopped" else "⚪ ")+f"@{row['bot_username']}",callback_data=f"clone:{action}:{row['clone_id']}") for row in rows]
    keyboard=[buttons[i:i+2] for i in range(0,len(buttons),2)]
    keyboard.append([InlineKeyboardButton("· ʙᴀᴄᴋ ·",callback_data="admin:back"),InlineKeyboardButton("· ᴄʟᴏsᴇ ·",callback_data="branding:close")])
    label="sᴛᴏᴘ" if action=="stop" else "ʀᴇsᴛᴀʀᴛ"
    await _send(update,context,f"(Quote start) ᴄʜᴏᴏsᴇ ᴛʜᴇ ʙᴏᴛ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ {label}, sᴇɴᴘᴀɪ! (Quote end)",InlineKeyboardMarkup(keyboard))

async def stopclone(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context): return await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ.")
    if not context.args: return await _clone_action_menu(update,context,"stop")
    else:
        row=await context.application.bot_data["db"].require().fetchrow("SELECT owner_id,container_id FROM clone_instances WHERE clone_id=$1",context.args[0])
        if not row or row["owner_id"]!=context.application.bot_data["owner_id"]: body="Clone not found or not owned by you."
        else:
            await context.application.bot_data["provisioner"].stop(row["container_id"])
            await context.application.bot_data["db"].require().execute("UPDATE clone_instances SET status='stopped',updated_at=NOW() WHERE clone_id=$1",context.args[0]); body="Clone stopped."
    await _send(update,context,body)

async def restartclone(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context): return await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ.")
    if not context.args: return await _clone_action_menu(update,context,"restart")
    else:
        row=await context.application.bot_data["db"].require().fetchrow("SELECT owner_id,container_id FROM clone_instances WHERE clone_id=$1",context.args[0])
        if not row or row["owner_id"]!=update.effective_user.id: body="Clone not found or not owned by you."
        else:
            await context.application.bot_data["provisioner"].restart(row["container_id"])
            await context.application.bot_data["db"].require().execute("UPDATE clone_instances SET status='running',updated_at=NOW() WHERE clone_id=$1",context.args[0]); body="Clone restarted."
    await _send(update,context,body)



async def cloneinfo(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context):
        await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ.")
        return
    if not context.args:
        rows=await context.application.bot_data["db"].require().fetch(
            "SELECT clone_id,bot_username,status FROM clone_instances WHERE owner_id=$1 ORDER BY created_at DESC LIMIT 50",
            update.effective_user.id)
        if not rows:
            await _send(update,context,"ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴄʀᴇᴀᴛᴇᴅ ᴀɴʏ ᴄʟᴏɴᴇs ʏᴇᴛ.")
            return
        body="(Quote start) ᴄʜᴏᴏsᴇ ᴀ ᴄʟᴏɴᴇ ᴛᴏ ᴠɪᴇᴡ ɪᴛs ᴅᴇᴛᴀɪʟs! 🎀 (Quote end)\n\n"
        body+="\n".join(("🟢 " if row["status"]=="running" else "🔴 " if row["status"]=="stopped" else "⚪ ")+f"@{row['bot_username']} — /cloneinfo {row['clone_id']}" for row in rows)
    else:
        row=await context.application.bot_data["db"].require().fetchrow(
            "SELECT * FROM clone_instances WHERE clone_id=$1 AND owner_id=$2",context.args[0],context.application.bot_data["owner_id"])
        if not row:
            body="ᴄʟᴏɴᴇ ɴᴏᴛ ғᴏᴜɴᴅ."
        else:
            status="🟢 ʀᴜɴɴɪɴɢ" if row["status"]=="running" else "🔴 sᴛᴏᴘᴘᴇᴅ" if row["status"]=="stopped" else "⚪ "+str(row["status"]).upper()
            body=f"(Quote start) ᴄʟᴏɴᴇ ɪɴғᴏʀᴍᴀᴛɪᴏɴ ♡ (Quote end)\n\nɴᴀᴍᴇ: @{row['bot_username']}\nɪᴅ: {row['clone_id']}\nᴛʏᴘᴇ: {row['product']}\nsᴛᴀᴛᴜs: {status}\nᴄʀᴇᴀᴛᴇᴅ: {row['created_at']}\nʙᴏᴛ ɪᴅ: {row['bot_id']}\nᴄᴏɴᴛᴀɪɴᴇʀ: {row['container_id'] or 'not assigned'}\nʟᴀsᴛ ᴇʀʀᴏʀ: {row['error_code'] or 'none'}"
    await _send(update,context,body)

async def cloneedit(update:Update,context:ContextTypes.DEFAULT_TYPE):
    """Platform-owner remote message override for an existing clone."""
    if not _allowed(update.effective_user.id,context):
        await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ.")
        return
    if len(context.args)!=2:
        body="Usage: `/cloneedit CLONE_ID TEMPLATE_KEY`"
    else:
        clone_id,key=context.args
        if not (key.startswith("file.") or key.startswith("link.")):
            body="Template key must start with file. or link."
        else:
            exists=await context.application.bot_data["db"].require().fetchrow("SELECT clone_id FROM clone_instances WHERE clone_id=$1",clone_id)
            if not exists: body="Clone ID not found."
            else:
                context.user_data["editing_text_key"]=key
                context.user_data["editing_clone_id"]=clone_id
                body=f"Send the replacement message for `{clone_id}` / `{key}` now. This writes a clone-specific override."
    await _send(update,context,body)

async def clonepreview(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context):
        await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ.")
        return
    if len(context.args)!=2: body="Usage: `/clonepreview CLONE_ID TEMPLATE_KEY`"
    else:
        clone_id,key=context.args
        row=await context.application.bot_data["db"].require().fetchrow("SELECT clone_id FROM clone_instances WHERE clone_id=$1",clone_id)
        if not row: body="Clone ID not found."
        else:
            value=await context.application.bot_data["db"].get_text(clone_id,key,f"(B)No custom override for {key}(/B)")
            rows=await context.application.bot_data["db"].get_buttons(clone_id,key)
            markup=keyboard_from_buttons(rows,small_caps=context.application.bot_data["small_caps"])
            await send_branded(context.bot,update.effective_chat.id,value,
                image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
                small_caps=context.application.bot_data["small_caps"],reply_markup=markup)
            return
    await _send(update,context,body)

async def clonebuttonadd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != context.application.bot_data["owner_id"]: return
    raw=update.effective_message.text.partition(" ")[2]
    parts=[x.strip() for x in raw.split("|",3)]
    if len(parts)!=4: body="Usage: `/clonebuttonadd CLONE_ID | TEMPLATE_KEY | LABEL | HTTPS_URL`"
    else:
        clone_id,key,label,url=parts
        if not url.startswith(("https://","http://")): body="Only HTTP(S) button URLs are accepted."
        else:
            exists=await context.application.bot_data["db"].require().fetchrow("SELECT clone_id FROM clone_instances WHERE clone_id=$1",clone_id)
            if not exists: body="Clone ID not found."
            else:
                rows=await context.application.bot_data["db"].get_buttons(clone_id,key); rows.append([{"text":label[:64],"url":url}])
                await context.application.bot_data["db"].set_buttons(clone_id,key,rows); body="Clone button added."
    await _send(update,context,body)

async def clonebuttonedit(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != context.application.bot_data["owner_id"]: return
    raw=update.effective_message.text.partition(" ")[2]
    parts=[x.strip() for x in raw.split("|",4)]
    if len(parts)!=5: body="Usage: `/clonebuttonedit CLONE_ID | TEMPLATE_KEY | INDEX | LABEL | HTTPS_URL`"
    else:
        clone_id,key,index_text,label,url=parts
        try: index=int(index_text)-1
        except ValueError: index=-1
        if index<0 or not url.startswith(("https://","http://")): body="Invalid index or URL."
        else:
            rows=await context.application.bot_data["db"].get_buttons(clone_id,key); flat=[b for row in rows for b in row]
            if index>=len(flat): body="Button index not found."
            else:
                flat[index]={"text":label[:64],"url":url}
                await context.application.bot_data["db"].set_buttons(clone_id,key,[[b] for b in flat]); body="Clone button updated."
    await _send(update,context,body)

async def clonebuttondel(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != context.application.bot_data["owner_id"]: return
    raw=update.effective_message.text.partition(" ")[2]
    parts=[x.strip() for x in raw.split("|",2)]
    if len(parts)!=3: body="Usage: `/clonebuttondel CLONE_ID | TEMPLATE_KEY | INDEX`"
    else:
        clone_id,key,index_text=parts
        try: index=int(index_text)-1
        except ValueError: index=-1
        rows=await context.application.bot_data["db"].get_buttons(clone_id,key); flat=[b for row in rows for b in row]
        if index<0 or index>=len(flat): body="Button index not found."
        else:
            del flat[index]; await context.application.bot_data["db"].set_buttons(clone_id,key,[[b] for b in flat]); body="Clone button removed."
    await _send(update,context,body)

def add_clone_handlers(app):
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("clone",clone))
    app.add_handler(CommandHandler("clones",clones))
    app.add_handler(CommandHandler("stopclone",stopclone))
    app.add_handler(CommandHandler("restartclone",restartclone))
    app.add_handler(CommandHandler("cloneedit",cloneedit))
    app.add_handler(CommandHandler("cloneinfo",cloneinfo))
    app.add_handler(CallbackQueryHandler(select_product,pattern=r"^clone:select:(file|link)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,receive_token),group=-2)
