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
        "\u05d1\u05e8\u05d5\u05da \u05d4\u05d1\u05d0 \u05dc-SLH Guardian.\n"
        "\u05de\u05e2\u05e8\u05db\u05ea \u05dc\u05e0\u05d9\u05d8\u05d5\u05e8 \u05ea\u05e9\u05ea\u05d9\u05d5\u05ea, \u05d2\u05d9\u05d1\u05d5\u05d9, \u05e0\u05d9\u05d4\u05d5\u05dc \u05ea\u05e4\u05e2\u05d5\u05dc, \u05d5\u05d4\u05db\u05e0\u05d4 \u05dc-SaaS \u05de\u05dc\u05d0.\n\n"
        "\u05e4\u05e7\u05d5\u05d3\u05d5\u05ea:\n"
        "/status    \u05e1\u05d8\u05d8\u05d5\u05e1 DB/Redis/Alembic\n"
        "/menu      \u05ea\u05e4\u05e8\u05d9\u05d8\n"
        "/whoami    \u05de\u05d9 \u05d0\u05e0\u05d9\n"
        "/health    \u05de\u05e6\u05d1 \u05de\u05e2\u05e8\u05db\u05ea\n"
        "/support   \U0001f6ce\ufe0f \u05d1\u05e7\u05e9 \u05ea\u05de\u05d9\u05db\u05d4 \u05de\u05e8\u05d7\u05d5\u05e7\n"
        "/ticket    \U0001f3ab \u05e4\u05ea\u05d7 \u05db\u05e8\u05d8\u05d9\u05e1 \u05ea\u05de\u05d9\u05db\u05d4\n"
        "/system    \U0001f5a5 \u05e1\u05d8\u05d8\u05d5\u05e1 \u05de\u05e2\u05e8\u05db\u05ea\n"
        "/snapshot  \U0001f4f8 \u05e1\u05e0\u05e4\u05e9\u05d5\u05d8 \u05de\u05e2\u05e8\u05db\u05ea\n"
    )
    if is_admin(update):
        text += (
            "\n/admin     \u05d3\u05d5\u05d7 \u05d0\u05d3\u05de\u05d9\u05df\n"
            "/vars      Vars (SET/MISSING)\n"
            "/webhook   Webhook Info\n"
            "/diag      \u05d3\u05d9\u05d0\u05d2\u05e0\u05d5\u05e1\u05d8\u05d9\u05e7\u05d4\n"
            "/pingdb    \u05d1\u05d3\u05d9\u05e7\u05ea DB latency\n"
            "/pingredis \u05d1\u05d3\u05d9\u05e7\u05ea Redis latency\n"
            "\n\U0001f6ce\ufe0f \u05ea\u05de\u05d9\u05db\u05d4 \u05de\u05e8\u05d7\u05d5\u05e7 / Remote Support:\n"
            "/queue       \u05d1\u05e7\u05e9\u05d5\u05ea \u05de\u05de\u05ea\u05d9\u05e0\u05d5\u05ea\n"
            "/connect     \u05d4\u05ea\u05d7\u05dc \u05e1\u05e9\u05df\n"
            "/say         \u05e9\u05dc\u05d7 \u05d4\u05d5\u05d3\u05e2\u05d4\n"
            "/guide       \u05e9\u05dc\u05d1 \u05d4\u05d3\u05e8\u05db\u05d4\n"
            "/checklist   \u05e8\u05e9\u05d9\u05de\u05ea \u05d1\u05d3\u05d9\u05e7\u05d4\n"
            "/screenshot  \u05d1\u05e7\u05e9 \u05e6\u05d9\u05dc\u05d5\u05dd \u05de\u05e1\u05da\n"
            "/sysinfo     \u05de\u05d9\u05d3\u05e2 \u05de\u05e2\u05e8\u05db\u05ea\n"
            "/quickfix    \u05ea\u05d9\u05e7\u05d5\u05df \u05de\u05d4\u05d9\u05e8\n"
            "/sessions    \u05e1\u05e9\u05e0\u05d9\u05dd \u05e4\u05e2\u05d9\u05dc\u05d9\u05dd\n"
            "/disconnect  \u05e1\u05d9\u05d5\u05dd \u05e1\u05e9\u05df\n"
            "\n\U0001f4f1 \u05d0\u05d1\u05d7\u05d5\u05df \u05d8\u05dc\u05e4\u05d5\u05df / Phone Diag:\n"
            "/phonediag   \u05d0\u05d1\u05d7\u05d5\u05df \u05de\u05db\u05e9\u05d9\u05e8\n"
            "/phonefix    \u05ea\u05d9\u05e7\u05d5\u05df \u05d8\u05dc\u05e4\u05d5\u05df\n"
            "/appscan     \u05d1\u05d3\u05d9\u05e7\u05ea \u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d5\u05ea\n"
        )
    await update.message.reply_text(text, parse_mode="Markdown")

