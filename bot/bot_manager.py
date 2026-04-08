"""
Guardian Bot Manager — Remote management of all SLH ecosystem bots via Telegram.
Uses `docker compose` commands to restart/stop/start/logs/status individual bot containers.
Admin-only access.
"""
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

logger = logging.getLogger(__name__)

# Docker Compose project path (inside guardian container, mapped via volume or using host docker socket)
COMPOSE_FILE = "/app/ecosystem/docker-compose.yml"
# Fallback: Windows host path (when running locally, not in Docker)
COMPOSE_FILE_WIN = "D:/SLH_ECOSYSTEM/docker-compose.yml"

# All manageable bot services (service_name -> display_name)
BOT_SERVICES = {
    "core-bot": "📚 Academia (Core)",
    "guardian-bot": "🛡️ Guardian",
    "botshop": "🏪 BotShop (GATE)",
    "wallet-bot": "💰 Wallet",
    "factory-bot": "🏭 Factory",
    "fun-bot": "🎉 FUN",
    "admin-bot": "👑 Super Admin",
    "expertnet-bot": "🧠 ExpertNet",
    "airdrop-bot": "🪂 Airdrop (HUB)",
    "campaign-bot": "📣 Campaign",
    "game-bot": "🎮 Game",
    "ton-mnh-bot": "🪙 TON-MNH",
    "slh-ton-bot": "💎 SLH-TON",
    "ledger-bot": "📒 Ledger",
    "osif-shop-bot": "🛒 Osif Shop",
    "nifti-bot": "🎨 NIFTI",
    "chance-bot": "🎰 Chance",
    "nfty-bot": "🐾 NFTY (Tamagotchi)",
    "selha-bot": "⭐ SELHA",
    "ts-set-bot": "⚙️ TS-SET",
    "crazy-panel-bot": "🤪 Crazy Panel",
    "nft-shop-bot": "🖼️ NFT Shop",
    "userinfo-bot": "ℹ️ UserInfo",
    "beynonibank-bot": "🏦 BeynoniBank",
    "test-bot": "🧪 Test Bot",
}

# Infrastructure services (separate category)
INFRA_SERVICES = {
    "postgres": "🐘 PostgreSQL",
    "redis": "🔴 Redis",
}

ITEMS_PER_PAGE = 8


async def _run_docker(cmd: str, timeout: int = 30) -> tuple[str, bool]:
    """Run a docker compose command and return (output, success)."""
    import os
    # Determine compose file path
    compose_file = COMPOSE_FILE if os.path.exists(COMPOSE_FILE) else COMPOSE_FILE_WIN

    full_cmd = f"docker compose -f {compose_file} {cmd}"
    logger.info(f"[BotManager] Running: {full_cmd}")

    try:
        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = (stdout or b"").decode("utf-8", errors="replace")
        errors = (stderr or b"").decode("utf-8", errors="replace")
        ok = proc.returncode == 0
        result = output if output.strip() else errors
        return result[:3000], ok  # Cap output length for Telegram
    except asyncio.TimeoutError:
        return "⏰ Command timed out", False
    except Exception as e:
        return f"❌ Error: {e}", False


def _bot_list_keyboard(page: int = 0, action: str = "status") -> InlineKeyboardMarkup:
    """Generate paginated inline keyboard of bots."""
    services = list(BOT_SERVICES.items())
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_services = services[start:end]
    total_pages = (len(services) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    buttons = []
    for svc, label in page_services:
        buttons.append([InlineKeyboardButton(label, callback_data=f"bm:{action}:{svc}")])

    # Navigation row
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ הקודם", callback_data=f"bm:page:{action}:{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="bm:noop"))
    if end < len(services):
        nav.append(InlineKeyboardButton("הבא ▶️", callback_data=f"bm:page:{action}:{page + 1}"))
    buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


# ── Command Handlers ─────────────────────────────────────────────

