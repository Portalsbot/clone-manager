from __future__ import annotations
import asyncio, logging, secrets, re, json
from pathlib import Path
from cryptography.fernet import Fernet
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from ..branding import send_branded, keyboard_from_buttons
from ..provisioner import RenderProvisioner

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
    globally_blocked=await db.require().fetchval(
        "SELECT EXISTS(SELECT 1 FROM bot_user_blocks WHERE user_id=$1)", user_id
    )
    existing=await db.require().fetchrow("SELECT is_banned FROM bot_users WHERE clone_id=$1 AND user_id=$2",clone_id,user_id)
    if globally_blocked or (existing and existing["is_banned"]):
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
    for state in ("pending_clone_edit","pending_clone_product","editing_text_key","editing_clone_id",
                  "pending_setting","pending_text_editor","awaiting_text_draft","user_action",
                  "broadcast_mode","pending_broadcast","awaiting_broadcast_time"):
        context.user_data.pop(state,None)
    if not _allowed(update.effective_user.id,context):
        await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ.")
        return
    markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("ғɪʟᴇ sʜᴀʀɪɴɢ ʙᴏᴛ",callback_data="clone:select:file")],
        [InlineKeyboardButton("ʟɪɴᴋ sʜᴀʀɪɴɢ ʙᴏᴛ",callback_data="clone:select:link")],
    ])
    body=await context.application.bot_data["db"].get_text(context.application.bot_data["clone_id"],"cloner.select",context.application.bot_data["defaults"]["cloner.select"])
    await _send(update,context,body,markup)

async def select_product(update:Update,context:ContextTypes.DEFAULT_TYPE):
    query=update.callback_query; await query.answer()
    if not _allowed(query.from_user.id,context): return
    product=query.data.rsplit(":",1)[-1]
    if product not in {"file","link"}: return
    context.user_data["pending_clone_product"]=product
    token_prompt=await context.application.bot_data["db"].get_text(context.application.bot_data["clone_id"],"cloner.token",context.application.bot_data["defaults"]["cloner.token"])
    await send_branded(context.bot,query.message.chat_id,
        token_prompt,
        image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
        small_caps=context.application.bot_data["small_caps"],
        footer_message=await context.application.bot_data["db"].get_setting("branding.footer",""))

async def receive_token(update:Update,context:ContextTypes.DEFAULT_TYPE):
    pending_edit=context.user_data.get("pending_clone_edit")
    if pending_edit:
        await _capture_clone_edit(update,context,pending_edit)
        from telegram.ext import ApplicationHandlerStop
        raise ApplicationHandlerStop
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
    owner_id=context.application.bot_data["owner_id"]
    provisioner=context.application.bot_data["provisioner"]
    repo_url=provisioner.repository_for(product)
    image_ref=provisioner.image_for(product)
    managed_environment={}
    if product=="link":
        managed_environment["SHORTENER_ENCRYPTION_KEY"]=Fernet.generate_key().decode("ascii")
    encrypted_environment=(
        cipher.encrypt(json.dumps(managed_environment).encode()).decode()
        if managed_environment else None
    )
    await db.require().execute(
        """INSERT INTO clone_instances(
            clone_id,owner_id,product,bot_id,bot_username,bot_name,repository_url,image_ref,
            hosting_provider,encrypted_token,encrypted_environment,status
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,'render',$9,$10,'provisioning')""",
        clone_id,owner_id,product,me.id,me.username or str(me.id),me.first_name,
        repo_url,image_ref,encrypted,encrypted_environment)
    try:
        render_service_id=await provisioner.create(
            product,clone_id,token,owner_id,image_ref=image_ref,
            extra_environment=managed_environment,
        )
        await db.require().execute("UPDATE clone_instances SET render_service_id=$1,status='provisioning',updated_at=NOW() WHERE clone_id=$2",render_service_id,clone_id)
        success_template=await db.get_text(context.application.bot_data["clone_id"],"cloner.success",context.application.bot_data["defaults"]["cloner.success"])
        await _send(update,context,success_template.format(username=me.username or me.id,product=product.title(),clone_id=clone_id))
    except Exception as exc:
        log.exception("Clone provisioning failed (%s)",type(exc).__name__)
        await db.require().execute("UPDATE clone_instances SET status='failed',error_code=$1,updated_at=NOW() WHERE clone_id=$2",type(exc).__name__,clone_id)
        await _send(update,context,f"ᴛᴏᴋᴇɴ ᴠᴀʟɪᴅᴀᴛᴇᴅ ғᴏʀ @{me.username}, ʙᴜᴛ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ғᴀɪʟᴇᴅ. ᴇʀʀᴏʀ: {type(exc).__name__}. ᴄᴏɴᴛᴀᴄᴛ ᴘʟᴀᴛғᴏʀᴍ ᴏᴡɴᴇʀ.")

