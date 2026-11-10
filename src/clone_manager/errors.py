import logging
from telegram import Update
from telegram.ext import ContextTypes
from .branding import send_branded

logger = logging.getLogger(__name__)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    # Do not log bot tokens, update payloads or arbitrary user-provided secrets.
    error_type=type(context.error).__name__ if context.error else "unknown"
    logger.error("Unhandled update error: %s", error_type)
    try:
        await context.application.bot_data["db"].require().execute(
            "INSERT INTO manager_activity(action,details,level) VALUES($1,$2,$3)",
            "error",error_type,"error")
    except Exception:
        logger.exception("Could not persist error activity")
    if isinstance(update, Update) and update.effective_chat:
        try:
            await send_branded(context.bot, update.effective_chat.id,
                "ᴡᴇ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴄᴏᴍᴘʟᴇᴛᴇ ᴛʜᴀᴛ ᴀᴄᴛɪᴏɴ. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ.",
                image_url=context.application.bot_data["image_url"],
                image_path=context.application.bot_data["image_path"],
                small_caps=context.application.bot_data["small_caps"],
                footer_message=await context.application.bot_data["db"].get_setting("branding.footer",""))
        except Exception:
            logger.exception("Unable to send branded error notice")
