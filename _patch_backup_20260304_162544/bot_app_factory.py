import logging
from bot.banner_anim import should_animate_banner, send_banner_animated
logger = logging.getLogger(__name__)
import os
import time
from typing import Callable, Awaitable

from telegram import Update
from telegram import BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from sqlalchemy.exc import IntegrityError
from telegram.error import Conflict

from bot.config import BOT_TOKEN, ENV, ADMIN_CHAT_ID, WEBHOOK_URL, MODE
from bot.infrastructure import init_infrastructure, runtime_report
from bot.telemetry import log_json, exc_to_str, update_brief, log_event, log_event
from bot.rbac_store import has_role, grant_role, revoke_role, list_users_with_role
from bot.config import DONATE_URL
from bot.economy_store import (
    add_account, list_accounts, set_plan_price, list_plans,
    create_payment_request, list_pending_requests, get_request, set_request_status,
    add_points, get_points_balance, list_user_requests,
    upsert_referral, get_referrer,

)

START_TS = time.time()

def _uptime_s() -> int:
    return int(time.time() - START_TS)

def _git_sha() -> str:
    return (
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("GIT_COMMIT_SHA")
        or os.getenv("COMMIT_SHA")
        or "")

def is_admin(update: Update) -> bool:
    return bool(ADMIN_CHAT_ID) and str(update.effective_chat.id) == str(ADMIN_CHAT_ID)

def is_owner(update: Update) -> bool:
    # owner is ADMIN_CHAT_ID (chat id)
    return bool(ADMIN_CHAT_ID) and str(update.effective_chat.id) == str(ADMIN_CHAT_ID)

async def is_admin_rbac(update: Update) -> bool:
    # owner always allowed; else admin role in DB
    if is_owner(update):
        return True
    try:
        return await has_role(int(update.effective_user.id), "admin")
    except Exception:
        # if DB not ready, fall back to legacy owner-only
        return False

ASCII_BANNER = ""
try:
    from pathlib import Path
    ASCII_BANNER = Path("assets/banner.txt").read_text(encoding="utf-8")
except Exception:
    ASCII_BANNER = (
        "=====================================\n"
        "==           SLH  GUARDIAN          ==\n"
        "=====================================\n"

)

def _parse_amount(x: str) -> int:
    return int(str(x).strip())

def with_latency(name: str, fn: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]):
    async def _wrap(update: Update, context: ContextTypes.DEFAULT_TYPE):
        t0 = time.perf_counter()
        try:
            await fn(update, context)
            ok = True
            err = None
        except Exception as e:
            ok = False
            err = f"{type(e).__name__}: {e}"
            raise
        finally:
            dt_ms = int((time.perf_counter() - t0) * 1000)
            brief = update_brief(update)
            log_json(logging.INFO, "handler_latency", handler=name, ok=ok, dt_ms=dt_ms, **brief, error=err)
    return _wrap

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # start ref hook
    try:
        if context.args and len(context.args) >= 1 and str(context.args[0]).startswith("ref_"):
            ref_id = int(str(context.args[0]).split("_", 1)[1])
            u = update.effective_user
            if u:
                ok_link = await upsert_referral(ref_id, int(u.id))
                if ok_link:
                    log_event(logging.INFO, "referral_linked", referrer_id=ref_id, referred_id=int(u.id))
    except Exception:
        pass

    footer = (
        "SLH Guardian Security + Ops Control\n\n"
        "Welcome to SLH Guardian.\n"
        "Infra monitoring, ops control, and SaaS-ready foundation.\n\n"
        "Commands:\n"
        "/status    DB/Redis/Alembic status\n"
        "/menu      menu\n"
        "/whoami    who am I\n"
        "/health    system health\n"
        "/donate    support / donate\n"
        "/admins    list admins (access-controlled)\n"
    )

    footer_full = footer

    text = "```\n" + ASCII_BANNER.strip() + "\n```\n" + footer_full

    if is_admin(update):
        admin_tail = "\n/admin     admin report\n/vars      Vars (SET/MISSING)\n/webhook   Webhook Info\n/diag      diagnostics\n/pingdb    DB latency\n/pingredis Redis latency\n/snapshot  snapshot\n"
        footer_full = footer + admin_tail
        text = "```\n" + ASCII_BANNER.strip() + "\n```\n" + footer_full

    await update.message.reply_text(text, parse_mode="Markdown")

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    c = update.effective_chat
    lines = [
        "WHOAMI",
        f"user_id: {u.id if u else None}",
        f"username: @{u.username}" if u and u.username else "username: (none)",
        f"chat_id: {c.id if c else None}",
        f"chat_type: {c.type if c else None}",
        f"is_admin_chat: {is_admin(update)}",
    ]
    await update.message.reply_text("\n".join(lines))

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["Commands:", "/start", "/status", "/menu", "/whoami", "/health", "/donate", "/admins", "/ref", "/my", "/buy", "/claim", "/grant_admin", "/revoke_admin", "/dm", "/broadcast_admins"]
    if is_admin(update):
        lines += ["", "Admin:", "/admin", "/vars", "/webhook", "/diag", "/pingdb", "/pingredis"]
    await update.message.reply_text("\n".join(lines))

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(await runtime_report(full=is_admin(update)))