async def _live_clone_rows(context, filter_key="all"):
    db=context.application.bot_data["db"]
    rows=await db.require().fetch(
        "SELECT clone_id,product,bot_username,status,created_at,render_service_id FROM clone_instances WHERE owner_id=$1 ORDER BY created_at DESC",
        context.application.bot_data["owner_id"])
    live_rows=[]
    for row in rows:
        if row["render_service_id"]:
            status=await context.application.bot_data["provisioner"].status(row["render_service_id"])
        else:
            status=row["status"] if row["status"] in {"failed","provisioning"} else "unknown"
        if status!=row["status"]:
            await db.require().execute("UPDATE clone_instances SET status=$1,updated_at=NOW() WHERE clone_id=$2",status,row["clone_id"])
        item=dict(row)
        item["status"]=status
        live_rows.append(item)
    if filter_key in {"running","stopped"}:
        live_rows=[r for r in live_rows if r["status"]==filter_key]
    elif filter_key in {"file","link"}:
        live_rows=[r for r in live_rows if r["product"]==filter_key]
    elif filter_key=="recent":
        live_rows=live_rows[:10]
    return live_rows

async def clones(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context):
        await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ.")
        return
    rows=await _live_clone_rows(context)
    running=sum(r["status"]=="running" for r in rows)
    stopped=sum(r["status"]=="stopped" for r in rows)
    body=(f"(Quote start) ᴇʜᴇ~! ʜᴇʀᴇ ɪs ʏᴏᴜʀ ʟɪᴛᴛʟᴇ ᴄʟᴏɴᴇ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ ᴄᴇɴᴛᴇʀ, sᴇɴᴘᴀɪ! ♡\\n\\n"
          f"ᴛᴏᴛᴀʟ: {len(rows)} · 🟢 ʀᴜɴɴɪɴɢ: {running} · 🔴 sᴛᴏᴘᴘᴇᴅ: {stopped}\\n"
          "ᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ ᴛᴏ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ᴄʟᴏɴᴇs. (Quote end)")
    markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("· ᴀʟʟ ᴄʟᴏɴᴇs ·",callback_data="clones:all"),InlineKeyboardButton("· ʀᴜɴɴɪɴɢ ·",callback_data="clones:running")],
        [InlineKeyboardButton("· sᴛᴏᴘᴘᴇᴅ ·",callback_data="clones:stopped"),InlineKeyboardButton("· ʀᴇᴄᴇɴᴛ ᴄʟᴏɴᴇs ·",callback_data="clones:recent")],
        [InlineKeyboardButton("· ꜰɪʟᴇ ʙᴏᴛs ·",callback_data="clones:file"),InlineKeyboardButton("· ʟɪɴᴋ ʙᴏᴛs ·",callback_data="clones:link")],
        [InlineKeyboardButton("· ʀᴇғʀᴇsʜ ·",callback_data="clones:refresh"),InlineKeyboardButton("· ʙᴀᴄᴋ ·",callback_data="admin:back")],
    ])
    await _send(update,context,body,markup)