async def bots_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all bots status overview."""
    from bot.app_factory import is_admin
    if not is_admin(update):
        await update.message.reply_text("⛔ Admin only.")
        return

    await update.message.reply_text("⏳ בודק סטטוס כל הבוטים...")

    output, ok = await _run_docker("ps --format 'table {{.Name}}\\t{{.Status}}\\t{{.State}}'", timeout=15)

    if not ok:
        # Fallback: try simpler command
        output, ok = await _run_docker("ps", timeout=15)

    # Build status summary
    lines = ["🤖 <b>SLH Bot Manager</b>\n"]
    running = 0
    stopped = 0

    for svc, label in BOT_SERVICES.items():
        # Check if service name or container name appears in output
        container_name = f"slh-{svc}" if svc != "botshop" else "slh-botshop"
        if container_name in output and ("Up" in output or "running" in output.lower()):
            lines.append(f"🟢 {label}")
            running += 1
        elif container_name in output:
            lines.append(f"🔴 {label}")
            stopped += 1
        else:
            lines.append(f"⚪ {label} (not found)")
            stopped += 1

    lines.insert(1, f"✅ {running} running | ❌ {stopped} stopped\n")

    # Add infra status
    lines.append("\n<b>Infrastructure:</b>")
    for svc, label in INFRA_SERVICES.items():
        if svc in output:
            lines.append(f"🟢 {label}")
        else:
            lines.append(f"🔴 {label}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def bot_restart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restart a specific bot. Usage: /bot_restart <service-name> or interactive."""
    from bot.app_factory import is_admin
    if not is_admin(update):
        await update.message.reply_text("⛔ Admin only.")
        return

    if context.args and context.args[0] in BOT_SERVICES:
        svc = context.args[0]
        label = BOT_SERVICES[svc]
        await update.message.reply_text(f"🔄 מפעיל מחדש {label}...")
        output, ok = await _run_docker(f"restart {svc}", timeout=60)
        emoji = "✅" if ok else "❌"
        await update.message.reply_text(f"{emoji} <b>{label}</b>\n<pre>{output[:1000]}</pre>", parse_mode="HTML")
    else:
        await update.message.reply_text(
            "🔄 <b>Restart Bot</b>\nבחר בוט להפעלה מחדש:",
            parse_mode="HTML",
            reply_markup=_bot_list_keyboard(0, "restart")
        )


async def bot_stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop a specific bot. Usage: /bot_stop <service-name>"""
    from bot.app_factory import is_admin
    if not is_admin(update):
        await update.message.reply_text("⛔ Admin only.")
        return

    if context.args and context.args[0] in BOT_SERVICES:
        svc = context.args[0]
        label = BOT_SERVICES[svc]
        await update.message.reply_text(f"⏹️ עוצר {label}...")
        output, ok = await _run_docker(f"stop {svc}", timeout=30)
        emoji = "✅" if ok else "❌"
        await update.message.reply_text(f"{emoji} <b>{label}</b> stopped\n<pre>{output[:1000]}</pre>", parse_mode="HTML")
    else:
        await update.message.reply_text(
            "⏹️ <b>Stop Bot</b>\nבחר בוט לעצירה:",
            parse_mode="HTML",
            reply_markup=_bot_list_keyboard(0, "stop")
        )


async def bot_start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a stopped bot. Usage: /bot_start <service-name>"""
    from bot.app_factory import is_admin
    if not is_admin(update):
        await update.message.reply_text("⛔ Admin only.")
        return

    if context.args and context.args[0] in BOT_SERVICES:
        svc = context.args[0]
        label = BOT_SERVICES[svc]
        await update.message.reply_text(f"▶️ מפעיל {label}...")
        output, ok = await _run_docker(f"start {svc}", timeout=30)
        emoji = "✅" if ok else "❌"
        await update.message.reply_text(f"{emoji} <b>{label}</b> started\n<pre>{output[:1000]}</pre>", parse_mode="HTML")
    else:
        await update.message.reply_text(
            "▶️ <b>Start Bot</b>\nבחר בוט להפעלה:",
            parse_mode="HTML",
            reply_markup=_bot_list_keyboard(0, "start")
        )


async def bot_logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent logs for a bot. Usage: /bot_logs <service-name> [lines]"""
    from bot.app_factory import is_admin
    if not is_admin(update):
        await update.message.reply_text("⛔ Admin only.")
        return

    if context.args and context.args[0] in BOT_SERVICES:
        svc = context.args[0]
        lines = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 20
        lines = min(lines, 50)  # Cap at 50 lines
        label = BOT_SERVICES[svc]
        output, ok = await _run_docker(f"logs --tail {lines} --no-color {svc}", timeout=15)
        if not output.strip():
            output = "(no logs available)"
        # Truncate for Telegram message limit
        if len(output) > 3500:
            output = output[-3500:]
        await update.message.reply_text(
            f"📋 <b>{label}</b> — last {lines} lines:\n<pre>{output}</pre>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            "📋 <b>Bot Logs</b>\nבחר בוט לצפייה בלוגים:",
            parse_mode="HTML",
            reply_markup=_bot_list_keyboard(0, "logs")
        )


async def bot_restart_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restart all bots (not infra). Admin only."""
    from bot.app_factory import is_admin
    if not is_admin(update):
        await update.message.reply_text("⛔ Admin only.")
        return

    bot_list = " ".join(BOT_SERVICES.keys())
    await update.message.reply_text(f"🔄 מפעיל מחדש את כל {len(BOT_SERVICES)} הבוטים...\nזה יכול לקחת כמה דקות.")
    output, ok = await _run_docker(f"restart {bot_list}", timeout=180)
    emoji = "✅" if ok else "⚠️"
    await update.message.reply_text(f"{emoji} <b>Restart All Complete</b>\n<pre>{output[:2000]}</pre>", parse_mode="HTML")