async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "whoami")
    u = update.effective_user
    c = update.effective_chat
    lines = [
        "\U0001f9fe WHOAMI",
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
        "\U0001f9ea \u05ea\u05e4\u05e8\u05d9\u05d8 \u05d1\u05d3\u05d9\u05e7\u05d5\u05ea:",
        "/start",
        "/status",
        "/menu",
        "/whoami",
        "/health",
    ]
    if is_admin(update):
        lines += ["", "\U0001f4cc \u05e4\u05e7\u05d5\u05d3\u05d5\u05ea \u05d0\u05d3\u05de\u05d9\u05df:", "/admin", "/vars", "/webhook", "/diag", "/pingdb", "/pingredis"]
    await update.message.reply_text("\n".join(lines))

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "status")
    await update.message.reply_text(await runtime_report(full=is_admin(update)))

async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "health")
    sha = _git_sha()
    lines = [
        "\U0001fac0 HEALTH",
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
        await update.message.reply_text("\u26d4 \u05d0\u05d9\u05df \u05dc\u05da \u05d4\u05e8\u05e9\u05d0\u05d4.")
        return
    lines = [
        "\U0001f4cc VARS (SET/MISSING)",
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
        await update.message.reply_text("\u26d4 \u05d0\u05d9\u05df \u05dc\u05da \u05d4\u05e8\u05e9\u05d0\u05d4.")
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
        data = r.json()
        result = data.get("result", {})
        lines = [
            "\U0001fa9d WEBHOOK INFO",
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
        await update.message.reply_text("\u26d4 \u05d0\u05d9\u05df \u05dc\u05da \u05d4\u05e8\u05e9\u05d0\u05d4.")
        return
    sha = _git_sha()
    lines = [
        "\U0001f9ea DIAG",
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
        await update.message.reply_text("\u26d4 \u05d0\u05d9\u05df \u05dc\u05da \u05d4\u05e8\u05e9\u05d0\u05d4.")
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
    await update.message.reply_text(f"\U0001f5c4\ufe0f DB ping: {'OK' if ok else 'FAIL'} ({dt_ms} ms){'' if not err else ' | ' + err}")

async def pingredis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "pingredis")
    if not is_admin(update):
        await update.message.reply_text("\u26d4 \u05d0\u05d9\u05df \u05dc\u05da \u05d4\u05e8\u05e9\u05d0\u05d4.")
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
    await update.message.reply_text(f"\U0001f9e0 Redis ping: {'OK' if ok else 'FAIL'} ({dt_ms} ms){'' if not err else ' | ' + err}")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "admin")
    if not is_admin(update):
        await update.message.reply_text("\u26d4 \u05d0\u05d9\u05df \u05dc\u05da \u05d4\u05e8\u05e9\u05d0\u05d4.")
        return
    await update.message.reply_text("\U0001f9fe BOOT/ADMIN REPORT\n\n" + await runtime_report(full=True))

# ============================================================
# REMOTE SUPPORT ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â TeamViewer-like customer assistance
# ============================================================
_support_sessions = {}  # {client_chat_id: {admin_id, started, notes, steps}}
_support_queue = []     # [{chat_id, username, issue, ts}]

async def support_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "support")
    args = context.args or []
    issue = " ".join(args) if args else "General help needed"
    uid = update.effective_user.id
    uname = update.effective_user.username or str(uid)
    entry = {"chat_id": uid, "username": uname, "issue": issue, "ts": time.time()}
    _support_queue[:] = [q for q in _support_queue if q["chat_id"] != uid]
    _support_queue.append(entry)
    await update.effective_message.reply_text(
        f"\U0001f6ce\ufe0f \u05d1\u05e7\u05e9\u05ea \u05ea\u05de\u05d9\u05db\u05d4 \u05e0\u05e9\u05dc\u05d7\u05d4!\n"
        f"\u05d1\u05e2\u05d9\u05d4: {issue}\n\u05de\u05d7\u05db\u05d4 \u05dc\u05ea\u05e9\u05d5\u05d1\u05d4...\n\n"
        f"\U0001f6ce\ufe0f Support request sent!\nIssue: {issue}\nWaiting for admin..."
    )
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID),
                text=f"\U0001f6a8 NEW SUPPORT REQUEST\nUser: @{uname} ({uid})\nIssue: {issue}\n\n/connect {uid}")
        except Exception: pass

async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "queue")
    if not is_admin(update):
        await update.effective_message.reply_text("\u26d4 Admin only"); return
    if not _support_queue:
        await update.effective_message.reply_text("\u2705 No pending requests"); return
    lines = ["\U0001f4cb SUPPORT QUEUE:"]
    for i, q in enumerate(_support_queue, 1):
        age = int(time.time() - q["ts"])
        lines.append(f"{i}. @{q['username']} ({q['chat_id']}) \u2014 {q['issue']} [{age//60}m ago]")
    lines.append("\n/connect <user_id> to start")
    await update.effective_message.reply_text("\n".join(lines))