async def clones_filter_callback(update,context):
    q=update.callback_query
    if not _allowed(q.from_user.id,context):
        await q.answer("Owner / Admin only.",show_alert=True); return
    await q.answer()
    action=q.data.split(":",1)[1]
    filter_key="all" if action=="refresh" else action
    rows=await _live_clone_rows(context,filter_key)
    all_rows=await _live_clone_rows(context,"all")
    running=sum(r["status"]=="running" for r in all_rows)
    stopped=sum(r["status"]=="stopped" for r in all_rows)
    title={"all":"ᴀʟʟ ᴄʟᴏɴᴇs","running":"ʀᴜɴɴɪɴɢ ᴄʟᴏɴᴇs","stopped":"sᴛᴏᴘᴘᴇᴅ ᴄʟᴏɴᴇs","recent":"ʀᴇᴄᴇɴᴛ ᴄʟᴏɴᴇs","file":"ꜰɪʟᴇ sʜᴀʀɪɴɢ ʙᴏᴛs","link":"ʟɪɴᴋ sʜᴀʀɪɴɢ ʙᴏᴛs"}.get(filter_key,"ᴀʟʟ ᴄʟᴏɴᴇs")
    body=f"(Quote start) {title}\\nᴛᴏᴛᴀʟ: {len(all_rows)} · 🟢 ʀᴜɴɴɪɴɢ: {running} · 🔴 sᴛᴏᴘᴘᴇᴅ: {stopped} (Quote end)"
    buttons=[]
    for row in rows:
        icon="🟢" if row["status"]=="running" else "🔴" if row["status"]=="stopped" else "⚪"
        buttons.append(InlineKeyboardButton(f"{icon} @{row['bot_username']}",callback_data=f"clone:detail:{row['clone_id']}"))
    keyboard=[buttons[i:i+2] for i in range(0,len(buttons),2)]
    keyboard.extend([
        [InlineKeyboardButton("· ᴀʟʟ ·",callback_data="clones:all"),InlineKeyboardButton("· ʀᴜɴɴɪɴɢ ·",callback_data="clones:running")],
        [InlineKeyboardButton("· sᴛᴏᴘᴘᴇᴅ ·",callback_data="clones:stopped"),InlineKeyboardButton("· ʀᴇғʀᴇsʜ ·",callback_data="clones:refresh")],
        [InlineKeyboardButton("· ʙᴀᴄᴋ ·",callback_data="admin:back")],
    ])
    await _send(update,context,body,InlineKeyboardMarkup(keyboard))

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
    body=f"(Quote start) ᴄʟᴏɴᴇ ɪɴғᴏʀᴍᴀᴛɪᴏɴ ♡ (Quote end)\n\nɴᴀᴍᴇ: @{row['bot_username']}\nɪᴅ: {row['clone_id']}\nᴛʏᴘᴇ: {row['product']}\nsᴛᴀᴛᴜs: {icon} {row['status']}\nᴄʀᴇᴀᴛᴇᴅ: {row['created_at']}\nʙᴏᴛ ɪᴅ: {row['bot_id']}\nʀᴇɴᴅᴇʀ sᴇʀᴠɪᴄᴇ: {row['render_service_id'] or 'not assigned'}\nʟᴀsᴛ ᴇʀʀᴏʀ: {row['error_code'] or 'none'}"
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
        if not row["render_service_id"]:
            await _send(update,context,"ᴛʜɪs ᴄʟᴏɴᴇ ʜᴀs ɴᴏ ᴀᴄᴛɪᴠᴇ ʀᴇɴᴅᴇʀ sᴇʀᴠɪᴄᴇ.")
            return
        verb="sᴛᴏᴘ" if action=="stop" else "ʀᴇsᴛᴀʀᴛ"
        markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"· ʏᴇs, {verb} ·",callback_data=f"clone:confirm-{action}:{clone_id}"),InlineKeyboardButton("· ᴄᴀɴᴄᴇʟ ·",callback_data="admin:back")]])
        await _send(update,context,f"(Quote start) ᴀʀᴇ ʏᴏᴜ sᴜʀᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ {verb} @{row['bot_username']}? (Quote end)",markup)
        return
    if action.startswith("confirm-"):
        if not row["render_service_id"]:
            await _send(update,context,"ᴛʜɪs ᴄʟᴏɴᴇ ʜᴀs ɴᴏ ᴀᴄᴛɪᴠᴇ ʀᴇɴᴅᴇʀ sᴇʀᴠɪᴄᴇ.")
            return
        operation=action.split("-",1)[1]
        if operation=="stop":
            await context.application.bot_data["provisioner"].stop(row["render_service_id"]); status="stopped"
        else:
            await context.application.bot_data["provisioner"].restart(row["render_service_id"]); status="running"
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
    keyboard.append([InlineKeyboardButton("· ʙᴀᴄᴋ ·",callback_data="admin:back")])
    label="sᴛᴏᴘ" if action=="stop" else "ʀᴇsᴛᴀʀᴛ"
    await _send(update,context,f"(Quote start) ᴄʜᴏᴏsᴇ ᴛʜᴇ ʙᴏᴛ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ {label}, sᴇɴᴘᴀɪ! (Quote end)",InlineKeyboardMarkup(keyboard))

async def stopclone(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context): return await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ.")
    if not context.args: return await _clone_action_menu(update,context,"stop")
    else:
        row=await context.application.bot_data["db"].require().fetchrow("SELECT owner_id,render_service_id FROM clone_instances WHERE clone_id=$1",context.args[0])
        if not row or row["owner_id"]!=context.application.bot_data["owner_id"]: body="Clone not found or not owned by you."
        elif not row["render_service_id"]: body="This clone has no active Render service."
        else:
            await context.application.bot_data["provisioner"].stop(row["render_service_id"])
            await context.application.bot_data["db"].require().execute("UPDATE clone_instances SET status='stopped',updated_at=NOW() WHERE clone_id=$1",context.args[0]); body="Clone stopped."
    await _send(update,context,body)

async def restartclone(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context): return await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ.")
    if not context.args: return await _clone_action_menu(update,context,"restart")
    else:
        row=await context.application.bot_data["db"].require().fetchrow("SELECT owner_id,render_service_id FROM clone_instances WHERE clone_id=$1",context.args[0])
        if not row or row["owner_id"]!=context.application.bot_data["owner_id"]: body="Clone not found or not owned by you."
        elif not row["render_service_id"]: body="This clone has no active Render service."
        else:
            await context.application.bot_data["provisioner"].restart(row["render_service_id"])
            await context.application.bot_data["db"].require().execute("UPDATE clone_instances SET status='running',updated_at=NOW() WHERE clone_id=$1",context.args[0]); body="Clone restarted."
    await _send(update,context,body)



