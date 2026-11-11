from __future__ import annotations
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from telegram import BotCommand, BotCommandScopeChat
from telegram.ext import ApplicationBuilder, ApplicationHandlerStop, CallbackQueryHandler, MessageHandler, filters
from .config import Settings
from .paths import APP_DATA_DIR
from .database import Database
from .defaults import DEFAULT_MESSAGES
from .provisioner import RenderProvisioner
from .handlers.clones import add_clone_handlers
from .message_editor.handlers import add_editor_handlers
from .admin import add_admin_handlers, command_access_gate
from .errors import error_handler
from .branding import close_branded_message
from .fsubs import add_fsubs_handlers, message_fsubs_gate, callback_fsubs_gate

async def post_init(app):
    s=app.bot_data["settings"]
    db=Database(s.database_url)
    await db.connect()
    migrations_dir = APP_DATA_DIR / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))
    if not migration_files:
        raise RuntimeError(f"No database migrations found in {migrations_dir}")
    for migration in migration_files:
        await db.init_schema(migration.read_text(encoding="utf-8"))
    # If a process stops mid-delivery, recipient-level outcomes are unknown.
    # Mark that job failed rather than replaying it and duplicating some recipients.
    interrupted = await db.require().fetch("""
        UPDATE scheduled_broadcasts
        SET status='failed',
            last_error=COALESCE(last_error,'Process restarted during delivery; recipient-level outcome is unknown.'),
            finished_at=COALESCE(finished_at,NOW())
        WHERE status='sending'
        RETURNING id,created_by
    """)
    for item in interrupted:
        await db.require().execute(
            "INSERT INTO manager_activity(actor_id,action,details,level) VALUES($1,'broadcast',$2,'error')",
            item["created_by"],
            f"scheduled id={item['id']} failed after restart; delivery outcome is unknown",
        )
    app.bot_data["db"]=db
    public_commands = [BotCommand("start", "Open the private bot menu")]
    admin_commands = [
        BotCommand("clone", "Create a new bot clone"),
        BotCommand("clones", "View and manage bot clones"),
        BotCommand("stopclone", "Stop a clone"),
        BotCommand("restartclone", "Restart a clone"),
        BotCommand("clonedit", "Edit clone configuration"),
        BotCommand("cloneinfo", "View detailed clone information"),
        BotCommand("about", "About Clone Manager"),
        BotCommand("help", "Contact administrator for help"),
        BotCommand("commands", "List available commands"),
        BotCommand("settings", "Open manager settings"),
        BotCommand("broadcast", "Create an immediate or scheduled broadcast"),
        BotCommand("users", "Manage registered users"),
        BotCommand("stats", "View manager statistics"),
        BotCommand("logs", "View activity and error logs"),
        BotCommand("ping", "Check bot response"),
        BotCommand("diagnostics", "Check Telegram, PostgreSQL and Render API"),
        BotCommand("fsubs", "Manage force-subscription channels and message"),
        BotCommand("restart", "Restart or stop the manager"),
        BotCommand("maintenance", "Open maintenance controls"),
        BotCommand("setmaintenance", "Manage maintenance mode"),
        BotCommand("setstart", "Edit Start message"),
        BotCommand("setabout", "Edit About message"),
        BotCommand("sethelp", "Edit Help message"),
        BotCommand("setimage", "Change branding image URL"),
        BotCommand("setbuttons", "Edit inline buttons"),
        BotCommand("setfooter", "Edit message footer"),
        BotCommand("setquote", "Toggle quote markup"),
        BotCommand("setname", "Change bot display name"),
    ]
    await app.bot.set_my_commands(public_commands)
    for user_id in {app.bot_data["owner_id"], *app.bot_data["admins"]}:
        try:
            await app.bot.set_my_commands(public_commands + admin_commands,
                scope=BotCommandScopeChat(chat_id=user_id))
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Could not set admin command menu for user %s: %s", user_id, type(exc).__name__)
    if not await db.get_setting("branding.footer",""):
        await db.set_setting("branding.footer",'(LINK url="https://t.me/just_astha")ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ᴄʜᴀᴛ ᴡɪᴛʜ ᴍᴇ(/LINK)')
    app.bot_data["image_url"]=await db.get_setting("branding.image_url",app.bot_data["image_url"])
    from .formatting import set_quote_enabled
    set_quote_enabled((await db.get_setting("branding.quote_enabled","true")).lower() in {"on","true"})
    import asyncio
    app.bot_data["broadcast_lock"] = asyncio.Lock()
    if app.job_queue is None:
        raise RuntimeError("PTB JobQueue is unavailable; install the project dependencies.")
    from .broadcasts import scheduled_broadcast_worker
    app.job_queue.run_repeating(scheduled_broadcast_worker, interval=15, first=5, name="scheduled-broadcasts")

async def callback_access_gate(update, context):
    query = update.callback_query
    if query is None or query.data == "branding:close":
        return
    if query.from_user.id == context.application.bot_data["owner_id"]:
        return
    if await context.application.bot_data["db"].get_setting("system.maintenance", "false") == "true":
        await query.answer("Maintenance mode is enabled.", show_alert=True)
        raise ApplicationHandlerStop


async def message_access_gate(update, context):
    user = update.effective_user
    if user is None or user.id == context.application.bot_data["owner_id"]:
        return
    if await context.application.bot_data["db"].get_setting("system.maintenance", "false") == "true":
        for state in (
            "pending_setting", "pending_text_editor", "awaiting_text_draft", "user_action",
            "pending_clone_edit", "pending_clone_product", "editing_text_key", "editing_clone_id",
            "broadcast_mode", "pending_broadcast", "awaiting_broadcast_time",
        ):
            context.user_data.pop(state, None)
        raise ApplicationHandlerStop


async def post_shutdown(app):
    db=app.bot_data.get("db")
    if db: await db.close()


def _start_health_server():
    raw_port = os.getenv("PORT", "").strip()
    if not raw_port:
        return None
    try:
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError as exc:
        raise RuntimeError("PORT must be a valid TCP port.") from exc

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in {"/", "/health"}:
                self.send_response(404)
                self.end_headers()
                return
            body = b'{"status":"ok","service":"clone-manager"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, name="http-health", daemon=True).start()
    return server

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
        "encryption_key":encryption_key,"provisioner":RenderProvisioner()})
    app.add_handler(MessageHandler(filters.ALL, message_fsubs_gate), group=-110)
    app.add_handler(CallbackQueryHandler(callback_fsubs_gate), group=-11)
    app.add_handler(CallbackQueryHandler(close_branded_message,pattern=r"^branding:close$"),group=-10)
    app.add_handler(CallbackQueryHandler(callback_access_gate), group=-9)
    app.add_handler(MessageHandler(filters.COMMAND, command_access_gate), group=-100)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_access_gate), group=-90)
    add_clone_handlers(app)
    add_editor_handlers(app)
    add_admin_handlers(app)
    add_fsubs_handlers(app)
    app.add_error_handler(error_handler)
    app.bot_data["health_server"] = _start_health_server()
    app.run_polling(allowed_updates=["message","callback_query"])

if __name__=="__main__": main()