async def connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "connect")
    if not is_admin(update):
        await update.effective_message.reply_text("\u26d4 Admin only"); return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /connect <user_id>"); return
    client_id = int(args[0])
    _support_sessions[client_id] = {"admin_id": update.effective_user.id, "started": time.time(), "notes": [], "steps": []}
    _support_queue[:] = [q for q in _support_queue if q["chat_id"] != client_id]
    await update.effective_message.reply_text(
        f"\U0001f50c SESSION STARTED with {client_id}\n\n"
        f"/say {client_id} <msg> \u2014 Send message\n"
        f"/guide {client_id} <step> \u2014 Guide step\n"
        f"/checklist {client_id} <a|b|c> \u2014 Checklist\n"
        f"/screenshot {client_id} \u2014 Request screenshot\n"
        f"/sysinfo {client_id} \u2014 System info\n"
        f"/quickfix {client_id} <template> \u2014 Quick fix\n"
        f"/note {client_id} <note> \u2014 Internal note\n"
        f"/disconnect {client_id} \u2014 End session\n"
        f"/sessions \u2014 All active sessions"
    )
    try:
        await context.bot.send_message(chat_id=client_id,
            text="\U0001f50c \u05d4\u05ea\u05d7\u05d1\u05e8\u05ea \u05dc\u05e1\u05e9\u05df \u05ea\u05de\u05d9\u05db\u05d4!\n\U0001f50c Connected to support!\n\n\u05d4\u05d8\u05db\u05e0\u05d0\u05d9 \u05de\u05d7\u05d5\u05d1\u05e8 \u05d5\u05d9\u05e1\u05d9\u05d9\u05e2 \u05dc\u05da.\nOur technician will assist you.\n\u05e9\u05dc\u05d7 \u05d4\u05d5\u05d3\u05e2\u05d5\u05ea, \u05e6\u05d9\u05dc\u05d5\u05de\u05d9\u05dd \u05d5\u05ea\u05de\u05d5\u05e0\u05d5\u05ea.")
    except Exception as e:
        await update.effective_message.reply_text(f"\u26a0 Could not reach {client_id}: {e}")

async def say_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "say")
    if not is_admin(update): return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /say <user_id> <message>"); return
    try:
        await context.bot.send_message(chat_id=int(args[0]), text=f"\U0001f9d1\u200d\U0001f4bb \u05d8\u05db\u05e0\u05d0\u05d9 SLH:\n{' '.join(args[1:])}")
        await update.effective_message.reply_text(f"\u2705 Sent to {args[0]}")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c {e}")

async def guide_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "guide")
    if not is_admin(update): return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /guide <user_id> <step>"); return
    client_id = int(args[0])
    step_text = " ".join(args[1:])
    s = _support_sessions.get(client_id, {"steps": []})
    s.setdefault("steps", []).append(step_text)
    n = len(s["steps"])
    try:
        await context.bot.send_message(chat_id=client_id, text=f"\U0001f4cb \u05e9\u05dc\u05d1 {n} / Step {n}:\n{step_text}")
        await update.effective_message.reply_text(f"\u2705 Step {n} sent")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c {e}")

async def checklist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "checklist")
    if not is_admin(update): return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /checklist <user_id> item1 | item2 | item3"); return
    client_id = int(args[0])
    items = [i.strip() for i in " ".join(args[1:]).split("|") if i.strip()]
    cl = "\n".join([f"\u2610 {i}" for i in items])
    try:
        await context.bot.send_message(chat_id=client_id, text=f"\U0001f4dd \u05e8\u05e9\u05d9\u05de\u05ea \u05d1\u05d3\u05d9\u05e7\u05d4 / Checklist:\n\n{cl}\n\n\u05e1\u05de\u05df \u05d1-\u2705 / Mark done with \u2705")
        await update.effective_message.reply_text(f"\u2705 Checklist ({len(items)} items) sent")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c {e}")

async def screenshot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "screenshot")
    if not is_admin(update): return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /screenshot <user_id>"); return
    try:
        await context.bot.send_message(chat_id=int(args[0]),
            text="\U0001f4f8 \u05d4\u05d8\u05db\u05e0\u05d0\u05d9 \u05de\u05d1\u05e7\u05e9 \u05e6\u05d9\u05dc\u05d5\u05dd \u05de\u05e1\u05da\n\U0001f4f8 Screenshot requested\n\n\u05e6\u05dc\u05dd \u05d5\u05e9\u05dc\u05d7 \u05db\u05ea\u05de\u05d5\u05e0\u05d4 / Take & send as photo\nWindows: Win+Shift+S\nMac: Cmd+Shift+4")
        await update.effective_message.reply_text(f"\u2705 Screenshot request sent to {args[0]}")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c {e}")

async def sysinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "sysinfo")
    if not is_admin(update): return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /sysinfo <user_id>"); return
    try:
        await context.bot.send_message(chat_id=int(args[0]),
            text="\U0001f4bb \u05e4\u05e8\u05d8\u05d9 \u05de\u05e2\u05e8\u05db\u05ea / System info:\n\n\u05e4\u05ea\u05d7 CMD \u05d5\u05d4\u05e8\u05e5 / Open CMD and run:\n\nsysteminfo | findstr /B /C:\"OS\" /C:\"System\" /C:\"Total\"\n\nipconfig | findstr /i \"IPv4 DNS Default\"\n\n\u05d4\u05e2\u05ea\u05e7 \u05ea\u05d5\u05e6\u05d0\u05d4 \u05db\u05d0\u05df / Paste output here")
        await update.effective_message.reply_text(f"\u2705 Sysinfo request sent to {args[0]}")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c {e}")