async def cloneinfo(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context):
        await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ.")
        return
    rows=await _live_clone_rows(context)
    if not rows:
        await _send(update,context,"ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴄʀᴇᴀᴛᴇᴅ ᴀɴʏ ᴄʟᴏɴᴇs ʏᴇᴛ."); return
    if context.args:
        clone_id=context.args[0]
        row=next((r for r in rows if r["clone_id"]==clone_id),None)
        if not row:
            await _send(update,context,"ᴄʟᴏɴᴇ ɴᴏᴛ ғᴏᴜɴᴅ."); return
        body=(f"(Quote start) ᴄʟᴏɴᴇ ɪɴғᴏʀᴍᴀᴛɪᴏɴ ♡ (Quote end)\\n\\n"
              f"ɴᴀᴍᴇ: @{row['bot_username']}\\nɪᴅ: {row['clone_id']}\\nᴛʏᴘᴇ: {row['product']}\\n"
              f"sᴛᴀᴛᴜs: {row['status']}\\nᴄʀᴇᴀᴛᴇᴅ: {row['created_at']}\\nʙᴏᴛ ɪᴅ: {row['bot_id']}\\n"
              f"ʀᴇɴᴅᴇʀ sᴇʀᴠɪᴄᴇ: {row['render_service_id'] or 'not assigned'}\\nʟᴀsᴛ ᴇʀʀᴏʀ: {row['error_code'] or 'none'}")
        await _send(update,context,body,InlineKeyboardMarkup([[
            InlineKeyboardButton("· sᴛᴏᴘ ·",callback_data=f"clone:stop:{clone_id}"),
            InlineKeyboardButton("· ʀᴇsᴛᴀʀᴛ ·",callback_data=f"clone:restart:{clone_id}")
        ]]))
        return
    buttons=[]
    for row in rows:
        icon="🟢" if row["status"]=="running" else "🔴" if row["status"]=="stopped" else "⚪"
        buttons.append(InlineKeyboardButton(f"{icon} @{row['bot_username']}",callback_data=f"clone:detail:{row['clone_id']}"))
    keyboard=[buttons[i:i+2] for i in range(0,len(buttons),2)]
    keyboard.append([InlineKeyboardButton("· ʙᴀᴄᴋ ·",callback_data="admin:back")])
    await _send(update,context,"(Quote start) ᴏᴏʜ~! ᴡᴀɴᴛ ᴛᴏ ᴋɴᴏᴡ ᴇᴠᴇʀʏᴛʜɪɴɢ ᴀʙᴏᴜᴛ ᴏɴᴇ ᴏғ ʏᴏᴜʀ ʟɪᴛᴛʟᴇ ʙᴏᴛs, sᴇɴᴘᴀɪ? 🎀\\n\\nᴄʜᴏᴏsᴇ ᴀ ᴄʟᴏɴᴇ ᴀɴᴅ ɪ'ʟʟ sʜᴏᴡ ʏᴏᴜ ɪᴛs ᴅᴇᴛᴀɪʟs! ♡ (Quote end)",InlineKeyboardMarkup(keyboard))

async def clonedit(update:Update,context:ContextTypes.DEFAULT_TYPE):
    for state in ("pending_clone_edit","pending_clone_product","editing_text_key","editing_clone_id",
                  "pending_setting","pending_text_editor","awaiting_text_draft","user_action",
                  "broadcast_mode","pending_broadcast","awaiting_broadcast_time"):
        context.user_data.pop(state,None)
    if not _allowed(update.effective_user.id,context):
        await _send(update,context,"ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ / ᴀᴅᴍɪɴ."); return
    db=context.application.bot_data["db"]
    if context.args:
        row=await db.require().fetchrow("SELECT * FROM clone_instances WHERE clone_id=$1 AND owner_id=$2",context.args[0],context.application.bot_data["owner_id"])
        if not row: await _send(update,context,"ᴄʟᴏɴᴇ ɴᴏᴛ ғᴏᴜɴᴅ."); return
        await _show_clone_edit_menu(update,context,row); return
    rows=await _live_clone_rows(context)
    if not rows: await _send(update,context,"ɴᴏ ᴄʟᴏɴᴇs ᴀʀᴇ ᴀᴠᴀɪʟᴀʙʟᴇ ᴛᴏ ᴇᴅɪᴛ."); return
    buttons=[InlineKeyboardButton(("🟢 " if r["status"]=="running" else "🔴 " if r["status"]=="stopped" else "⚪ ")+f"@{r['bot_username']}",callback_data=f"clone:edit:{r['clone_id']}") for r in rows]
    keyboard=[buttons[i:i+2] for i in range(0,len(buttons),2)]
    keyboard.append([InlineKeyboardButton("· ʙᴀᴄᴋ ·",callback_data="admin:back")])
    await _send(update,context,"(Quote start) ᴄʜᴏᴏsᴇ ᴀ ᴄʟᴏɴᴇ ᴛᴏ ᴇᴅɪᴛ ɪᴛs ᴄᴏɴғɪɢᴜʀᴀᴛɪᴏɴ, sᴇɴᴘᴀɪ! 🎀 (Quote end)",InlineKeyboardMarkup(keyboard))


