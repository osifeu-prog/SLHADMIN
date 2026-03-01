import os
import logging
import traceback
import json
import time
from pathlib import Path
from collections import deque
from urllib.parse import urlparse

import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.error import Conflict

from dotenv import load_dotenv
load_dotenv(".env.local")  # local only (ignored in git)

from bot.config import BOT_TOKEN, ENV, MODE, ADMIN_CHAT_ID, WEBHOOK_URL
from bot.infrastructure import init_infrastructure, runtime_report

START_TS = time.time()
CMD_HISTORY = deque(maxlen=30)

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
)
logger = logging.getLogger(__name__)


def _global_error_handler(update, context):
    try:
        u = getattr(update, "effective_user", None)
        c = getattr(update, "effective_chat", None)
        uid = getattr(u, "id", None)
        cid = getattr(c, "id", None)
        logger.exception("GLOBAL_ERROR: uid=%s cid=%s update=%s", uid, cid, update)
    except Exception:
        logger.exception("GLOBAL_ERROR: failed to log update context")
if ENV in ("prod", "production"):
    logging.getLogger("httpx").setLevel(logging.WARNING)

ASCII_BANNER = ""
try:
    ASCII_BANNER = Path("assets/banner.txt").read_text(encoding="utf-8")
except Exception:
    ASCII_BANNER = r"""
=====================================
==           SLH  GUARDIAN          ==
=====================================
"""


def is_admin(update: Update) -> bool:
    return bool(ADMIN_CHAT_ID) and str(update.effective_chat.id) == str(ADMIN_CHAT_ID)

def _uptime_s() -> int:
    return int(time.time() - START_TS)

def _git_sha() -> str:
    return (
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("GIT_COMMIT_SHA")
        or os.getenv("COMMIT_SHA")
        or ""
    )

def _mask_bool(v: str | None) -> str:
    return "SET" if v else "MISSING"

def _parse_webhook_path(url: str) -> str:
    p = urlparse(url)
    return p.path.lstrip("/") or "tg/webhook"

def _normalize_webhook_url(url: str) -> str:
    if not url:
        return url
    p = urlparse(url)
    if not p.path or p.path == "/":
        return url.rstrip("/") + "/tg/webhook"
    return url

async def _log_cmd(update: Update, name: str):
    try:
        u = update.effective_user
        c = update.effective_chat
        item = {
            "ts": int(time.time()),
            "cmd": name,
            "chat_id": getattr(c, "id", None),
            "user_id": getattr(u, "id", None),
            "username": getattr(u, "username", None),
        }
        CMD_HISTORY.append(item)
        logger.info(
            "cmd=%s chat_id=%s user_id=%s username=%s",
            name,
            item["chat_id"],
            item["user_id"],
            item["username"],
        )
    except Exception:
        logger.exception("failed to log command")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "start")
    text = (
        f"```\n{ASCII_BANNER.strip()}\n```\n"
        "SLH Security + Ops Control\n\n"
        "×‘×¨×•×ڑ ×”×‘×گ ×œ-.\n"
        "×‍×¢×¨×›×ھ ×œ× ×™×ک×•×¨ ×ھ×©×ھ×™×•×ھ, ×’×™×‘×•×™, × ×™×”×•×œ ×ھ×¤×¢×•×œ, ×•×”×›× ×” ×œ-SaaS ×‍×œ×گ.\n\n"
        "×¤×§×•×“×•×ھ:\n"
        "/status    ×،×ک×ک×•×، DB/Redis/Alembic\n"
        "/menu      ×ھ×¤×¨×™×ک\n"
        "/whoami    ×‍×™ ×گ× ×™\n"
        "/health    ×‍×¦×‘ ×‍×¢×¨×›×ھ\n"
    )
    if is_admin(update):
        text += (
            "\n/admin     ×“×•×— ×گ×“×‍×™×ں\n"
            "/vars      Vars (SET/MISSING)\n"
            "/webhook   Webhook Info\n"
            "/diag      ×“×™×گ×’× ×•×،×ک×™×§×”\n"
            "/pingdb    ×‘×“×™×§×ھ DB latency\n"
            "/pingredis ×‘×“×™×§×ھ Redis latency\n"
        )
    await update.message.reply_text(text, parse_mode="Markdown")