async def note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "note")
    if not is_admin(update): return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /note <user_id> <note>"); return
    s = _support_sessions.get(int(args[0]))
    if not s:
        await update.effective_message.reply_text(f"\u26a0 No session for {args[0]}"); return
    s["notes"].append({"text": " ".join(args[1:]), "ts": time.time()})
    await update.effective_message.reply_text(f"\U0001f4dd Note saved ({len(s['notes'])} total)")

async def disconnect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "disconnect")
    if not is_admin(update): return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /disconnect <user_id>"); return
    client_id = int(args[0])
    s = _support_sessions.pop(client_id, None)
    if not s:
        await update.effective_message.reply_text(f"No session for {client_id}"); return
    dur = int(time.time() - s.get("started", time.time()))
    try:
        await context.bot.send_message(chat_id=client_id,
            text="\u2705 \u05d4\u05e1\u05e9\u05df \u05d4\u05e1\u05ea\u05d9\u05d9\u05dd. \u05ea\u05d5\u05d3\u05d4!\n\u2705 Session ended. Thank you!\n\n\u05e6\u05e8\u05d9\u05da \u05e2\u05d5\u05d3 \u05e2\u05d6\u05e8\u05d4? \u05e9\u05dc\u05d7 /support")
    except Exception: pass
    await update.effective_message.reply_text(f"\U0001f50c SESSION CLOSED\nClient: {client_id}\nDuration: {dur//60}m {dur%60}s\nSteps: {len(s.get('steps',[]))}\nNotes: {len(s.get('notes',[]))}")

async def sessions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "sessions")
    if not is_admin(update): return
    if not _support_sessions:
        await update.effective_message.reply_text("\u2705 No active sessions"); return
    lines = ["\U0001f50c ACTIVE SESSIONS:"]
    for cid, s in _support_sessions.items():
        dur = int(time.time() - s.get("started", time.time()))
        lines.append(f"\u2022 {cid} \u2014 {dur//60}m \u2014 {len(s.get('steps',[]))} steps, {len(s.get('notes',[]))} notes")
    lines.append(f"\nQueue: {len(_support_queue)} waiting")
    await update.effective_message.reply_text("\n".join(lines))

async def quickfix_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "quickfix")
    if not is_admin(update): return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text(
            "\U0001f527 QUICKFIX TEMPLATES:\n\n"
            "/quickfix <uid> restart\n/quickfix <uid> cache\n/quickfix <uid> dns\n"
            "/quickfix <uid> network\n/quickfix <uid> update\n/quickfix <uid> safe\n/quickfix <uid> disk")
        return
    client_id = int(args[0])
    fixes = {
        "restart": "\U0001f504 \u05d4\u05e4\u05e2\u05dc\u05d4 \u05de\u05d7\u05d3\u05e9 / Restart:\n1. \u05e9\u05de\u05d5\u05e8 \u05e2\u05d1\u05d5\u05d3\u05d4 / Save work\n2. Start > Power > Restart\n3. \u05d4\u05de\u05ea\u05df \u05dc\u05d0\u05ea\u05d7\u05d5\u05dc / Wait for reboot\n4. \u05d1\u05d3\u05d5\u05e7 / Check if fixed",
        "cache": "\U0001f9f9 \u05e0\u05d9\u05e7\u05d5\u05d9 \u05de\u05d8\u05de\u05d5\u05df / Clear Cache:\n1. Ctrl+Shift+Delete\n2. \u05e1\u05de\u05df \u05d4\u05db\u05dc / Select all\n3. Clear / \u05e0\u05e7\u05d4\n4. \u05e1\u05d2\u05d5\u05e8 \u05d3\u05e4\u05d3\u05e4\u05df / Close & reopen",
        "dns": "\U0001f310 DNS Flush:\n1. \u05e4\u05ea\u05d7 CMD \u05db\u05de\u05e0\u05d4\u05dc / Open CMD as admin\n2. ipconfig /flushdns\n3. ipconfig /release\n4. ipconfig /renew",
        "network": "\U0001f4e1 \u05d0\u05d9\u05e4\u05d5\u05e1 \u05e8\u05e9\u05ea / Network Reset:\n1. CMD \u05db\u05de\u05e0\u05d4\u05dc / CMD as admin\n2. netsh winsock reset\n3. netsh int ip reset\n4. \u05d4\u05e4\u05e2\u05dc \u05de\u05d7\u05d3\u05e9 / Restart",
        "update": "\U0001f4e6 \u05e2\u05d3\u05db\u05d5\u05e0\u05d9\u05dd / Updates:\n1. Settings > Update & Security\n2. Check for updates\n3. Install all\n4. Restart if needed",
        "safe": "\U0001f6e1 Safe Mode:\n1. Settings > Recovery > Restart now\n2. Troubleshoot > Advanced\n3. Startup Settings > Restart\n4. Press F5 (Safe Mode + Network)",
        "disk": "\U0001f4be Disk Cleanup:\n1. \u05e4\u05ea\u05d7 / Run: cleanmgr\n2. \u05d1\u05d7\u05e8 C: / Select C:\n3. \u05e1\u05de\u05df \u05d4\u05db\u05dc / Select all\n4. Clean up system files"
    }
    txt = fixes.get(args[1].lower(), f"\u26a0 Unknown: {args[1]}. Options: restart, cache, dns, network, update, safe, disk")
    try:
        await context.bot.send_message(chat_id=client_id, text=txt)
        await update.effective_message.reply_text(f"\u2705 Quickfix '{args[1]}' sent to {client_id}")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c {e}")