async def _show_clone_edit_menu(update,context,row):
    clone_id=row["clone_id"]
    count=0
    if row["encrypted_environment"]:
        try: count=len(json.loads(Fernet(context.application.bot_data["encryption_key"]).decrypt(row["encrypted_environment"].encode()).decode()))
        except Exception: count=-1
    body=(f"(Quote start) ᴄʟᴏɴᴇ ᴄᴏɴғɪɢᴜʀᴀᴛɪᴏɴ · @{row['bot_username']} (Quote end)\n\n"
          f"ɪᴅ: {clone_id}\nɴᴀᴍᴇ: {row['bot_name'] or 'not customised'}\n"
          f"ʀᴇᴘᴏsɪᴛᴏʀʏ: {row['repository_url'] or row['image_ref'] or 'product default'}\n"
          f"ʜᴏsᴛɪɴɢ: Render Background Worker\n"
          f"ᴄᴜsᴛᴏᴍ ᴇɴᴠ ᴠᴀʀs: {'unreadable' if count<0 else count}\n"
          f"ʀᴇɢɪᴏɴ: {row['render_region'] or 'workspace default'}\n"
          f"ᴘʟᴀɴ: {row['render_plan'] or 'workspace default'}")
    markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("· ʙᴏᴛ ɴᴀᴍᴇ ·",callback_data=f"clone:editfield:{clone_id}:name"),InlineKeyboardButton("· ʙᴏᴛ ᴛᴏᴋᴇɴ ·",callback_data=f"clone:editfield:{clone_id}:token")],
        [InlineKeyboardButton("· ʀᴇᴘᴏsɪᴛᴏʀʏ ·",callback_data=f"clone:editfield:{clone_id}:repository"),InlineKeyboardButton("· ʀᴇɴᴅᴇʀ ᴘʟᴀɴ ·",callback_data=f"clone:editfield:{clone_id}:hosting")],
        [InlineKeyboardButton("· ᴇɴᴠɪʀᴏɴᴍᴇɴᴛ ·",callback_data=f"clone:editfield:{clone_id}:environment"),InlineKeyboardButton("· ᴍᴇssᴀɢᴇs ·",callback_data=f"clone:editfield:{clone_id}:messages")],
        [InlineKeyboardButton("· ᴅᴇᴘʟᴏʏ ᴀɢᴀɪɴ ·",callback_data=f"clone:deploy:{clone_id}"),InlineKeyboardButton("· ʙᴀᴄᴋ ·",callback_data="admin:back")]
    ])
    await _send(update,context,body,markup)


def _parse_environment(text:str)->dict[str,str]:
    protected={"BOT_TOKEN","DATABASE_URL","OWNER_ID","ADMINS","CLONE_ID","CONFIG_FILE","BRANDING_IMAGE_URL","BRANDING_IMAGE_PATH","SHORTENER_ENCRYPTION_KEY"}
    result={}
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith("#"): continue
        if "=" not in line: raise ValueError("ᴜsᴇ KEY=VALUE, ᴏɴᴇ ᴠᴀʀɪᴀʙʟᴇ ᴘᴇʀ ʟɪɴᴇ.")
        key,value=line.split("=",1); key=key.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}",key) or key in protected: raise ValueError(f"ɪɴᴠᴀʟɪᴅ ᴏʀ ʀᴇsᴇʀᴠᴇᴅ ᴋᴇʏ: {key}")
        if len(value)>4000: raise ValueError(f"ᴠᴀʟᴜᴇ ғᴏʀ {key} ɪs ᴛᴏᴏ ʟᴏɴɢ.")
        result[key]=value
    if len(result)>100: raise ValueError("ᴍᴀxɪᴍᴜᴍ 100 ᴄᴜsᴛᴏᴍ ᴠᴀʀɪᴀʙʟᴇs ᴀʀᴇ ᴀʟʟᴏᴡᴇᴅ.")
    return result


def _parse_repository(value:str,product:str)->tuple[str|None,str]:
    from urllib.parse import urlparse
    value=value.strip(); parsed=urlparse(value)
    if parsed.scheme in {"http","https"} and parsed.netloc.lower() in {"github.com","www.github.com"}:
        parts=[p for p in parsed.path.strip("/").split("/") if p]
        if len(parts)<2: raise ValueError("sᴇɴᴅ ᴀ GɪᴛHᴜʙ ʀᴇᴘᴏsɪᴛᴏʀʏ URL ᴡɪᴛʜ ᴏᴡɴᴇʀ ᴀɴᴅ ʀᴇᴘᴏsɪᴛᴏʀʏ.")
        owner,repo=parts[:2]; repo=repo.removesuffix(".git")
        canonical=f"https://github.com/{owner}/{repo}"
        known={
            ("portalsbot","file-share-bot"):("file","ghcr.io/portalsbot/file-share-bot:latest"),
            ("portalsbot","link-sharing-bot"):("link","ghcr.io/portalsbot/link-sharing-bot:latest"),
        }
        mapped=known.get((owner.lower(),repo.lower()))
        if mapped and mapped[0]!=product:
            raise ValueError("ᴛʜɪs ʀᴇᴘᴏsɪᴛᴏʀʏ ʙᴇʟᴏɴɢs ᴛᴏ ᴛʜᴇ ᴏᴛʜᴇʀ ʙᴏᴛ ᴘʀᴏᴅᴜᴄᴛ.")
        image=mapped[1] if mapped else f"ghcr.io/{owner.lower()}/{repo.lower()}:latest"
        return canonical,image
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{1,254}",value) or "://" in value:
        raise ValueError("sᴇɴᴅ ᴀ GɪᴛHᴜʙ ʀᴇᴘᴏ URL ᴏʀ GHCR ɪᴍᴀɢᴇ ʀᴇғᴇʀᴇɴᴄᴇ.")
    return None,value