async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "whoami")
    u = update.effective_user
    c = update.effective_chat
    lines = [
        "ًں§¾ WHOAMI",
        f"user_id: {u.id if u else None}",
        f"username: @{u.username}" if u and u.username else "username: (none)",
        f"chat_id: {c.id if c else None}",
        f"chat_type: {c.type if c else None}",
        f"is_admin_chat: {is_admin(update)}",
    ]
    await update.message.reply_text("\n".join(lines))

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "menu")
    lines = [
        "ًں§ھ ×ھ×¤×¨×™×ک ×‘×“×™×§×•×ھ:",
        "/start",
        "/status",
        "/menu",
        "/whoami",
        "/health",
    ]
    if is_admin(update):
        lines += ["", "ًں”گ ×¤×§×•×“×•×ھ ×گ×“×‍×™×ں:", "/admin", "/vars", "/webhook", "/diag", "/pingdb", "/pingredis"]
    await update.message.reply_text("\n".join(lines))

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "status")
    await update.message.reply_text(await runtime_report(full=is_admin(update)))

async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "health")
    sha = _git_sha()
    lines = [
        "ًں«€ HEALTH",
        f"ENV: {ENV}",
        f"MODE: {MODE}",
        f"uptime_s: {_uptime_s()}",
        f"log_level: {LOG_LEVEL}",
    ]
    if sha:
        lines.append(f"git_sha: {sha[:12]}")
    if is_admin(update):
        lines.append(f"webhook_url: {_normalize_webhook_url(WEBHOOK_URL) if WEBHOOK_URL else 'MISSING'}")
    await update.message.reply_text("\n".join(lines))

async def vars_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "vars")
    if not is_admin(update):
        await update.message.reply_text("â›” ×گ×™×ں ×œ×ڑ ×”×¨×©×گ×”.")
        return
    lines = [
        "ًں”گ VARS (SET/MISSING)",
        f"ENV: {ENV}",
        f"MODE: {MODE}",
        f"BOT_TOKEN: {_mask_bool(BOT_TOKEN)}",
        f"DATABASE_URL: {_mask_bool(os.getenv('DATABASE_URL'))}",
        f"REDIS_URL: {_mask_bool(os.getenv('REDIS_URL'))}",
        f"ADMIN_CHAT_ID: {_mask_bool(ADMIN_CHAT_ID)}",
        f"WEBHOOK_URL: {_mask_bool(WEBHOOK_URL)}",
        f"LOG_LEVEL: {_mask_bool(os.getenv('LOG_LEVEL'))}",
        f"OPENAI_API_KEY: {_mask_bool(os.getenv('OPENAI_API_KEY'))}",
    ]
    await update.message.reply_text("\n".join(lines))

async def webhook_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "webhook")
    if not is_admin(update):
        await update.message.reply_text("â›” ×گ×™×ں ×œ×ڑ ×”×¨×©×گ×”.")
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
        data = r.json()
        result = data.get("result", {})
        lines = [
            "ًںھ‌ WEBHOOK INFO",
            f"url: {result.get('url') or ''}",
            f"pending_update_count: {result.get('pending_update_count')}",
            f"last_error_date: {result.get('last_error_date')}",
            f"last_error_message: {result.get('last_error_message')}",
        ]
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.exception("webhook_cmd failed")
        await update.message.reply_text(f"webhook_cmd error: {type(e).__name__}")