async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sha = _git_sha()
    lines = ["HEALTH", f"ENV: {ENV}", f"MODE: {MODE}", f"uptime_s: {_uptime_s()}"]
    if sha:
        lines.append(f"git_sha: {sha[:12]}")
    if is_admin(update):
        lines.append(f"webhook_url: {WEBHOOK_URL or 'MISSING'}")
    await update.message.reply_text("\n".join(lines))

async def ref_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        await update.message.reply_text("No user.")
        return
    bot_user = await context.bot.get_me()
    link = f"https://t.me/{bot_user.username}?start=ref_{u.id}"
    log_event(logging.INFO, "referral_link_issued", user_id=int(u.id), username=(u.username or None))
    await update.message.reply_text("REFERRAL LINK\n" + link)

async def my_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        await update.message.reply_text("No user.")
        return
    bal = await get_points_balance(int(u.id))
    reqs = await list_user_requests(int(u.id), limit=5)
    lines = [
        "MY",
        f"user_id: {u.id}",
        f"points: {bal}",
        "",
        "Recent requests:",
    ]
    if not reqs:
        lines.append("(none)")

    await update.message.reply_text("\n".join(lines))

async def buy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        await update.message.reply_text("No user.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /buy <amount> [note]")
        return
    amt = _parse_amount(context.args[0])
    note = " ".join(context.args[1:]) if len(context.args) > 1 else None
    req_id = await create_payment_request(int(u.id), "buy_token", amt, "SELHA", note=note)
    log_event(logging.INFO, "economy_request_created", kind="buy_token", request_id=req_id, amount=amt, user_id=int(u.id), username=(u.username or None))
    await update.message.reply_text(f"OK: buy request created #{req_id} (pending)")

async def claim_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        await update.message.reply_text("No user.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /claim <amount> <tx_ref> [note]")
        return
    amt = _parse_amount(context.args[0])
    tx = context.args[1]
    note = " ".join(context.args[2:]) if len(context.args) > 2 else None
    req_id = await create_payment_request(int(u.id), "donate", amt, "SELHA", tx_ref=tx, note=note)
    log_event(logging.INFO, "economy_request_created", kind="donate", request_id=req_id, amount=amt, user_id=int(u.id), username=(u.username or None), tx_ref=tx)
    log_event(logging.INFO, "economy_request_created", kind="donate", request_id=req_id, amount=amt, user_id=int(u.id), username=(u.username or None), tx_ref=tx)
    await update.message.reply_text(f"OK: donation claim created #{req_id} (pending)")

async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_rbac(update):
        await update.message.reply_text("Access denied.")
        return
    items = await list_pending_requests(limit=10)
    lines = ["PENDING REQUESTS:"]
    if not items:
        lines.append("(none)")

    await update.message.reply_text("\n".join(lines))

async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_rbac(update):
        await update.message.reply_text("Access denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /approve <request_id>")
        return
    rid = int(context.args[0])
    req = await get_request(rid)
    if not req or req["status"] != "pending":
        await update.message.reply_text("Not found or not pending.")
        return

    await set_request_status(rid, "approved", decided_by=int(update.effective_user.id))
    await add_points(int(req["user_id"]), int(req["amount"]), reason=req["kind"], ref=str(rid))

    referrer = await get_referrer(int(req["user_id"]))
    if referrer:
        bonus = max(1, int(int(req["amount"]) * 0.05))
        await add_points(int(referrer), bonus, reason="ref_bonus", ref=str(rid))

    log_event(logging.INFO, "economy_request_decided", action="approve", request_id=rid, user_id=int(req["user_id"]), decided_by=int(update.effective_user.id), amount=int(req["amount"]), kind=req["kind"])
    log_event(logging.INFO, "points_awarded", user_id=int(req["user_id"]), delta=int(req["amount"]), reason=req["kind"], ref=str(rid))
    await update.message.reply_text(f"OK: approved #{rid} and awarded {req['amount']} points")