async def _start_clone_edit(update,context,clone_id,field):
    for state in ("pending_setting","pending_text_editor","awaiting_text_draft","user_action",
                  "broadcast_mode","pending_broadcast","awaiting_broadcast_time","pending_clone_product",
                  "editing_text_key","editing_clone_id"):
        context.user_data.pop(state,None)
    db=context.application.bot_data["db"]
    row=await db.require().fetchrow("SELECT * FROM clone_instances WHERE clone_id=$1 AND owner_id=$2",clone_id,context.application.bot_data["owner_id"])
    if not row: await _send(update,context,"ᴄʟᴏɴᴇ ɴᴏᴛ ғᴏᴜɴᴅ."); return
    if field=="messages":
        product=row["product"]; keys=[f"{product}.start",f"{product}.about",f"{product}.help"]
        markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("· ᴇᴅɪᴛ sᴛᴀʀᴛ ·",callback_data=f"clone:editkey:{clone_id}:{keys[0]}"),InlineKeyboardButton("· ᴇᴅɪᴛ ᴀʙᴏᴜᴛ ·",callback_data=f"clone:editkey:{clone_id}:{keys[1]}")],
            [InlineKeyboardButton("· ᴇᴅɪᴛ ʜᴇʟᴘ ·",callback_data=f"clone:editkey:{clone_id}:{keys[2]}")],
            [InlineKeyboardButton("· ʙᴀᴄᴋ ·",callback_data=f"clone:edit:{clone_id}")]
        ])
        await _send(update,context,f"(Quote start) ᴍᴇssᴀɢᴇ ᴇᴅɪᴛᴏʀ ғᴏʀ @{row['bot_username']} (Quote end)",markup); return
    if field not in {"name","token","repository","hosting","environment"}:
        await _send(update,context,"ᴜɴᴋɴᴏᴡɴ ᴄᴏɴғɪɢᴜʀᴀᴛɪᴏɴ ғɪᴇʟᴅ."); return
    context.user_data["pending_clone_edit"]={"clone_id":clone_id,"field":field}
    prompts={
      "name":"sᴇɴᴅ ᴛʜᴇ ɴᴇᴡ ᴅɪsᴘʟᴀʏ ɴᴀᴍᴇ (ᴍᴀx 64 ᴄʜᴀʀᴀᴄᴛᴇʀs).",
      "token":"sᴇɴᴅ ᴛʜᴇ ɴᴇᴡ ʙᴏᴛғᴀᴛʜᴇʀ ᴛᴏᴋᴇɴ ғᴏʀ ᴛʜᴇ sᴀᴍᴇ ʙᴏᴛ. ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ.",
      "repository":"sᴇɴᴅ ᴛʜᴇ ᴘʀɪᴠᴀᴛᴇ GɪᴛHᴜʙ ʀᴇᴘᴏsɪᴛᴏʀʏ URL ғᴏʀ ᴛʜɪs ᴘʀᴏᴅᴜᴄᴛ. Tʜᴇ ᴘʀᴏᴅᴜᴄᴛ's ᴅᴇғᴀᴜʟᴛ ᴘᴀᴄᴋᴀɢᴇ ɪs ᴍᴀᴘᴘᴇᴅ ᴛᴏ ɪᴛs ᴄᴏʀʀᴇᴄᴛ GHCR ɪᴍᴀɢᴇ.",
      "hosting":"sᴇɴᴅ plan=starter ᴛᴏ ᴄʜᴀɴɢᴇ ᴛʜᴇ ᴄᴏᴍᴘᴜᴛᴇ ᴘʟᴀɴ. Tʜᴇ ʀᴇɢɪᴏɴ ɪs sᴇᴛ ʙʏ RENDER_REGION ɪɴ ᴛʜᴇ ᴍᴀɴᴀɢᴇʀ's ᴇɴᴠɪʀᴏɴᴍᴇɴᴛ.",
      "environment":"sᴇɴᴅ ᴄᴜsᴛᴏᴍ ᴠᴀʀɪᴀʙʟᴇs ᴀs KEY=VALUE, ᴏɴᴇ ᴘᴇʀ ʟɪɴᴇ. ᴄᴏʀᴇ sᴇᴄʀᴇᴛs ᴀʀᴇ ᴘʀᴏᴛᴇᴄᴛᴇᴅ; ᴠᴀʟᴜᴇs ᴀʀᴇ ᴇɴᴄʀʏᴘᴛᴇᴅ."
    }
    await _send(update,context,prompts[field],InlineKeyboardMarkup([[InlineKeyboardButton("· ᴄᴀɴᴄᴇʟ ·",callback_data=f"clone:edit:{clone_id}")]]))


async def _redeploy_clone(update,context,row,token_override=None):
    db=context.application.bot_data["db"]; cipher=Fernet(context.application.bot_data["encryption_key"])
    token=token_override or cipher.decrypt(row["encrypted_token"].encode()).decode()
    env=json.loads(cipher.decrypt(row["encrypted_environment"].encode()).decode()) if row["encrypted_environment"] else {}
    new_id=await context.application.bot_data["provisioner"].redeploy(
        row["product"],row["clone_id"],token,context.application.bot_data["owner_id"],
        current_service_id=row["render_service_id"],image_ref=row["image_ref"] or None,
        extra_environment=env,region=row["render_region"],plan=row["render_plan"])
    encrypted=cipher.encrypt(token.encode()).decode()
    await db.require().execute("UPDATE clone_instances SET render_service_id=$1,encrypted_token=$2,status='provisioning',error_code=NULL,updated_at=NOW() WHERE clone_id=$3",new_id,encrypted,row["clone_id"])
    await _send(update,context,f"ᴄʟᴏɴᴇ @{row['bot_username']} ʜᴀs ʙᴇᴇɴ ʀᴇᴅᴇᴘʟᴏʏᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ.")


