import logging, os, uuid
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from bot.main import is_admin, _log_cmd
from bot.infrastructure import get_db_session as get_session

logger = logging.getLogger(__name__)
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

async def ticket_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "ticket")
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: /ticket <description>\n"
            "Example: /ticket My app crashes on startup"
        )
        return
    ticket_id = str(uuid.uuid4())[:8].upper()
    description = " ".join(args)
    user = update.effective_user
    chat = update.effective_chat
    try:
        async with get_session() as db:
            await db.execute(
                "INSERT INTO tickets (ticket_id, user_id, username, description, status, created_at) "
                "VALUES (:tid, :uid, :uname, :desc, 'open', :ts)",
                {"tid": ticket_id, "uid": user.id, "uname": user.username or str(user.id),
                 "desc": description, "ts": datetime.utcnow().isoformat()}
            )
            await db.commit()
    except Exception as e:
        logger.warning("DB save failed, continuing: %s", e)
    await update.message.reply_text(
        f"Ticket #{ticket_id} created\n"
        f"Issue: {description}\n"
        f"Status: OPEN\n"
        f"An admin will contact you shortly."
    )
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_CHAT_ID),
                text=f"NEW TICKET #{ticket_id}\n"
                     f"User: @{user.username or user.id} ({user.id})\n"
                     f"Issue: {description}\n\n"
                     f"/connect {user.id}"
            )
        except Exception as e:
            logger.warning("Admin notify failed: %s", e)

async def tickets_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "tickets")
    if not is_admin(update):
        await update.message.reply_text("Admin only")
        return
    try:
        async with get_session() as db:
            rows = await db.execute(
                "SELECT ticket_id, username, description, status, created_at "
                "FROM tickets ORDER BY created_at DESC LIMIT 10"
            )
            tickets = rows.fetchall()
        if not tickets:
            await update.message.reply_text("No tickets yet")
            return
        lines = ["OPEN TICKETS (last 10):", ""]
        for t in tickets:
            lines.append(f"#{t[0]} [{t[3]}] @{t[1]}: {t[2][:50]}")
        await update.message.reply_text(chr(10).join(lines))
    except Exception as e:
        await update.message.reply_text(f"DB error: {type(e).__name__}: {e}")

def register_handlers(app):
    app.add_handler(CommandHandler("ticket", ticket_cmd))
    app.add_handler(CommandHandler("tickets", tickets_cmd))
    logger.info("ticket handlers registered")