async def reject_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_rbac(update):
        await update.message.reply_text("Access denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /reject <request_id>")
        return
    rid = int(context.args[0])
    req = await get_request(rid)
    if not req or req["status"] != "pending":
        await update.message.reply_text("Not found or not pending.")
        return
    await set_request_status(rid, "rejected", decided_by=int(update.effective_user.id))
    log_event(logging.INFO, "economy_request_decided", action="reject", request_id=rid, decided_by=int(update.effective_user.id))
    log_event(logging.INFO, "economy_request_decided", action="reject", request_id=rid, decided_by=int(update.effective_user.id))
    await update.message.reply_text(f"OK: rejected #{rid}")

async def add_account_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        await update.message.reply_text("No user.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /add_account <bank|crypto> <label> <details...>\nExample: /add_account crypto MyTON address=UQ...\nExample: /add_account bank MyBank bank=Hapoalim branch=123 account=456")
        return

    acc_type = context.args[0].lower()
    if acc_type not in ("bank","crypto"):
        await update.message.reply_text("First arg must be bank or crypto.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /add_account <bank|crypto> <label> <details...>")
        return

    label = context.args[1]
    details = {}
    for token in context.args[2:]:
        if "=" in token:
            k,v = token.split("=",1)
            details[k.strip()] = v.strip()

    acc_id = await add_account(int(u.id), acc_type, label, details)
    await update.message.reply_text(f"OK: account saved #{acc_id}")

async def prices_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = await list_plans()
    lines = ["PRICES:"]
    if not plans:
        lines.append("(none)")

    await update.message.reply_text("\n".join(lines))

async def set_price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("Access denied.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /set_price <plan_code> <amount>")
        return
    code = context.args[0]
    amt = _parse_amount(context.args[1])
    await set_plan_price(code, amt, "SELHA")
    await update.message.reply_text(f"OK: price set {code} = {amt} SELHA")

async def trade_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # manual trading wizard (request -> approve)
    u = update.effective_user
    if not u:
        await update.message.reply_text("No user.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /trade <buy|sell> <amount> [note]\nExample: /trade buy 100\nExample: /trade sell 50 reason=takeprofit")
        return
    side = context.args[0].lower()
    if side not in ("buy","sell"):
        await update.message.reply_text("First arg must be buy or sell.")
        return
    amt = _parse_amount(context.args[1])
    note = " ".join(context.args[2:]) if len(context.args) > 2 else None
    kind = "buy_token" if side == "buy" else "sell_token"
    req_id = await create_payment_request(int(u.id), kind, amt, "SELHA", note=note)
    await update.message.reply_text(f"OK: trade request created #{req_id} ({kind}) [pending]")

async def donate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DONATE_URL:
        await update.message.reply_text("Donations are not configured yet.")
        return
    await update.message.reply_text(f"DONATE / SUPPORT\n{DONATE_URL}")

async def vars_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("? Access denied.")
        return
    def mask(v): return "SET" if v else "MISSING"
    lines = [
        "VARS (SET/MISSING)",
        f"ENV: {ENV}",
        f"MODE: {MODE}",
        f"BOT_TOKEN: {mask(BOT_TOKEN)}",
        f"DATABASE_URL: {mask(os.getenv('DATABASE_URL'))}",
        f"REDIS_URL: {mask(os.getenv('REDIS_URL'))}",
        f"ADMIN_CHAT_ID: {mask(ADMIN_CHAT_ID)}",
        f"WEBHOOK_URL: {mask(WEBHOOK_URL)}",
        f"LOG_LEVEL: {mask(os.getenv('LOG_LEVEL'))}",
        f"OPENAI_API_KEY: {mask(os.getenv('OPENAI_API_KEY'))}",
    ]
    await update.message.reply_text("\n".join(lines))