# ============================================================
# PHONE DIAGNOSTICS ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Remote phone troubleshooting
# ============================================================

async def phonediag_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /phonediag <user_id> ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â send full phone diagnostic checklist"""
    await _log_cmd(update, "phonediag")
    if not is_admin(update): return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /phonediag <user_id>"); return
    client_id = int(args[0])
    try:
        await context.bot.send_message(chat_id=client_id, text=(
            "\U0001f4f1 \u05d0\u05d1\u05d7\u05d5\u05df \u05de\u05db\u05e9\u05d9\u05e8 / Phone Diagnostics\n\n"
            "\u05d0\u05e0\u05d0 \u05e9\u05dc\u05d7 \u05dc\u05d9 \u05d0\u05ea \u05d4\u05de\u05d9\u05d3\u05e2 \u05d4\u05d1\u05d0 / Please send me:\n\n"
            "1\ufe0f\u20e3 \u05e6\u05d9\u05dc\u05d5\u05dd \u05de\u05e1\u05da \u05e9\u05dc Settings > About Phone\n"
            "   Screenshot of Settings > About Phone\n\n"
            "2\ufe0f\u20e3 \u05e6\u05d9\u05dc\u05d5\u05dd \u05de\u05e1\u05da \u05e9\u05dc Settings > Storage\n"
            "   Screenshot of Settings > Storage\n\n"
            "3\ufe0f\u20e3 \u05e6\u05d9\u05dc\u05d5\u05dd \u05de\u05e1\u05da \u05e9\u05dc Settings > Battery\n"
            "   Screenshot of Settings > Battery\n\n"
            "4\ufe0f\u20e3 \u05d4\u05d0\u05dd \u05d4\u05d8\u05dc\u05e4\u05d5\u05df \u05d7\u05dd \u05dc\u05de\u05d2\u05e2?\n"
            "   Is the phone hot to touch?\n\n"
            "5\ufe0f\u20e3 \u05de\u05ea\u05d9 \u05d4\u05ea\u05d7\u05d9\u05dc\u05d4 \u05d4\u05d1\u05e2\u05d9\u05d4?\n"
            "   When did the problem start?\n\n"
            "\U0001f4f8 \u05e9\u05dc\u05d7 \u05e6\u05d9\u05dc\u05d5\u05de\u05d9\u05dd \u05db\u05d0\u05df / Send screenshots here"
        ))
        await update.effective_message.reply_text(f"\u2705 Phone diagnostic request sent to {client_id}")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c {e}")

async def phonefix_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /phonefix <user_id> <template> ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â send phone fix templates"""
    await _log_cmd(update, "phonefix")
    if not is_admin(update): return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text(
            "\U0001f4f1 PHONEFIX TEMPLATES:\n\n"
            "/phonefix <uid> clear_cache \u2014 \u05e0\u05d9\u05e7\u05d5\u05d9 \u05de\u05d8\u05de\u05d5\u05df \u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d5\u05ea\n"
            "/phonefix <uid> storage \u2014 \u05e4\u05d9\u05e0\u05d5\u05d9 \u05d0\u05d7\u05e1\u05d5\u05df\n"
            "/phonefix <uid> restart \u2014 \u05d4\u05e4\u05e2\u05dc\u05d4 \u05de\u05d7\u05d3\u05e9\n"
            "/phonefix <uid> safe_mode \u2014 \u05de\u05e6\u05d1 \u05d1\u05d8\u05d5\u05d7\n"
            "/phonefix <uid> virus \u2014 \u05e1\u05e8\u05d9\u05e7\u05ea \u05d5\u05d9\u05e8\u05d5\u05e1\u05d9\u05dd\n"
            "/phonefix <uid> battery \u2014 \u05d1\u05e2\u05d9\u05d5\u05ea \u05e1\u05d5\u05dc\u05dc\u05d4\n"
            "/phonefix <uid> network \u2014 \u05d1\u05e2\u05d9\u05d5\u05ea \u05e8\u05e9\u05ea\n"
            "/phonefix <uid> factory \u2014 \u05d0\u05d9\u05e4\u05d5\u05e1 \u05dc\u05de\u05e6\u05d1 \u05d9\u05e6\u05e8\u05df"
        ); return
    client_id = int(args[0])
    template = args[1].lower()
    fixes = {
        "clear_cache": (
            "\U0001f9f9 \u05e0\u05d9\u05e7\u05d5\u05d9 \u05de\u05d8\u05de\u05d5\u05df / Clear App Cache:\n\n"
            "Android:\n1. Settings > Apps\n2. \u05d1\u05d7\u05e8 \u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d4 \u05d1\u05e2\u05d9\u05d9\u05ea\u05d9\u05ea / Select problem app\n"
            "3. Storage > Clear Cache\n4. \u05d0\u05dd \u05dc\u05d0 \u05e2\u05d5\u05d6\u05e8: Clear Data\n\n"
            "iPhone:\n1. Settings > General > iPhone Storage\n2. \u05d1\u05d7\u05e8 \u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d4 / Select app\n3. Offload App > Reinstall"
        ),
        "storage": (
            "\U0001f4be \u05e4\u05d9\u05e0\u05d5\u05d9 \u05d0\u05d7\u05e1\u05d5\u05df / Free Storage:\n\n"
            "1. \u05de\u05d7\u05e7 \u05ea\u05de\u05d5\u05e0\u05d5\u05ea \u05d9\u05e9\u05e0\u05d5\u05ea / Delete old photos+videos\n"
            "2. \u05de\u05d7\u05e7 \u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d5\u05ea \u05dc\u05d0 \u05d1\u05e9\u05d9\u05de\u05d5\u05e9 / Remove unused apps\n"
            "3. \u05e0\u05e7\u05d4 \u05d4\u05d5\u05e8\u05d3\u05d5\u05ea \u05d9\u05e9\u05e0\u05d5\u05ea / Clear old downloads\n"
            "4. WhatsApp > Settings > Storage > Clean Up\n"
            "5. Telegram > Settings > Data > Storage Usage > Clear"
        ),
        "restart": (
            "\U0001f504 \u05d4\u05e4\u05e2\u05dc\u05d4 \u05de\u05d7\u05d3\u05e9 / Phone Restart:\n\n"
            "1. \u05dc\u05d7\u05e5 \u05d0\u05e8\u05d5\u05da \u05e2\u05dc \u05db\u05e4\u05ea\u05d5\u05e8 \u05d4\u05e4\u05e2\u05dc\u05d4 / Hold power button\n"
            "2. \u05d1\u05d7\u05e8 Restart / \u05d4\u05e4\u05e2\u05dc \u05de\u05d7\u05d3\u05e9\n"
            "3. \u05d4\u05de\u05ea\u05df 2 \u05d3\u05e7\u05d5\u05ea / Wait 2 minutes\n"
            "4. \u05d1\u05d3\u05d5\u05e7 \u05d0\u05dd \u05d4\u05d1\u05e2\u05d9\u05d4 \u05e0\u05e4\u05ea\u05e8\u05d4 / Check if fixed"
        ),
        "safe_mode": (
            "\U0001f6e1 \u05de\u05e6\u05d1 \u05d1\u05d8\u05d5\u05d7 / Safe Mode:\n\n"
            "Android:\n1. \u05dc\u05d7\u05e5 \u05d0\u05e8\u05d5\u05da \u05e2\u05dc Power / Hold power\n"
            "2. \u05dc\u05d7\u05e5 \u05d0\u05e8\u05d5\u05da \u05e2\u05dc 'Power Off' / Long-press Power Off\n"
            "3. \u05d1\u05d7\u05e8 'Safe Mode' / Tap Safe Mode\n"
            "4. \u05d1\u05d3\u05d5\u05e7 \u05d0\u05dd \u05d4\u05d1\u05e2\u05d9\u05d4 \u05e0\u05de\u05e9\u05db\u05ea / Test if issue persists\n\n"
            "iPhone:\n1. \u05db\u05d1\u05d4 \u05d5\u05d4\u05e4\u05e2\u05dc \u05de\u05d7\u05d3\u05e9 / Shutdown & restart\n"
            "2. \u05d4\u05d7\u05d6\u05e7 Vol Down \u05d1\u05d6\u05de\u05df \u05d0\u05ea\u05d7\u05d5\u05dc / Hold Vol Down during boot"
        ),
        "virus": (
            "\U0001f9f9 \u05e1\u05e8\u05d9\u05e7\u05ea \u05d5\u05d9\u05e8\u05d5\u05e1\u05d9\u05dd / Virus Scan:\n\n"
            "Android:\n1. \u05d4\u05d5\u05e8\u05d3 Malwarebytes \u05de-Play Store\n"
            "2. \u05d4\u05e8\u05e5 \u05e1\u05e8\u05d9\u05e7\u05d4 \u05de\u05dc\u05d0\u05d4 / Run full scan\n"
            "3. \u05de\u05d7\u05e7 \u05db\u05dc \u05de\u05d4 \u05e9\u05e0\u05de\u05e6\u05d0 / Delete all threats\n"
            "4. Settings > Apps > \u05de\u05d7\u05e7 \u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d5\u05ea \u05d7\u05e9\u05d5\u05d3\u05d5\u05ea / Remove suspicious apps\n"
            "5. \u05d1\u05d3\u05d5\u05e7: Settings > Security > Google Play Protect\n\n"
            "iPhone:\n1. \u05e2\u05d3\u05db\u05df iOS \u05dc\u05d2\u05e8\u05e1\u05d4 \u05d0\u05d7\u05e8\u05d5\u05e0\u05d4 / Update iOS\n"
            "2. \u05de\u05d7\u05e7 \u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d5\u05ea \u05dc\u05d0 \u05de\u05d5\u05db\u05e8\u05d5\u05ea / Remove unknown apps\n"
            "3. Settings > Safari > Clear History\n"
            "4. \u05d0\u05dd \u05dc\u05d0 \u05e2\u05d5\u05d6\u05e8: \u05d0\u05d9\u05e4\u05d5\u05e1 \u05dc\u05de\u05e6\u05d1 \u05d9\u05e6\u05e8\u05df / Factory reset as last resort"
        ),
        "battery": (
            "\U0001f50b \u05d1\u05e2\u05d9\u05d5\u05ea \u05e1\u05d5\u05dc\u05dc\u05d4 / Battery Fix:\n\n"
            "1. Settings > Battery > \u05d1\u05d3\u05d5\u05e7 \u05de\u05d4 \u05e6\u05d5\u05e8\u05da \u05d4\u05e8\u05d1\u05d4 / Check top drainers\n"
            "2. \u05db\u05d1\u05d4 \u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d5\u05ea \u05e8\u05e7\u05e2 / Kill background apps\n"
            "3. \u05d4\u05e4\u05e2\u05dc Low Power Mode\n"
            "4. \u05db\u05d1\u05d4 Location \u05dc\u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d5\u05ea \u05dc\u05d0 \u05d7\u05d9\u05d5\u05e0\u05d9\u05d5\u05ea / Disable location for non-essential apps\n"
            "5. \u05d4\u05d5\u05e8\u05d3 \u05d1\u05d4\u05d9\u05e8\u05d5\u05ea \u05de\u05e1\u05da / Lower brightness\n"
            "6. \u05d4\u05e4\u05e2\u05dc \u05de\u05d7\u05d3\u05e9 / Restart phone"
        ),
        "network": (
            "\U0001f4e1 \u05d1\u05e2\u05d9\u05d5\u05ea \u05e8\u05e9\u05ea / Network Fix:\n\n"
            "1. \u05d4\u05e4\u05e2\u05dc \u05de\u05e6\u05d1 \u05d8\u05d9\u05e1\u05d4 / Toggle Airplane mode ON then OFF\n"
            "2. \u05db\u05d1\u05d4 WiFi \u05d5\u05d4\u05ea\u05d7\u05d1\u05e8 \u05de\u05d7\u05d3\u05e9 / Forget WiFi & reconnect\n"
            "3. Settings > General > Reset Network Settings\n"
            "4. \u05d4\u05e4\u05e2\u05dc \u05de\u05d7\u05d3\u05e9 \u05d0\u05ea \u05d4\u05e8\u05d0\u05d5\u05d8\u05e8 / Restart router\n"
            "5. \u05e0\u05e1\u05d4 DNS \u05d9\u05d3\u05e0\u05d9: WiFi > DNS > 8.8.8.8\n"
            "6. \u05d0\u05dd \u05dc\u05d0 \u05e2\u05d5\u05d1\u05d3: \u05d4\u05d5\u05e6\u05d0 \u05d5\u05d4\u05db\u05e0\u05e1 SIM / Eject & reinsert SIM"
        ),
        "factory": (
            "\u26a0\ufe0f \u05d0\u05d9\u05e4\u05d5\u05e1 \u05dc\u05de\u05e6\u05d1 \u05d9\u05e6\u05e8\u05df / FACTORY RESET:\n\n"
            "\u26a0\ufe0f \u05d6\u05d4 \u05d9\u05de\u05d7\u05e7 \u05d4\u05db\u05dc! \u05d2\u05d1\u05d4 \u05e7\u05d5\u05d3\u05dd!\n"
            "\u26a0\ufe0f This will ERASE everything! Backup first!\n\n"
            "\u05d2\u05d9\u05d1\u05d5\u05d9 / Backup:\n"
            "1. Google/iCloud \u05d2\u05d9\u05d1\u05d5\u05d9 \u05ea\u05de\u05d5\u05e0\u05d5\u05ea + \u05d0\u05e0\u05e9\u05d9 \u05e7\u05e9\u05e8\n"
            "2. WhatsApp > Settings > Chats > Backup\n"
            "3. \u05d4\u05e2\u05ea\u05e7 \u05ea\u05de\u05d5\u05e0\u05d5\u05ea \u05d7\u05e9\u05d5\u05d1\u05d5\u05ea \u05dc\u05de\u05d7\u05e9\u05d1 / Save important photos to PC\n\n"
            "\u05d0\u05d9\u05e4\u05d5\u05e1 / Reset:\n"
            "Android: Settings > System > Reset > Erase all data\n"
            "iPhone: Settings > General > Transfer or Reset > Erase All"
        )
    }
    txt = fixes.get(template, f"\u26a0 Unknown: {template}. Options: clear_cache, storage, restart, safe_mode, virus, battery, network, factory")
    try:
        await context.bot.send_message(chat_id=client_id, text=txt)
        await update.effective_message.reply_text(f"\u2705 Phone fix '{template}' sent to {client_id}")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c {e}")

