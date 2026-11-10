from __future__ import annotations
import os
from pathlib import Path
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, MessageHandler, filters
from .config import Settings
from .database import Database
from .defaults import DEFAULT_MESSAGES
from .provisioner import DockerProvisioner
from .handlers.clones import add_clone_handlers
from .message_editor.handlers import add_editor_handlers
from .admin import add_admin_handlers, command_access_gate
from .errors import error_handler
from .branding import close_branded_message

async def post_init(app):
    s=app.bot_data["settings"]
    db=Database(s.database_url)
    await db.connect()
    await db.init_schema(Path("migrations/001_initial.sql").read_text(encoding="utf-8"))
    app.bot_data["db"]=db
    if not await db.get_setting("branding.footer",""):
        await db.set_setting("branding.footer",'(LINK url="https://t.me/just_astha")ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ᴄʜᴀᴛ ᴡɪᴛʜ ᴍᴇ(/LINK)')
    app.bot_data["image_url"]=await db.get_setting("branding.image_url",app.bot_data["image_url"])
    from .formatting import set_quote_enabled
    set_quote_enabled((await db.get_setting("branding.quote_enabled","true")).lower() in {"on","true"})

async def post_shutdown(app):
    db=app.bot_data.get("db")
    if db: await db.close()

def main():
    settings=Settings.from_env()
    owner_id=settings.owner_id
    admin_ids={int(x) for x in os.getenv("ADMIN_IDS","").replace(","," ").split() if x.isdigit()}
    allowed=set(admin_ids); allowed.add(owner_id)
    encryption_key=os.environ.get("TOKEN_ENCRYPTION_KEY","").encode()
    if not encryption_key: raise RuntimeError("TOKEN_ENCRYPTION_KEY is required. Generate with scripts/generate_fernet_key.py")
    from cryptography.fernet import Fernet
    Fernet(encryption_key)
    app=(ApplicationBuilder().token(settings.bot_token).post_init(post_init).post_shutdown(post_shutdown).build())
    app.bot_data.update({"settings":settings,"owner_id":owner_id,"admins":admin_ids,"clone_id":settings.clone_id,
        "image_url":settings.branding_image_url,"image_path":settings.branding_image_path,
        "small_caps":settings.small_caps,"defaults":DEFAULT_MESSAGES,"allowed_users":allowed,
        "encryption_key":encryption_key,"provisioner":DockerProvisioner()})
    app.add_handler(CallbackQueryHandler(close_branded_message,pattern=r"^branding:close$"),group=-10)
    app.add_handler(MessageHandler(filters.COMMAND, command_access_gate), group=-100)
    add_clone_handlers(app)
    add_editor_handlers(app)
    add_admin_handlers(app)
    app.add_error_handler(error_handler)
    app.run_polling(allowed_updates=["message","callback_query"])

if __name__=="__main__": main()