# ── Callback Query Handler (inline buttons) ──────────────────────

async def bot_manager_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses for bot manager."""
    from bot.app_factory import is_admin
    query = update.callback_query
    await query.answer()

    if not is_admin(update):
        await query.edit_message_text("⛔ Admin only.")
        return

    data = query.data
    if not data.startswith("bm:"):
        return

    parts = data.split(":")

    # Pagination: bm:page:<action>:<page_num>
    if parts[1] == "page":
        action = parts[2]
        page = int(parts[3])
        titles = {"restart": "🔄 Restart Bot", "stop": "⏹️ Stop Bot", "start": "▶️ Start Bot",
                  "logs": "📋 Bot Logs", "status": "🤖 Bot Status"}
        await query.edit_message_text(
            f"{titles.get(action, '🤖')} — בחר בוט:",
            parse_mode="HTML",
            reply_markup=_bot_list_keyboard(page, action)
        )
        return

    if parts[1] == "noop":
        return

    # Action on a specific bot: bm:<action>:<service>
    action = parts[1]
    svc = parts[2]
    label = BOT_SERVICES.get(svc, svc)

    if action == "restart":
        await query.edit_message_text(f"🔄 מפעיל מחדש {label}...")
        output, ok = await _run_docker(f"restart {svc}", timeout=60)
        emoji = "✅" if ok else "❌"
        await query.edit_message_text(f"{emoji} <b>{label}</b> restarted\n<pre>{output[:1000]}</pre>", parse_mode="HTML")

    elif action == "stop":
        await query.edit_message_text(f"⏹️ עוצר {label}...")
        output, ok = await _run_docker(f"stop {svc}", timeout=30)
        emoji = "✅" if ok else "❌"
        await query.edit_message_text(f"{emoji} <b>{label}</b> stopped\n<pre>{output[:1000]}</pre>", parse_mode="HTML")

    elif action == "start":
        await query.edit_message_text(f"▶️ מפעיל {label}...")
        output, ok = await _run_docker(f"start {svc}", timeout=30)
        emoji = "✅" if ok else "❌"
        await query.edit_message_text(f"{emoji} <b>{label}</b> started\n<pre>{output[:1000]}</pre>", parse_mode="HTML")

    elif action == "logs":
        await query.edit_message_text(f"📋 טוען לוגים של {label}...")
        output, ok = await _run_docker(f"logs --tail 20 --no-color {svc}", timeout=15)
        if not output.strip():
            output = "(no logs available)"
        if len(output) > 3500:
            output = output[-3500:]
        await query.edit_message_text(
            f"📋 <b>{label}</b> — last 20 lines:\n<pre>{output}</pre>",
            parse_mode="HTML"
        )

    elif action == "status":
        output, ok = await _run_docker(f"ps {svc}", timeout=10)
        await query.edit_message_text(
            f"🤖 <b>{label}</b>\n<pre>{output[:2000]}</pre>",
            parse_mode="HTML"
        )


# ── Registration Helper ──────────────────────────────────────────

def register_bot_manager(app, with_latency_fn):
    """Register all bot manager commands and callbacks on the Application."""
    app.add_handler(CommandHandler("bots", with_latency_fn("bots", bots_cmd)))
    app.add_handler(CommandHandler("bot_restart", with_latency_fn("bot_restart", bot_restart_cmd)))
    app.add_handler(CommandHandler("bot_stop", with_latency_fn("bot_stop", bot_stop_cmd)))
    app.add_handler(CommandHandler("bot_start", with_latency_fn("bot_start", bot_start_cmd)))
    app.add_handler(CommandHandler("bot_logs", with_latency_fn("bot_logs", bot_logs_cmd)))
    app.add_handler(CommandHandler("bot_restart_all", with_latency_fn("bot_restart_all", bot_restart_all_cmd)))
    app.add_handler(CallbackQueryHandler(bot_manager_callback, pattern=r"^bm:"))
    logger.info("[BotManager] Registered 6 commands + callback handler")
