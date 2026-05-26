import logging, os, time
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from bot.main import is_admin, _log_cmd
import httpx

logger = logging.getLogger(__name__)
RAILWAY_API = os.getenv("SLH_API_URL", "https://slh-api-production.up.railway.app")

async def snapshot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "snapshot")
    if not is_admin(update):
        await update.message.reply_text("Admin only")
        return

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "SLH ECOSYSTEM SNAPSHOT",
        f"Generated: {now}",
        "",
        "=== SERVICES ===",
    ]

    # Check Railway API
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{RAILWAY_API}/api/health")
            lines.append(f"Railway API: OK ({r.status_code})")
    except Exception as e:
        lines.append(f"Railway API: FAIL ({type(e).__name__})")

    # Check Guardian Health
    try:
        from bot.infrastructure import runtime_report as _rr
        await _rr(full=False)
        lines.append("Guardian Bot: OK (running)")
    except Exception as e:
        lines.append(f"Guardian Bot: FAIL ({type(e).__name__})")

    # DB + Redis
    db_url = os.getenv("DATABASE_URL", "")
    redis_url = os.getenv("REDIS_URL", "")
    lines.append(f"Guardian DB: {'OK' if db_url else 'MISSING'}")
    lines.append(f"Guardian Redis: {'OK' if redis_url else 'MISSING'}")

    lines += [
        "",
        "=== BOTS ===",
        "@Grdian_bot      â€” Guardian (Docker port 8002)",
        "@SLH_Claude_bot  â€” AI assistant (NSSM service)",
        "",
        "=== ENDPOINTS ===",
        f"Railway API: {RAILWAY_API}",
        "Website: https://slh.co.il",
        "Support: https://t.me/+Iy57lfQQ3vM5Yjlk",
        "",
        "=== GUARDIAN COMMANDS ===",
        "/system /ticket /tickets /connect /sessions",
        "/admin /vars /gr_ping /gr_check /gr_report",
        "/support /queue /say /guide /disconnect",
        "/snapshot â€” this command",
        "",
        "=== DIRS ===",
        "Guardian: D:\GUARDIAN_ISOLATED",
        "SLH Eco:  D:\SLH_ECOSYSTEM",
        "Claude:   D:\SLH_ECOSYSTEM\slh-claude-bot",
        "",
        "=== QUICK COMMANDS ===",
        "Guardian start: cd D:\GUARDIAN_ISOLATED && docker compose up -d guardian-bot",
        "Claude start:   nssm start SLH_Bot",
        "Status check:   docker compose ps",
        "",
        "=== SHARE THIS WITH AI ===",
        "Paste this snapshot at the start of a new chat to continue development.",
        f"Admin chat_id: {os.getenv('ADMIN_CHAT_ID', '224223270')}",
    ]

    text = chr(10).join(lines)
    await update.message.reply_text(text)

def register_handlers(app):
    app.add_handler(CommandHandler("snapshot", snapshot_cmd))
    logger.info("snapshot_cmd registered")

