import os
import logging
import time
import traceback
from collections import deque
from pathlib import Path
from urllib.parse import urlparse
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import Conflict
from dotenv import load_dotenv

load_dotenv(".env.local")

from bot.config import BOT_TOKEN, ENV, MODE, ADMIN_CHAT_ID, WEBHOOK_URL
from bot.infrastructure import init_infrastructure, runtime_report
from bot import db_live
from bot import daily_rewards

START_TS = time.time()
CMD_HISTORY = deque(maxlen=30)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
)
logger = logging.getLogger(__name__)

async def _global_error_handler(update, context):
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

# ====================== COMMANDS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "start")
    text = (
        f"```\n{ASCII_BANNER.strip()}\n```\n"
        "SLH Security + Ops Control\n\n"
        "ברוך הבא ל-SLH Guardian.\n"
        "מערכת לניטור תשתיות, גיבוי, ניהול תפעול, והכנה ל-SaaS מלא.\n\n"
        "פקודות:\n"
        "/status    סטטוס DB/Redis/Alembic\n"
        "/menu      תפריט\n"
        "/whoami    מי אני\n"
        "/health    מצב מערכת\n"
        "/support   🛎️ בקש תמיכה מרחוק\n"
        "/ticket    🎫 פתח כרטיס תמיכה\n"
        "/system    🖥 סטטוס מערכת\n"
        "/snapshot  📸 סנפשוט מערכת\n\n"
        "/admin     דוח אדמין\n"
        "/vars      Vars (SET/MISSING)\n"
        "/webhook   Webhook Info\n"
        "/diag      דיאגנוסטיקה\n"
        "/pingdb    בדיקת DB latency\n"
        "/pingredis בדיקת Redis latency\n\n"
        "🛎️ תמיכה מרחוק / Remote Support:\n"
        "/queue       בקשות ממתינות\n"
        "/connect     התחל סשן\n"
        "/say         שלח הודעה\n"
        "/guide       שלב הדרכה\n"
        "/checklist   רשימת בדיקה\n"
        "/screenshot  בקש צילום מסך\n"
        "/sysinfo     מידע מערכת\n"
        "/quickfix    תיקון מהיר\n"
        "/sessions    סשנים פעילים\n"
        "/disconnect  סיום סשן\n\n"
        "📱 אבחון טלפון / Phone Diag:\n"
        "/phonediag   אבחון מכשיר\n"
        "/phonefix    תיקון טלפון\n"
        "/appscan     בדיקת אפליקציות\n\n"
        "➕ נוספות: /referral, /points, /leaderboard, /analytics, /royalties, /roadmap"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "whoami")
    u = update.effective_user
    c = update.effective_chat
    lines = [
        "🫸 WHOAMI",
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
        "🧪 תפריט בדיקות:",
        "/start",
        "/status",
        "/menu",
        "/whoami",
        "/health",
    ]
    if is_admin(update):
        lines += ["", "📌 פקודות אדמין:", "/admin", "/vars", "/webhook", "/diag", "/pingdb", "/pingredis"]
    await update.message.reply_text("\n".join(lines))

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "status")
    await update.message.reply_text(await runtime_report(full=is_admin(update)))

async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "health")
    sha = _git_sha()
    lines = [
        "🩺 HEALTH",
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
        await update.message.reply_text("⛔ אין לך הרשאה.")
        return
    lines = [
        "📌 VARS (SET/MISSING)",
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
        await update.message.reply_text("⛔ אין לך הרשאה.")
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
        data = r.json()
        result = data.get("result", {})
        lines = [
            "🪝 WEBHOOK INFO",
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
        await update.message.reply_text("⛔ אין לך הרשאה.")
        return
    sha = _git_sha()
    lines = [
        "🧪 DIAG",
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
        await update.message.reply_text("⛔ אין לך הרשאה.")
        return
    t0 = time.perf_counter()
    ok = False
    err = None
    try:
        _ = await runtime_report(full=False)
        ok = True
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    dt_ms = int((time.perf_counter() - t0) * 1000)
    await update.message.reply_text(f"🗄️ DB ping: {'OK' if ok else 'FAIL'} ({dt_ms} ms){'' if not err else ' | ' + err}")

async def pingredis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "pingredis")
    if not is_admin(update):
        await update.message.reply_text("⛔ אין לך הרשאה.")
        return
    t0 = time.perf_counter()
    ok = False
    err = None
    try:
        _ = await runtime_report(full=False)
        ok = True
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    dt_ms = int((time.perf_counter() - t0) * 1000)
    await update.message.reply_text(f"🧠 Redis ping: {'OK' if ok else 'FAIL'} ({dt_ms} ms){'' if not err else ' | ' + err}")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "admin")
    if not is_admin(update):
        await update.message.reply_text("⛔ אין לך הרשאה.")
        return
    await update.message.reply_text("🫸 BOOT/ADMIN REPORT\n\n" + await runtime_report(full=True))

# ====================== ADMIN MENU ======================
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 סטטוס מערכת", callback_data="admin_status")],
        [InlineKeyboardButton("💰 תשלומים", callback_data="admin_payments")],
        [InlineKeyboardButton("👥 ניהול משתמשים", callback_data="admin_users")],
        [InlineKeyboardButton("🔍 דיאגנוסטיקה", callback_data="admin_diag")],
        [InlineKeyboardButton("📈 סטטיסטיקות", callback_data="admin_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "*🔧 תפריט אדמין SLH Guardian*\n\nבחר פעולה:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "admin_status":
        text = await runtime_report(full=False)
    elif data == "admin_payments":
        text = "💰 מערכת תשלומים  בקרוב"
    elif data == "admin_users":
        text = "👥 ניהול משתמשים  יש להשלים"
    elif data == "admin_diag":
        text = f"🔍 דיאגנוסטיקה\nENV: {ENV}\nMODE: {MODE}\nUptime: {_uptime_s()//3600}h"
    elif data == "admin_stats":
        text = f"📈 סטטיסטיקות\nפקודות אחרונות: {len(CMD_HISTORY)}"
    else:
        text = "❓ פעולה לא מזוהה"
    await query.edit_message_text(text=text, parse_mode='Markdown')

# ====================== REFERRAL & POINTS ======================
async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"*🔗 קוד ההפניה שלך:* `{user_id}`\n\n100 נקודות + 10% עמלה",
        parse_mode='Markdown'
    )

async def points_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "points")
    await update.message.reply_text("🏆 *הנקודות שלך:* `0`\n💡 100 נקודות = 10% הנחה", parse_mode='Markdown')

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "leaderboard")
    await update.message.reply_text("📊 *טבלת מובילים*\nאין נתונים כרגע", parse_mode='Markdown')

async def analytics_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "analytics")
    if not is_admin(update):
        await update.message.reply_text("⛔ גישה מוגבלת לאדמינים בלבד.")
        return
    text = f"📊 *SLH Guardian Analytics*\n\n👥 סה\"כ משתמשים: 0\n🔗 סה\"כ הפניות: 0\n📈 Uptime: {_uptime_s()//3600}h\nENV: {ENV}\nMODE: {MODE}"
    await update.message.reply_text(text, parse_mode='Markdown')

