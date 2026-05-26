from __future__ import annotations
import logging, httpx, os
from telegram import Update
from telegram.ext import ContextTypes
from bot.main import is_admin, _log_cmd

logger = logging.getLogger(__name__)
RAILWAY_API = os.getenv("SLH_API_URL", "https://slh-api-production.up.railway.app")
MONITORED_SERVICES = [("Railway API", f"{RAILWAY_API}/api/health")]

async def system_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "system")
    if not is_admin(update):
        await update.message.reply_text("Admin only")
        return
    lines = ["SYSTEM STATUS", ""]
    async with httpx.AsyncClient(timeout=5) as client:
        for name, url in MONITORED_SERVICES:
            try:
                r = await client.get(url)
                status = "OK" if r.status_code == 200 else f"WARN {r.status_code}"
            except Exception as e:
                status = f"FAIL {type(e).__name__}"
            lines.append(f"{status} {name}")
    try:
        from bot.infrastructure import runtime_report as _rr
        await _rr(full=False)
        lines.append("OK Guardian Health")
    except Exception as e:
        lines.append(f"FAIL Guardian Health: {type(e).__name__}")
    db_url = os.getenv("DATABASE_URL", "")
    redis_url = os.getenv("REDIS_URL", "")
    lines.append("")
    lines.append("DB: " + ("configured" if db_url else "missing"))
    lines.append("Redis: " + ("configured" if redis_url else "missing"))
    await update.message.reply_text(chr(10).join(lines))