async def webhookinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("? Access denied.")
        return
    import httpx
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url)
    data = r.json().get("result", {})
    lines = [
        "WEBHOOK INFO",
        f"url: {data.get('url') or ''}",
        f"pending_update_count: {data.get('pending_update_count')}",
        f"last_error_date: {data.get('last_error_date')}",
        f"last_error_message: {data.get('last_error_message')}",
    ]
    await update.message.reply_text("\n".join(lines))

async def diag_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("? Access denied.")
        return
    sha = _git_sha()
    await update.message.reply_text("\n".join([
        "DIAG",
        f"env: {ENV}",
        f"mode: {MODE}",
        f"uptime_s: {_uptime_s()}",
        f"git_sha: {(sha[:12] if sha else '(none)')}",
        f"webhook_url: {WEBHOOK_URL or 'MISSING'}",
    ]))

async def pingdb_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("? Access denied.")
        return
    t0 = time.perf_counter()
    ok = True
    err = None
    try:
        _ = await runtime_report(full=False)
    except Exception as e:
        ok = False
        err = f"{type(e).__name__}: {e}"
    dt = int((time.perf_counter() - t0) * 1000)
    await update.message.reply_text(f"DB ping: {'OK' if ok else 'FAIL'} ({dt} ms){'' if not err else ' | ' + err}")

async def pingredis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("? Access denied.")
        return
    t0 = time.perf_counter()
    ok = True
    err = None
    try:
        _ = await runtime_report(full=False)
    except Exception as e:
        ok = False
        err = f"{type(e).__name__}: {e}"
    dt = int((time.perf_counter() - t0) * 1000)
    await update.message.reply_text(f"Redis ping: {'OK' if ok else 'FAIL'} ({dt} ms){'' if not err else ' | ' + err}")

async def snapshot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Access denied.")
        return

    import httpx  # local import to avoid NameError

    base = "https://gardient2-production.up.railway.app"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            version = (await client.get(f"{base}/version")).text.strip()
            healthz = (await client.get(f"{base}/healthz")).text.strip()
            readyz  = (await client.get(f"{base}/readyz")).text.strip()
            snap    = (await client.get(f"{base}/snapshot")).text.strip()

        msg = "\n".join([
            "SNAPSHOT",
            f"base: {base}",
            "",
            f"/version: {version}",
            f"/healthz: {healthz}",
            f"/readyz:  {readyz}",
            f"/snapshot: {snap}",
        ])
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"snapshot error: {type(e).__name__}: {e}")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("? Access denied.")
        return
    await update.message.reply_text("BOOT/ADMIN REPORT\n\n" + await runtime_report(full=True))

async def grant_admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("Access denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /grant_admin <user_id>")
        return
    uid = int(context.args[0])
    await grant_role(uid, "admin", granted_by=int(update.effective_user.id))
    await update.message.reply_text(f"OK: granted admin to {uid}")

async def revoke_admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("Access denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /revoke_admin <user_id>")
        return
    uid = int(context.args[0])
    await revoke_role(uid, "admin")
    await update.message.reply_text(f"OK: revoked admin from {uid}")

async def admins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_rbac(update):
        await update.message.reply_text("Access denied.")
        return
    admins = await list_users_with_role("admin")
    lines = ["ADMINS:"]
    if not admins:
        lines.append("(none)")

    await update.message.reply_text("\n".join(lines))

async def dm_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_rbac(update):
        await update.message.reply_text("Access denied.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /dm <user_id> <msg>")
        return
    uid = int(context.args[0])
    msg = " ".join(context.args[1:])
    await context.bot.send_message(chat_id=uid, text=msg)
    await update.message.reply_text("OK: sent.")

async def broadcast_admins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("Access denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast_admins <msg>")
        return
    msg = " ".join(context.args)
    admins = await list_users_with_role("admin")
    sent = 0
    for a in admins:
        try:
            await context.bot.send_message(chat_id=int(a["user_id"]), text=msg)
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"OK: broadcasted to {sent} admins.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    e = context.error
    brief = update_brief(update) if isinstance(update, Update) else {}
    log_json(logging.ERROR, "bot_error", error_type=type(e).__name__, error=str(e), trace=exc_to_str(e), **brief)
    if isinstance(e, Conflict):
        log_json(logging.ERROR, "bot_conflict_409", **brief)