async def _capture_clone_edit(update,context,pending):
    message=update.effective_message
    if not message or not message.text: return
    if not _allowed(update.effective_user.id,context):
        context.user_data.pop("pending_clone_edit",None); return
    clone_id,field=pending["clone_id"],pending["field"]; db=context.application.bot_data["db"]
    row=await db.require().fetchrow("SELECT * FROM clone_instances WHERE clone_id=$1 AND owner_id=$2",clone_id,context.application.bot_data["owner_id"])
    if not row:
        context.user_data.pop("pending_clone_edit",None); await _send(update,context,"ᴄʟᴏɴᴇ ɴᴏᴛ ғᴏᴜɴᴅ."); return
    value=message.text.strip()
    if field=="token":
        try: await message.delete()
        except Exception: log.warning("Could not delete replacement token message")
        try:
            new_bot=Bot(token=value); await new_bot.initialize()
            try: identity=await new_bot.get_me()
            finally: await new_bot.shutdown()
            if identity.id!=row["bot_id"]: raise ValueError("Token belongs to a different bot")
            await _redeploy_clone(update,context,row,token_override=value)
            context.user_data.pop("pending_clone_edit",None)
        except Exception as exc:
            log.warning("Bot token replacement failed (%s)",type(exc).__name__)
            await _send(update,context,f"ɴᴇᴡ ᴛᴏᴋᴇɴ ɴᴏᴛ ᴀᴘᴘʟɪᴇᴅ: {type(exc).__name__}. ᴛʀʏ ᴀɢᴀɪɴ ᴏʀ ᴄʜᴇᴄᴋ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ.")
        return
    if field=="name":
        if not value or len(value)>64: await _send(update,context,"ɴᴀᴍᴇ ᴍᴜsᴛ ʙᴇ 1–64 ᴄʜᴀʀᴀᴄᴛᴇʀs."); return
        token=Fernet(context.application.bot_data["encryption_key"]).decrypt(row["encrypted_token"].encode()).decode()
        bot=Bot(token=token)
        try:
            await bot.initialize()
            try: await bot.set_my_name(value)
            finally: await bot.shutdown()
        except Exception as exc: await _send(update,context,f"ᴄᴏᴜʟᴅ ɴᴏᴛ ᴜᴘᴅᴀᴛᴇ ɴᴀᴍᴇ: {type(exc).__name__}."); return
        await db.require().execute("UPDATE clone_instances SET bot_name=$1,updated_at=NOW() WHERE clone_id=$2",value,clone_id)
    elif field=="repository":
        try: repo_url,image_ref=_parse_repository(value,row['product'])
        except ValueError as exc: await _send(update,context,str(exc)); return
        await db.require().execute("UPDATE clone_instances SET repository_url=$1,image_ref=$2,updated_at=NOW() WHERE clone_id=$3",repo_url,image_ref,clone_id)
    elif field=="hosting":
        items={}
        for line in value.splitlines():
            if not line.strip(): continue
            if "=" not in line: await _send(update,context,"ᴜsᴇ plan=VALUE ᴛᴏ ᴄʜᴀɴɢᴇ ᴛʜᴇ ᴡᴏʀᴋᴇʀ ᴘʟᴀɴ."); return
            key,val=line.split("=",1); items[key.strip()]=val.strip()
        if set(items)-{"plan"}: await _send(update,context,"ᴏɴʟʏ plan ɪs ᴇᴅɪᴛᴀʙʟᴇ ʜᴇʀᴇ; ᴡᴏʀᴋᴇʀ ʀᴇɢɪᴏɴ ɪs sᴇᴛ ɢʟᴏʙᴀʟʟʏ ɪɴ RENDER_REGION."); return
        plan=items.get("plan",row["render_plan"] or "starter").lower()
        valid_plans={"starter","standard","pro","pro_plus","pro_max","pro_ultra","0.5c-512mb","1c-2g","2c-4g","2c-8g","2c-16g","4c-8g","4c-16g","4c-32g","8c-16g","8c-32g","8c-64g","12c-24g","12c-48g","12c-96g"}
        if plan not in valid_plans: await _send(update,context,"ɪɴᴠᴀʟɪᴅ Rᴇɴᴅᴇʀ ᴘʟᴀɴ."); return
        await db.require().execute("UPDATE clone_instances SET render_plan=$1,updated_at=NOW() WHERE clone_id=$2",plan,clone_id)
    elif field=="environment":
        try: env=_parse_environment(value)
        except ValueError as exc: await _send(update,context,str(exc)); return
        previous=(
            json.loads(Fernet(context.application.bot_data["encryption_key"]).decrypt(row["encrypted_environment"].encode()).decode())
            if row["encrypted_environment"] else {}
        )
        if row["product"]=="link" and previous.get("SHORTENER_ENCRYPTION_KEY"):
            env["SHORTENER_ENCRYPTION_KEY"]=previous["SHORTENER_ENCRYPTION_KEY"]
        secret=Fernet(context.application.bot_data["encryption_key"]).encrypt(json.dumps(env,ensure_ascii=False).encode()).decode()
        await db.require().execute("UPDATE clone_instances SET encrypted_environment=$1,updated_at=NOW() WHERE clone_id=$2",secret,clone_id)
    context.user_data.pop("pending_clone_edit",None)
    await _send(update,context,"ᴄᴏɴғɪɢᴜʀᴀᴛɪᴏɴ sᴀᴠᴇᴅ. ᴘʀᴇss ᴅᴇᴘʟᴏʏ ᴀɢᴀɪɴ ᴛᴏ ᴀᴘᴘʟʏ ᴛʜᴇ ᴄʜᴀɴɢᴇs.",
                InlineKeyboardMarkup([[InlineKeyboardButton("· ᴏᴘᴇɴ ᴄʟᴏɴᴇ ᴇᴅɪᴛᴏʀ ·",callback_data=f"clone:edit:{clone_id}")]]))


