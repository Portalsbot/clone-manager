from __future__ import annotations
import asyncio, logging, secrets, re
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
        small_caps=context.application.bot_data["small_caps"],reply_markup=markup)

def _allowed(user_id:int, context)->bool:
    return user_id in context.application.bot_data["allowed_users"]

async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context): return
    await _send(update,context,context.application.bot_data["defaults"]["cloner.start"])

async def clone(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context): return
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
        small_caps=context.application.bot_data["small_caps"])

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
    if not _allowed(update.effective_user.id,context): return
    rows=await context.application.bot_data["db"].require().fetch(
        "SELECT clone_id,product,bot_username,status,created_at FROM clone_instances WHERE owner_id=$1 ORDER BY created_at DESC LIMIT 50",update.effective_user.id)
    body="**ʏᴏᴜʀ ᴄʟᴏɴᴇs**\n\n"+("\n".join(f"{r['clone_id']} · {r['product']} · @{r['bot_username']} · {r['status']}" for r in rows) if rows else "No clones registered.")
    await _send(update,context,body)

async def stopclone(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context): return
    if not context.args: body="Usage: `/stopclone CLONE_ID`"
    else:
        row=await context.application.bot_data["db"].require().fetchrow("SELECT owner_id,container_id FROM clone_instances WHERE clone_id=$1",context.args[0])
        if not row or row["owner_id"]!=update.effective_user.id: body="Clone not found or not owned by you."
        else:
            await context.application.bot_data["provisioner"].stop(row["container_id"])
            await context.application.bot_data["db"].require().execute("UPDATE clone_instances SET status='stopped',updated_at=NOW() WHERE clone_id=$1",context.args[0]); body="Clone stopped."
    await _send(update,context,body)

async def restartclone(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id,context): return
    if not context.args: body="Usage: `/restartclone CLONE_ID`"
    else:
        row=await context.application.bot_data["db"].require().fetchrow("SELECT owner_id,container_id FROM clone_instances WHERE clone_id=$1",context.args[0])
        if not row or row["owner_id"]!=update.effective_user.id: body="Clone not found or not owned by you."
        else:
            await context.application.bot_data["provisioner"].restart(row["container_id"])
            await context.application.bot_data["db"].require().execute("UPDATE clone_instances SET status='running',updated_at=NOW() WHERE clone_id=$1",context.args[0]); body="Clone restarted."
    await _send(update,context,body)


async def cloneedit(update:Update,context:ContextTypes.DEFAULT_TYPE):
    """Platform-owner remote message override for an existing clone."""
    if update.effective_user.id != context.application.bot_data["owner_id"]: return
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
    if update.effective_user.id != context.application.bot_data["owner_id"]: return
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
    app.add_handler(CommandHandler("clonepreview",clonepreview))
    app.add_handler(CommandHandler("clonebuttonadd",clonebuttonadd))
    app.add_handler(CommandHandler("clonebuttonedit",clonebuttonedit))
    app.add_handler(CommandHandler("clonebuttondel",clonebuttondel))
    app.add_handler(CallbackQueryHandler(select_product,pattern=r"^clone:select:(file|link)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,receive_token),group=-2)