async def post_init(app):
    await init_infrastructure()
    if ADMIN_CHAT_ID:
        await app.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text="BOOT/ADMIN REPORT\n\n" + await runtime_report(full=True))

    # Telegram official commands (autocomplete)
    try:
        await app.bot.set_my_commands([
            BotCommand("start","Start"),
            BotCommand("menu","Show menu"),
            BotCommand("status","Infra status"),
            BotCommand("health","Health report"),
            BotCommand("whoami","User info"),
            BotCommand("donate","Support / donate"),
            BotCommand("admins","List admins"),
            BotCommand("grant_admin","(owner) Grant admin"),
            BotCommand("revoke_admin","(owner) Revoke admin"),
            BotCommand("dm","DM a user (admin)"),
            BotCommand("broadcast_admins","(owner) Broadcast to admins"),
        ])
    except Exception:
        pass

def _safe_add_cmd(app, name: str, func, with_latency_fn):
    """
    Register a CommandHandler only if func exists.
    Prevents startup crashes due to NameError while iterating fast.
    """
    try:
        if func is None:
            return
        app.add_handler(CommandHandler(name, with_latency_fn(name, func)))
    except NameError:
        # func name not defined in module globals
        return
    except Exception:
        logger.exception("safe_add_cmd failed for %s", name)

async def points_cmd(update, context):
    """
    /points -> show internal wallet balance for current Telegram user.
    """
    try:
        u = getattr(update, "effective_user", None)
        if u is None or getattr(u, "id", None) is None:
            return
        bal = await get_points_balance(int(u.id))
        msg = f"points balance: {bal}"
        m = getattr(update, "effective_message", None)
        if m is not None:
            await m.reply_text(msg)
    except Exception as e:
        logger.exception("points_cmd failed")
        try:
            m = getattr(update, "effective_message", None)
            if m is not None:
                await m.reply_text(f"points error: {type(e).__name__}")
        except Exception:
            pass

async def credit_points_cmd(update, context):
    """
    /credit_points <telegram_id> <amount> <ref>
    Admin only. Idempotent by (user_id, ref) unique constraint.
    """
    try:
        # admin check
        if not is_admin(update):
            m = getattr(update, "effective_message", None)
            if m is not None:
                await m.reply_text("Not authorized.")
            return

        args = getattr(context, "args", []) or []
        if len(args) < 3:
            m = getattr(update, "effective_message", None)
            if m is not None:
                await m.reply_text("Usage: /credit_points <telegram_id> <amount> <ref>")
            return

        user_id = int(args[0])
        amount = int(args[1])
        ref = str(args[2])

        # add_points already exists and uses DB
        await add_points(user_id, amount, ref=ref, reason="admin_credit")
        m = getattr(update, "effective_message", None)
        if m is not None:
            await m.reply_text(f"Credited {amount} to {user_id} (ref={ref}).")
    except IntegrityError:
        m = getattr(update, "effective_message", None)
        if m is not None:
            await m.reply_text("Duplicate ref (already credited).")
    except Exception as e:
        logger.exception("credit_points_cmd failed")
        try:
            m = getattr(update, "effective_message", None)
            if m is not None:
                await m.reply_text(f"credit_points error: {type(e).__name__}")
        except Exception:
            pass