async def appscan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /appscan <user_id> ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â guide user through checking suspicious apps"""
    await _log_cmd(update, "appscan")
    if not is_admin(update): return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /appscan <user_id>"); return
    client_id = int(args[0])
    try:
        await context.bot.send_message(chat_id=client_id, text=(
            "\U0001f50d \u05d1\u05d3\u05d9\u05e7\u05ea \u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d5\u05ea / App Security Check:\n\n"
            "1\ufe0f\u20e3 \u05e4\u05ea\u05d7 Settings > Apps / Open Settings > Apps\n\n"
            "2\ufe0f\u20e3 \u05d7\u05e4\u05e9 \u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d5\u05ea \u05dc\u05d0 \u05de\u05d5\u05db\u05e8\u05d5\u05ea / Look for apps you don't recognize\n\n"
            "3\ufe0f\u20e3 \u05e6\u05dc\u05dd \u05de\u05e1\u05da \u05e9\u05dc \u05e8\u05e9\u05d9\u05de\u05ea \u05d4\u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d5\u05ea / Screenshot your app list\n\n"
            "4\ufe0f\u20e3 \u05e9\u05dc\u05d7 \u05d0\u05ea \u05d4\u05e6\u05d9\u05dc\u05d5\u05dd \u05db\u05d0\u05df / Send the screenshot here\n\n"
            "5\ufe0f\u20e3 \u05d1\u05d3\u05d5\u05e7: Settings > Security > Device Admin Apps\n"
            "   \u05e6\u05dc\u05dd \u05d2\u05dd \u05d0\u05ea \u05d6\u05d4 / Screenshot this too\n\n"
            "\U0001f6a8 \u05d0\u05dc \u05ea\u05de\u05d7\u05e7 \u05e9\u05d5\u05dd \u05d3\u05d1\u05e8 \u05dc\u05e4\u05e0\u05d9 \u05e9\u05e0\u05d1\u05d3\u05d5\u05e7!\n"
            "\U0001f6a8 Don't delete anything until we check!"
        ))
        await update.effective_message.reply_text(f"\u2705 App scan request sent to {client_id}")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c {e}")

# ============================================================

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
            text="\U0001f9fe BOOT/ADMIN REPORT\n\n" + await runtime_report(full=True),
        )


async def chatid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    title = getattr(chat, "title", "private")
    msg = f"Chat ID: {chat.id}\nType: {chat.type}\nTitle: {title}\nUser ID: {user.id}"
    await update.message.reply_text(msg)

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != int(os.getenv("ADMIN_ID", "224223270")):
        await update.message.reply_text("Unauthorized")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    msg = " ".join(context.args)
    chat_ids_str = os.getenv("BROADCAST_CHATS", "")
    if not chat_ids_str:
        await update.message.reply_text("Set BROADCAST_CHATS in env first")
        return
    ok, fail = 0, 0
    for cid in chat_ids_str.split(","):
        try:
            await context.bot.send_message(chat_id=int(cid.strip()), text=msg)
            ok += 1
        except Exception as e:
            fail += 1
    await update.message.reply_text(f"Broadcast: {ok} ok, {fail} failed")

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

    # Remote Support
    app.add_handler(CommandHandler("support", support_cmd))
    app.add_handler(CommandHandler("queue", queue_cmd))
    app.add_handler(CommandHandler("connect", connect_cmd))
    app.add_handler(CommandHandler("say", say_cmd))
    app.add_handler(CommandHandler("guide", guide_cmd))
    app.add_handler(CommandHandler("checklist", checklist_cmd))
    app.add_handler(CommandHandler("screenshot", screenshot_cmd))
    app.add_handler(CommandHandler("sysinfo", sysinfo_cmd))
    app.add_handler(CommandHandler("note", note_cmd))
    app.add_handler(CommandHandler("disconnect", disconnect_cmd))
    app.add_handler(CommandHandler("sessions", sessions_cmd))
    app.add_handler(CommandHandler("quickfix", quickfix_cmd))
    app.add_handler(CommandHandler("phonediag", phonediag_cmd))
    app.add_handler(CommandHandler("phonefix", phonefix_cmd))
    app.add_handler(CommandHandler("appscan", appscan_cmd))

    # Guardian ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â slh-api bridge (2026-04-20)
    try:
        from bot.commands.guardian_ops import register_handlers as _register_guardian_ops
        _register_guardian_ops(app)
    except Exception as e:
        logger.warning("guardian_ops registration failed: %s", e)
    try:
        from bot.commands.system_cmd import system_cmd
        app.add_handler(CommandHandler("system", system_cmd))
        logger.info("system_cmd registered")
    except Exception as e:
        logger.warning("system_cmd registration failed: %s", e)
    app.add_handler(CommandHandler("chatid", chatid_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))

    try:
        from bot.commands.ticket_cmd import register_handlers as _reg_ticket
        _reg_ticket(app)
    except Exception as e:
        logger.warning("ticket_cmd registration failed: %s", e)

    try:
        from bot.commands.snapshot_cmd import register_handlers as _reg_snapshot
        _reg_snapshot(app)
    except Exception as e:
        logger.warning("snapshot_cmd registration failed: %s", e)

    try:
        from bot.commands.snapshot_cmd import register_handlers as _reg_snapshot
        _reg_snapshot(app)
    except Exception as e:
        logger.warning("snapshot_cmd registration failed: %s", e)

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
        app.add_error_handler(_global_error_handler)
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