async def royalties_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "royalties")
    await update.message.reply_text("👑 *התמלוגים שלך:* `0 TON`\n(יופקדו בהמשך)", parse_mode='Markdown')

async def roadmap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """🗺️ *SLH Guardian Roadmap*

✅ *הושלם (26.5)*
 בוט יציב, כפתורי אדמין, הפניות, נקודות

📌 *שלב 1 (השבוע)*
• מנוע תמלוגים  20% מהכנסות מתחלקים למביאי הפניות
• Premium subscription (49$/חודש)
• TON Payment Watcher

📌 *שלב 2 (שבועיים)*
• בונוס יומי, ליגות, אתגרים
• Dashboard אישי

📌 *שלב 3 (חודשיים)*
• טוקן SLH על TON
• המרת נקודות + Royalties לטוקנים

💡 *כל משתמש שמביא חבר מקבל 100 נקודות + 10% מהחודש הראשון של החבר.*
"""
    await update.message.reply_text(text, parse_mode='Markdown')

# ====================== SUPPORT (PLACEHOLDERS) ======================
async def support_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛎️ מערכת התמיכה תשוחזר בהמשך. בינתיים, פנה לאדמין.")

async def ticket_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎫 פתיחת כרטיס תמיכה  בקרוב.")

# (ניתן להוסיף בקלות את שאר הפקודות מ-backup)


async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "daily")
    u = update.effective_user
    await db_live.ensure_user(u.id, u.username)
    result = await daily_rewards.claim_daily(u.id)
    if result["ok"]:
        streak = result["streak"]
        amount = result["amount"]
        bars = "🔥" * streak + "⬜" * (7 - streak)
        next_reward = daily_rewards.STREAK_REWARDS.get(min(streak + 1, 7), 200)
        text = (
            f"✅ *Daily Reward נדרש!*\n\n"
            f"💰 קיבלת: `{amount} SLH`\n"
            f"🔥 Streak: `{streak}/7`\n"
            f"{bars}\n\n"
            f"⏭ מחר: `+{next_reward} SLH`\n"
            f"💡 שמור על ה-Streak לקבל `200 SLH` ביום 7!"
        )
    else:
        streak = result["streak"]
        bars = "🔥" * streak + "⬜" * (7 - streak)
        text = (
            f"⏳ *כבר תבעת היום!*\n\n"
            f"🕐 הבא בעוד: `{result['wait']}`\n"
            f"🔥 Streak נוכחי: `{streak}/7`\n"
            f"{bars}"
        )
    await update.message.reply_text(text, parse_mode='Markdown')

# ====================== POST_INIT ======================
async def post_init(app):
    await init_infrastructure()
    if ADMIN_CHAT_ID:
        await app.bot.send_message(
            chat_id=int(ADMIN_CHAT_ID),
            text="🫸 BOOT/ADMIN REPORT\n\n" + await runtime_report(full=True),
        )

# ====================== MAIN ======================
def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set")
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_error_handler(_global_error_handler)

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
    app.add_handler(CommandHandler("admin_menu", admin_menu))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(CommandHandler("referral", referral_cmd))
    app.add_handler(CommandHandler("points", points_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CommandHandler("analytics", analytics_cmd))
    app.add_handler(CommandHandler("royalties", royalties_cmd))
    app.add_handler(CommandHandler("roadmap", roadmap_cmd))
    app.add_handler(CommandHandler("support", support_cmd))
    app.add_handler(CommandHandler("ticket", ticket_cmd))
    app.add_handler(CommandHandler("daily", daily_cmd))

    logger.info("✅ Guardian SaaS started  Full Features Restored")
    mode = (MODE or "polling").lower()
    if mode == "webhook":
        if not WEBHOOK_URL:
            raise ValueError("WEBHOOK_URL not set for webhook mode")
        listen = "0.0.0.0"
        port = int(os.getenv("PORT", "8080"))
        webhook_url = _normalize_webhook_url(WEBHOOK_URL)
        url_path = _parse_webhook_path(webhook_url)
        app.run_webhook(
            listen=listen,
            port=port,
            url_path=url_path,
            webhook_url=webhook_url,
            drop_pending_updates=True,
        )
    else:
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()






