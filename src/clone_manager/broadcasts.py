"""Immediate and persistent scheduled broadcasts."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter
from telegram.ext import ApplicationHandlerStop

from .branding import send_branded
from .formatting import render_text

log = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo("Asia/Kolkata")
MEDIA_METHODS = {
    "photo": ("send_photo", "photo"),
    "video": ("send_video", "video"),
    "document": ("send_document", "document"),
    "audio": ("send_audio", "audio"),
    "animation": ("send_animation", "animation"),
    "voice": ("send_voice", "voice"),
    "video_note": ("send_video_note", "video_note"),
    "sticker": ("send_sticker", "sticker"),
}


def parse_scheduled_at(value: str, *, now: datetime | None = None) -> datetime:
    try:
        scheduled = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=LOCAL_TZ)
    except ValueError as exc:
        raise ValueError("ᴜsᴇ YYYY-MM-DD HH:MM (Asia/Kolkata).") from exc
    current = now or datetime.now(LOCAL_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=LOCAL_TZ)
    if scheduled <= current.astimezone(LOCAL_TZ):
        raise ValueError("ᴛʜᴇ sᴄʜᴇᴅᴜʟᴇ ᴛɪᴍᴇ ᴍᴜsᴛ ʙᴇ ɪɴ ᴛʜᴇ ғᴜᴛᴜʀᴇ.")
    return scheduled.astimezone(timezone.utc)


def serialize_message(message) -> dict:
    if message.text:
        return {"kind": "text", "text": message.text}
    for media_type in MEDIA_METHODS:
        media = getattr(message, media_type, None)
        if not media:
            continue
        if media_type == "photo":
            media = media[-1]
        return {
            "kind": "media",
            "media_type": media_type,
            "file_id": media.file_id,
            "caption": message.caption or "",
        }
    raise ValueError("sᴇɴᴅ ᴛᴇxᴛ ᴏʀ sᴜᴘᴘᴏʀᴛᴇᴅ ᴍᴇᴅɪᴀ (ᴘʜᴏᴛᴏ, ᴠɪᴅᴇᴏ, ᴅᴏᴄᴜᴍᴇɴᴛ, ᴀᴜᴅɪᴏ, ᴀɴɪᴍᴀᴛɪᴏɴ, ᴠᴏɪᴄᴇ, ᴠɪᴅᴇᴏ ɴᴏᴛᴇ, sᴛɪᴄᴋᴇʀ).")


def _is_admin(user_id: int, context) -> bool:
    return user_id == context.application.bot_data["owner_id"] or user_id in context.application.bot_data.get("admins", set())


def _markup(rows):
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data) for label, data in row] for row in rows])


async def _send(context, chat_id, body, markup=None):
    db = context.application.bot_data["db"]
    footer = await db.get_setting("branding.footer", '(LINK url="https://t.me/just_astha")ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ᴄʜᴀᴛ ᴡɪᴛʜ ᴍᴇ(/LINK)')
    return await send_branded(
        context.bot, chat_id, body,
        image_url=context.application.bot_data["image_url"],
        image_path=context.application.bot_data.get("image_path"),
        small_caps=context.application.bot_data.get("small_caps", True),
        reply_markup=markup, footer_message=footer,
    )


async def _recipient_ids(db) -> list[int]:
    rows = await db.require().fetch("""
        SELECT DISTINCT u.user_id
        FROM bot_users AS u
        WHERE u.is_banned = FALSE
          AND NOT EXISTS (SELECT 1 FROM bot_user_blocks AS b WHERE b.user_id = u.user_id)
          AND NOT EXISTS (SELECT 1 FROM bot_users AS banned WHERE banned.user_id = u.user_id AND banned.is_banned = TRUE)
        ORDER BY u.user_id
    """)
    return [int(row["user_id"]) for row in rows]


async def _deliver_one(context, chat_id: int, payload: dict) -> None:
    db = context.application.bot_data["db"]
    footer = await db.get_setting("branding.footer", '(LINK url="https://t.me/just_astha")ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ᴄʜᴀᴛ ᴡɪᴛʜ ᴍᴇ(/LINK)')
    if payload["kind"] == "text":
        await send_branded(
            context.bot, chat_id, payload["text"],
            image_url=context.application.bot_data["image_url"],
            image_path=context.application.bot_data.get("image_path"),
            small_caps=context.application.bot_data.get("small_caps", True),
            footer_message=footer,
        )
        return
    media_type = payload["media_type"]
    method_name, argument_name = MEDIA_METHODS[media_type]
    args = {"chat_id": chat_id, argument_name: payload["file_id"]}
    caption = payload.get("caption", "")
    if caption and media_type not in {"sticker", "video_note"}:
        args["caption"] = render_text(caption, context.application.bot_data.get("small_caps", True))
        args["parse_mode"] = "HTML"
    args["reply_markup"] = InlineKeyboardMarkup([[InlineKeyboardButton("· ᴄʟᴏsᴇ ·", callback_data="branding:close")]])
    await send_branded(
        context.bot, chat_id, "ᴍᴇᴅɪᴀ ʙʀᴏᴀᴅᴄᴀsᴛ",
        image_url=context.application.bot_data["image_url"],
        image_path=context.application.bot_data.get("image_path"),
        small_caps=context.application.bot_data.get("small_caps", True),
        footer_message=footer,
    )
    await getattr(context.bot, method_name)(**args)


async def _deliver_payload(context, payload: dict) -> tuple[int, int]:
    recipients = await _recipient_ids(context.application.bot_data["db"])
    sent = failed = 0
    for chat_id in recipients:
        for attempt in range(3):
            try:
                await _deliver_one(context, chat_id, payload)
                sent += 1
                break
            except RetryAfter as exc:
                if attempt == 2:
                    failed += 1
                else:
                    delay = exc.retry_after.total_seconds() if hasattr(exc.retry_after, "total_seconds") else float(exc.retry_after)
                    await asyncio.sleep(delay + 0.25)
            except Exception as exc:
                failed += 1
                log.warning("Broadcast delivery failed (%s)", type(exc).__name__)
                break
        await asyncio.sleep(0.08)
    return sent, failed


async def _log_broadcast(db, actor_id: int, details: str, level: str = "info") -> None:
    await db.require().execute(
        "INSERT INTO manager_activity(actor_id,action,details,level) VALUES($1,'broadcast',$2,$3)",
        actor_id, details[:1000], level,
    )


async def _preview(context, chat_id: int, payload: dict) -> None:
    await _deliver_one(context, chat_id, payload)
    await _send(
        context, chat_id, "ᴘʀᴇᴠɪᴇᴡ ʀᴇᴀᴅʏ. ᴄʜᴏᴏsᴇ ᴀ ᴅᴇʟɪᴠᴇʀʏ ᴀᴄᴛɪᴏɴ.",
        _markup([
            [("· sᴇɴᴅ ɴᴏᴡ ·", "broadcast:now"), ("· sᴄʜᴇᴅᴜʟᴇ ·", "broadcast:settime")],
            [("· ᴄᴀɴᴄᴇʟ ·", "broadcast:cancel")],
        ]),
    )


async def capture_broadcast_message(update, context) -> None:
    message = update.effective_message
    if not message or not _is_admin(update.effective_user.id, context):
        return
    if context.user_data.get("awaiting_broadcast_time"):
        try:
            scheduled = parse_scheduled_at(message.text or "")
        except ValueError as exc:
            await _send(context, update.effective_chat.id, str(exc))
            raise ApplicationHandlerStop
        pending = context.user_data.get("pending_broadcast")
        if not pending:
            context.user_data.pop("awaiting_broadcast_time", None)
            await _send(context, update.effective_chat.id, "ᴛʜᴇ ʙʀᴏᴀᴅᴄᴀsᴛ ᴅʀᴀғᴛ ᴇxᴘɪʀᴇᴅ. sᴛᴀʀᴛ ᴀɢᴀɪɴ.")
            raise ApplicationHandlerStop
        db = context.application.bot_data["db"]
        row = await db.require().fetchrow(
            "INSERT INTO scheduled_broadcasts(created_by,scheduled_at,payload,status) VALUES($1,$2,$3::jsonb,'pending') RETURNING id",
            update.effective_user.id, scheduled, json.dumps(pending["payload"], ensure_ascii=False),
        )
        context.user_data.pop("awaiting_broadcast_time", None)
        context.user_data.pop("pending_broadcast", None)
        local_time = scheduled.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
        await _send(context, update.effective_chat.id, f"ʙʀᴏᴀᴅᴄᴀsᴛ #{row['id']} sᴄʜᴇᴅᴜʟᴇᴅ ғᴏʀ {local_time} Asia/Kolkata.",
                    _markup([[("· ᴠɪᴇᴡ Qᴜᴇᴜᴇ ·", "broadcast:queue")]]))
        await _log_broadcast(db, update.effective_user.id, f"scheduled id={row['id']} at={local_time}")
        raise ApplicationHandlerStop

    mode = context.user_data.get("broadcast_mode")
    if not mode:
        return
    try:
        payload = serialize_message(message)
    except ValueError as exc:
        await _send(context, update.effective_chat.id, str(exc))
        raise ApplicationHandlerStop
    if mode == "text" and payload["kind"] != "text":
        await _send(context, update.effective_chat.id, "ᴛᴇxᴛ ʙʀᴏᴀᴅᴄᴀsᴛ ʀᴇǫᴜɪʀᴇs ᴀ ᴛᴇxᴛ ᴍᴇssᴀɢᴇ.")
        raise ApplicationHandlerStop
    if mode == "media" and payload["kind"] != "media":
        await _send(context, update.effective_chat.id, "ᴍᴇᴅɪᴀ ʙʀᴏᴀᴅᴄᴀsᴛ ʀᴇǫᴜɪʀᴇs ᴀ ᴍᴇᴅɪᴀ ᴍᴇssᴀɢᴇ.")
        raise ApplicationHandlerStop

    context.user_data.pop("broadcast_mode", None)
    context.user_data["pending_broadcast"] = {"payload": payload}
    await _preview(context, update.effective_chat.id, payload)
    if mode == "schedule":
        context.user_data["awaiting_broadcast_time"] = True
        await _send(context, update.effective_chat.id, "sᴇɴᴅ ᴅᴇʟɪᴠᴇʀʏ ᴛɪᴍᴇ ɪɴ Asia/Kolkata: YYYY-MM-DD HH:MM.")
    raise ApplicationHandlerStop


async def broadcast_callback(update, context) -> None:
    q = update.callback_query
    db = context.application.bot_data["db"]
    if not _is_admin(q.from_user.id, context):
        await q.answer("Owner / Admin only.", show_alert=True)
        return
    if q.from_user.id != context.application.bot_data["owner_id"] and await db.get_setting("system.maintenance", "false") == "true":
        await q.answer("Maintenance mode is enabled.", show_alert=True)
        return
    await q.answer()
    chat_id = q.message.chat_id
    data = q.data
    if data in {"broadcast:text", "broadcast:media", "broadcast:all", "broadcast:schedule"}:
        for state in ("pending_setting","pending_text_editor","awaiting_text_draft","user_action",
                      "pending_clone_edit","pending_clone_product","editing_text_key","editing_clone_id"):
            context.user_data.pop(state,None)
    if data == "broadcast:text":
        context.user_data["broadcast_mode"] = "text"
        context.user_data.pop("pending_broadcast", None)
        await _send(context, chat_id, "sᴇɴᴅ ᴛʜᴇ ᴛᴇxᴛ ᴍᴇssᴀɢᴇ ᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ.")
    elif data == "broadcast:media":
        context.user_data["broadcast_mode"] = "media"
        context.user_data.pop("pending_broadcast", None)
        await _send(context, chat_id, "sᴇɴᴅ ᴛʜᴇ ᴍᴇᴅɪᴀ ᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ.")
    elif data == "broadcast:all":
        count = len(await _recipient_ids(db))
        await _send(context, chat_id, f"ᴀʟʟ ᴜɴʙʟᴏᴄᴋᴇᴅ ᴜsᴇʀs sᴇʟᴇᴄᴛᴇᴅ: {count}. ᴛᴇxᴛ, ᴍᴇᴅɪᴀ, ᴀɴᴅ sᴄʜᴇᴅᴜʟᴇ ᴀʀᴇ ᴀᴠᴀɪʟᴀʙʟᴇ.",
                    _markup([[("· ᴛᴇxᴛ ·","broadcast:text"),("· ᴍᴇᴅɪᴀ ·","broadcast:media")],[("· sᴄʜᴇᴅᴜʟᴇ ·","broadcast:schedule")]]))
    elif data == "broadcast:schedule":
        context.user_data["broadcast_mode"] = "schedule"
        context.user_data.pop("pending_broadcast", None)
        context.user_data.pop("awaiting_broadcast_time", None)
        await _send(context, chat_id, "sᴇɴᴅ ᴛʜᴇ ᴛᴇxᴛ ᴏʀ ᴍᴇᴅɪᴀ ᴍᴇssᴀɢᴇ ᴛᴏ sᴄʜᴇᴅᴜʟᴇ.")
    elif data == "broadcast:now":
        pending = context.user_data.get("pending_broadcast")
        if not pending:
            await _send(context, chat_id, "ɴᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ᴅʀᴀғᴛ ɪs ᴀᴠᴀɪʟᴀʙʟᴇ.")
            return
        context.user_data.pop("pending_broadcast", None)
        context.user_data.pop("awaiting_broadcast_time", None)
        sent, failed = await _deliver_payload(context, pending["payload"])
        await _log_broadcast(db, q.from_user.id, f"sent={sent}, failed={failed}, kind={pending['payload']['kind']}")
        await _send(context, chat_id, f"ʙʀᴏᴀᴅᴄᴀsᴛ ғɪɴɪsʜᴇᴅ. sᴇɴᴛ: {sent} · ғᴀɪʟᴇᴅ: {failed}")
    elif data == "broadcast:settime":
        if not context.user_data.get("pending_broadcast"):
            await _send(context, chat_id, "ɴᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ᴅʀᴀғᴛ ɪs ᴀᴠᴀɪʟᴀʙʟᴇ.")
            return
        context.user_data["awaiting_broadcast_time"] = True
        await _send(context, chat_id, "sᴇɴᴅ ᴅᴇʟɪᴠᴇʀʏ ᴛɪᴍᴇ ɪɴ Asia/Kolkata: YYYY-MM-DD HH:MM.")
    elif data == "broadcast:cancel":
        for key in ("broadcast_mode", "pending_broadcast", "awaiting_broadcast_time"):
            context.user_data.pop(key, None)
        await _send(context, chat_id, "ʙʀᴏᴀᴅᴄᴀsᴛ ᴅʀᴀғᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ.")
    elif data == "broadcast:queue":
        rows = await db.require().fetch("SELECT id,scheduled_at,status FROM scheduled_broadcasts WHERE status='pending' ORDER BY scheduled_at LIMIT 20")
        if not rows:
            await _send(context, chat_id, "sᴄʜᴇᴅᴜʟᴇᴅ ʙʀᴏᴀᴅᴄᴀsᴛ Qᴜᴇᴜᴇ ɪs ᴇᴍᴘᴛʏ.")
            return
        lines = ["(Quote start) sᴄʜᴇᴅᴜʟᴇᴅ ʙʀᴏᴀᴅᴄᴀsᴛs (Quote end)"]
        buttons = []
        for row in rows:
            local_time = row["scheduled_at"].astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
            lines.append(f"#{row['id']} · {local_time} Asia/Kolkata")
            buttons.append([("· ᴄᴀɴᴄᴇʟ #" + str(row["id"]) + " ·", f"broadcast:canceljob:{row['id']}")])
        buttons.append([("· ʙᴀᴄᴋ ·","admin:back")])
        await _send(context, chat_id, "\n".join(lines), _markup(buttons))
    elif data.startswith("broadcast:canceljob:"):
        try:
            job_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            await _send(context, chat_id, "ɪɴᴠᴀʟɪᴅ sᴄʜᴇᴅᴜʟᴇ ɪᴅ.")
            return
        result = await db.require().execute("UPDATE scheduled_broadcasts SET status='cancelled',finished_at=NOW() WHERE id=$1 AND status='pending'", job_id)
        await _send(context, chat_id, f"sᴄʜᴇᴅᴜʟᴇᴅ ʙʀᴏᴀᴅᴄᴀsᴛ #{job_id} ᴄᴀɴᴄᴇʟʟᴇᴅ." if result.endswith(" 1") else "ᴛʜɪs sᴄʜᴇᴅᴜʟᴇ ɪs ɴᴏᴛ ᴘᴇɴᴅɪɴɢ.")
    elif data == "broadcast:report":
        rows = await db.require().fetch("SELECT created_at,details FROM manager_activity WHERE action='broadcast' ORDER BY created_at DESC LIMIT 10")
        report = "(Quote start) ʟᴀsᴛ 10 ʙʀᴏᴀᴅᴄᴀsᴛs (Quote end)\n\n" + ("\n".join(f"{r['created_at']} · {r['details']}" for r in rows) if rows else "ɴᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ʀᴇᴄᴏʀᴅs.")
        await _send(context, chat_id, report, _markup([[("· Qᴜᴇᴜᴇ ·","broadcast:queue")]]))


async def scheduled_broadcast_worker(context) -> None:
    app = context.application
    db = app.bot_data["db"]
    lock = app.bot_data["broadcast_lock"]
    if lock.locked():
        return
    async with lock:
        for _ in range(3):
            async with db.require().acquire() as connection:
                async with connection.transaction():
                    row = await connection.fetchrow("""
                        SELECT id, created_by, payload
                        FROM scheduled_broadcasts
                        WHERE status='pending' AND scheduled_at <= NOW()
                        ORDER BY scheduled_at, id
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    """)
                    if row:
                        await connection.execute("UPDATE scheduled_broadcasts SET status='sending',started_at=NOW() WHERE id=$1", row["id"])
            if not row:
                return
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            try:
                sent, failed = await _deliver_payload(context, payload)
                status = "completed" if failed == 0 else ("partial" if sent else "failed")
                await db.require().execute(
                    "UPDATE scheduled_broadcasts SET status=$1,sent_count=$2,failed_count=$3,finished_at=NOW() WHERE id=$4",
                    status, sent, failed, row["id"],
                )
                await _log_broadcast(db, row["created_by"], f"scheduled id={row['id']}, status={status}, sent={sent}, failed={failed}", "info" if not failed else "warning")
                try:
                    await _send(
                        context, row["created_by"],
                        f"sᴄʜᴇᴅᴜʟᴇᴅ ʙʀᴏᴀᴅᴄᴀsᴛ #{row['id']} {status}. sᴇɴᴛ: {sent} · ғᴀɪʟᴇᴅ: {failed}.",
                        _markup([[("· ᴠɪᴇᴡ ʙʀᴏᴀᴅᴄᴀsᴛ ʀᴇᴘᴏʀᴛ ·", "broadcast:report")]]),
                    )
                except Exception as notify_error:
                    log.warning("Could not notify broadcast creator (%s)", type(notify_error).__name__)
            except Exception as exc:
                log.exception("Scheduled broadcast %s failed", row["id"])
                await db.require().execute("UPDATE scheduled_broadcasts SET status='failed',last_error=$1,finished_at=NOW() WHERE id=$2", type(exc).__name__, row["id"])
                await _log_broadcast(db, row["created_by"], f"scheduled id={row['id']} failed: {type(exc).__name__}", "error")