async def clone_edit_callback(update,context):
    q=update.callback_query
    if not _allowed(q.from_user.id,context): await q.answer("Owner / Admin only.",show_alert=True); return
    await q.answer(); parts=q.data.split(":"); db=context.application.bot_data["db"]
    if parts[1]=="edit":
        context.user_data.pop("pending_clone_edit",None)
        row=await db.require().fetchrow("SELECT * FROM clone_instances WHERE clone_id=$1 AND owner_id=$2",parts[2],context.application.bot_data["owner_id"])
        if not row: await _send(update,context,"ᴄʟᴏɴᴇ ɴᴏᴛ ғᴏᴜɴᴅ."); return
        await _show_clone_edit_menu(update,context,row)
    elif parts[1]=="editfield" and len(parts)==4:
        await _start_clone_edit(update,context,parts[2],parts[3])
    elif parts[1]=="editkey" and len(parts)==4:
        clone_id,key=parts[2],parts[3]
        row=await db.require().fetchrow("SELECT clone_id FROM clone_instances WHERE clone_id=$1 AND owner_id=$2",clone_id,context.application.bot_data["owner_id"])
        if not row or key not in {"file.start","file.about","file.help","link.start","link.about","link.help"}:
            await _send(update,context,"ɪɴᴠᴀʟɪᴅ ᴄʟᴏɴᴇ ᴏʀ ᴍᴇssᴀɢᴇ."); return
        context.user_data["editing_text_key"]=key; context.user_data["editing_clone_id"]=clone_id
        current=await db.get_text(clone_id,key,"")
        await _send(update,context,f"(Quote start) ᴇᴅɪᴛɪɴɢ {key} (Quote end)\n\nᴄᴜʀʀᴇɴᴛ ᴛᴇxᴛ:\n{current}\n\nsᴇɴᴅ ᴛʜᴇ ɴᴇᴡ ᴛᴇxᴛ ɴᴏᴡ.")
    elif parts[1]=="deploy":
        clone_id=parts[2]
        markup=InlineKeyboardMarkup([[InlineKeyboardButton("· ʏᴇs, ᴅᴇᴘʟᴏʏ ·",callback_data=f"clone:redeploy:{clone_id}"),InlineKeyboardButton("· ᴄᴀɴᴄᴇʟ ·",callback_data=f"clone:edit:{clone_id}")]])
        await _send(update,context,"(Quote start) ʀᴇᴘʟᴀᴄᴇ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ʀᴇɴᴅᴇʀ sᴇʀᴠɪᴄᴇ ᴡɪᴛʜ ᴛʜᴇ sᴀᴠᴇᴅ ᴄᴏɴғɪɢᴜʀᴀᴛɪᴏɴ? (Quote end)",markup)
    elif parts[1]=="redeploy":
        row=await db.require().fetchrow("SELECT * FROM clone_instances WHERE clone_id=$1 AND owner_id=$2",parts[2],context.application.bot_data["owner_id"])
        if not row: await _send(update,context,"ᴄʟᴏɴᴇ ɴᴏᴛ ғᴏᴜɴᴅ."); return
        try: await _redeploy_clone(update,context,row)
        except Exception as exc:
            log.exception("Clone redeploy failed (%s)",type(exc).__name__)
            await _send(update,context,f"ʀᴇᴅᴇᴘʟᴏʏ ғᴀɪʟᴇᴅ: {type(exc).__name__}.")


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
    app.add_handler(CommandHandler("clonedit",clonedit))
    app.add_handler(CommandHandler("cloneinfo",cloneinfo))
    app.add_handler(CallbackQueryHandler(select_product,pattern=r"^clone:select:(file|link)$"))
    app.add_handler(CallbackQueryHandler(clones_filter_callback,pattern=r"^clones:(all|running|stopped|recent|file|link|refresh)$"))
    app.add_handler(CallbackQueryHandler(clone_detail_callback,pattern=r"^clone:detail:"))
    app.add_handler(CallbackQueryHandler(clone_manage_callback,pattern=r"^clone:(stop|restart|confirm-stop|confirm-restart):"))
    app.add_handler(CallbackQueryHandler(clone_edit_callback,pattern=r"^clone:(edit|editkey|editfield|deploy|redeploy):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,receive_token),group=-2)