async def diag_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "diag")
    if not is_admin(update):
        await update.message.reply_text("â›” ×گ×™×ں ×œ×ڑ ×”×¨×©×گ×”.")
        return
    sha = _git_sha()
    lines = [
        "ًں§ھ DIAG",
        f"env: {ENV}",
        f"mode: {MODE}",
        f"uptime_s: {_uptime_s()}",
        f"log_level: {LOG_LEVEL}",
        f"git_sha: {(sha[:12] if sha else '(none)')}",
        f"webhook_url: {(_normalize_webhook_url(WEBHOOK_URL) if WEBHOOK_URL else 'MISSING')}",
        "",
        "last_cmds:",
    ]
    for item in list(CMD_HISTORY)[-10:]:
        lines.append(f"- {item['ts']} cmd={item['cmd']} user={item.get('username')} chat_id={item.get('chat_id')}")
    await update.message.reply_text("\n".join(lines))

async def pingdb_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "pingdb")
    if not is_admin(update):
        await update.message.reply_text("â›” ×گ×™×ں ×œ×ڑ ×”×¨×©×گ×”.")
        return
    t0 = time.perf_counter()
    ok = False
    err = None
    try:
        # runtime_report already checks DB; we reuse it and time it.
        _ = await runtime_report(full=False)
        ok = True
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    dt_ms = int((time.perf_counter() - t0) * 1000)
    await update.message.reply_text(f"ًں—„ï¸ڈ DB ping: {'OK' if ok else 'FAIL'} ({dt_ms} ms){'' if not err else ' | ' + err}")

async def pingredis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "pingredis")
    if not is_admin(update):
        await update.message.reply_text("â›” ×گ×™×ں ×œ×ڑ ×”×¨×©×گ×”.")
        return
    # Same approach: time infra report (redis is included there).
    t0 = time.perf_counter()
    ok = False
    err = None
    try:
        _ = await runtime_report(full=False)
        ok = True
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    dt_ms = int((time.perf_counter() - t0) * 1000)
    await update.message.reply_text(f"ًں§  Redis ping: {'OK' if ok else 'FAIL'} ({dt_ms} ms){'' if not err else ' | ' + err}")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "admin")
    if not is_admin(update):
        await update.message.reply_text("â›” ×گ×™×ں ×œ×ڑ ×”×¨×©×گ×”.")
        return
    await update.message.reply_text("ًں§¾ BOOT/ADMIN REPORT\n\n" + await runtime_report(full=True))

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    logger.exception("Unhandled error", exc_info=err)
    if isinstance(err, Conflict):
        logger.error("409 Conflict: another instance is polling. Switch to webhook mode or ensure single instance.")

async def post_init(app):
    await init_infrastructure()
    if ADMIN_CHAT_ID:
        await app.bot.send_message(
            chat_id=int(ADMIN_CHAT_ID),
            text="ًں§¾ BOOT/ADMIN REPORT\n\n" + await runtime_report(full=True),
        )

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("health", health_cmd))
    app.add_handler(CommandHandler("vars", vars_cmd))
    app.add_handler(CommandHandler("webhook", webhook_cmd))
    app.add_handler(CommandHandler("diag", diag_cmd))
    app.add_handler(CommandHandler("pingdb", pingdb_cmd))
    app.add_handler(CommandHandler("pingredis", pingredis_cmd))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("admin", admin_cmd))

    print("Guardian SaaS started")

    mode = (MODE or "polling").lower()

    if mode == "webhook":
        if not WEBHOOK_URL:
            raise ValueError("WEBHOOK_URL not set for webhook mode")

        listen = "0.0.0.0"
        port = int(os.getenv("PORT", "8080"))

        webhook_url = _normalize_webhook_url(WEBHOOK_URL)
        url_path = _parse_webhook_path(webhook_url)

        app.add_error_handler(_global_error_handler)

        app.run_webhook(
            listen=listen,
            port=port,
            url_path=url_path,
            webhook_url=webhook_url,
            drop_pending_updates=True,
        )
    else:
        raise RuntimeError("Polling disabled. Use webhook mode only.")

if __name__ == "__main__":
    main()