async def bsc_token_cmd(update, context):
    """
    /bsc_token -> token metadata from BSC (admin only for now)
    """
    try:
        if not is_admin(update):
            m = getattr(update, "effective_message", None)
            if m is not None:
                await m.reply_text("Not authorized.")
            return

        from bsc.token import token_meta
        meta = token_meta()
        import json
        m = getattr(update, "effective_message", None)
        if m is not None:
            await m.reply_text(json.dumps(meta, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.exception("bsc_token_cmd failed")
        m = getattr(update, "effective_message", None)
        if m is not None:
            await m.reply_text(f"bsc_token error: {type(e).__name__}")

async def bsc_balance_cmd(update, context):
    """
    /bsc_balance <address>
    """
    try:
        if not is_admin(update):
            m = getattr(update, "effective_message", None)
            if m is not None:
                await m.reply_text("Not authorized.")
            return

        args = getattr(context, "args", []) or []
        if len(args) < 1:
            m = getattr(update, "effective_message", None)
            if m is not None:
                await m.reply_text("Usage: /bsc_balance <address>")
            return

        addr = str(args[0]).strip()
        from bsc.token import balance_of
        bal = balance_of(addr)
        import json
        m = getattr(update, "effective_message", None)
        if m is not None:
            await m.reply_text(json.dumps(bal, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.exception("bsc_balance_cmd failed")
        m = getattr(update, "effective_message", None)
        if m is not None:
            await m.reply_text(f"bsc_balance error: {type(e).__name__}")

def build_application():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set")
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", with_latency("start", start_cmd)))
    app.add_handler(CommandHandler("menu", with_latency("menu", menu_cmd)))
    app.add_handler(CommandHandler("status", with_latency("status", status_cmd)))
    app.add_handler(CommandHandler("health", with_latency("health", health_cmd)))
    app.add_handler(CommandHandler("healthz", with_latency("healthz", healthz_cmd)))
    app.add_handler(CommandHandler("readyz", with_latency("readyz", readyz_cmd)))
    app.add_handler(CommandHandler("donate", with_latency("donate", donate_cmd)))
    app.add_handler(CommandHandler("vars", with_latency("vars", vars_cmd)))
    app.add_handler(CommandHandler("webhook", with_latency("webhook", webhookinfo_cmd)))
    app.add_handler(CommandHandler("diag", with_latency("diag", diag_cmd)))
    app.add_handler(CommandHandler("pingdb", with_latency("pingdb", pingdb_cmd)))
    app.add_handler(CommandHandler("pingredis", with_latency("pingredis", pingredis_cmd)))
    app.add_handler(CommandHandler("whoami", with_latency("whoami", whoami_cmd)))
    app.add_handler(CommandHandler("snapshot", with_latency("snapshot", snapshot_cmd)))
    app.add_handler(CommandHandler("admin", with_latency("admin", admin_cmd)))
    app.add_handler(CommandHandler("grant_admin", with_latency("grant_admin", grant_admin_cmd)))
    app.add_handler(CommandHandler("revoke_admin", with_latency("revoke_admin", revoke_admin_cmd)))
    app.add_handler(CommandHandler("admins", with_latency("admins", admins_cmd)))
    app.add_handler(CommandHandler("dm", with_latency("dm", dm_cmd)))
    app.add_handler(CommandHandler("broadcast_admins", with_latency("broadcast_admins", broadcast_admins_cmd)))

    # === Economy commands (Commit A) ===
    app.add_handler(CommandHandler("ref", with_latency("ref", ref_cmd)))
    app.add_handler(CommandHandler("my", with_latency("my", my_cmd)))
    app.add_handler(CommandHandler("buy", with_latency("buy", buy_cmd)))
    app.add_handler(CommandHandler("claim", with_latency("claim", claim_cmd)))
    app.add_handler(CommandHandler("pending", with_latency("pending", pending_cmd)))
    app.add_handler(CommandHandler("approve", with_latency("approve", approve_cmd)))
    app.add_handler(CommandHandler("reject", with_latency("reject", reject_cmd)))
    app.add_handler(CommandHandler("add_account", with_latency("add_account", add_account_cmd)))
    _safe_add_cmd(app, "points", globals().get("points_cmd"), with_latency)
    _safe_add_cmd(app, "credit_points", globals().get("credit_points_cmd"), with_latency)
    app.add_handler(CommandHandler("prices", with_latency("prices", prices_cmd)))
    app.add_handler(CommandHandler("set_price", with_latency("set_price", set_price_cmd)))
    app.add_handler(CommandHandler("trade", with_latency("trade", trade_cmd)))

    return app

# --- BOT COMMANDS: /healthz and /readyz (mirror HTTP endpoints) ---
import json
import time
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy.exc import IntegrityError

async def healthz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # mirror HTTP /healthz shape
        payload = {"ok": True, "uptime_s": _uptime_s(), "git_sha": (git_sha() if callable(globals().get("git_sha")) else None)}
    except Exception as e:
        payload = {"ok": False, "error": str(e)}
    await update.effective_message.reply_text(json.dumps(payload, ensure_ascii=False))

async def readyz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    t0 = time.perf_counter()
    try:
        # lightweight readiness: if runtime_report exists use it; else just ok
        rr = globals().get("runtime_report")
        if rr:
            _ = await rr(full=False)
        payload = {"ok": True, "elapsed_ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as e:
        payload = {"ok": False, "error": str(e), "elapsed_ms": int((time.perf_counter() - t0) * 1000)}
    await update.effective_message.reply_text(json.dumps(payload, ensure_ascii=False))



