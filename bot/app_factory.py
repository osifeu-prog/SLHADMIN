import logging

app.add_handler(CommandHandler("token_info", with_latency("token_info", token_info_cmd)))
app.add_handler(CommandHandler("onchain_balance", with_latency("onchain_balance", onchain_balance_cmd)))
import logging

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
        "\u05d1\u05e8\u05d5\u05da \u05d4\u05d1\u05d0 \u05dc-SLH Guardian.\n"
        "\u05de\u05e2\u05e8\u05db\u05ea \u05dc\u05e0\u05d9\u05d8\u05d5\u05e8 \u05ea\u05e9\u05ea\u05d9\u05d5\u05ea, \u05d2\u05d9\u05d1\u05d5\u05d9, \u05e0\u05d9\u05d4\u05d5\u05dc \u05ea\u05e4\u05e2\u05d5\u05dc, \u05d5\u05d4\u05db\u05e0\u05d4 \u05dc-SaaS \u05de\u05dc\u05d0.\n\n"
        "Commands:\n"
        "/status    \u05e1\u05d8\u05d8\u05d5\u05e1 DB/Redis/Alembic\n"
        "/menu      \u05ea\u05e4\u05e8\u05d9\u05d8\n"
        "/whoami    \u05de\u05d9 \u05d0\u05e0\u05d9\n"
        "/health    \u05de\u05e6\u05d1 \u05de\u05e2\u05e8\u05db\u05ea\n"
        "/support   \U0001f6ce\ufe0f \u05d1\u05e7\u05e9 \u05ea\u05de\u05d9\u05db\u05d4 \u05de\u05e8\u05d7\u05d5\u05e7\n"
        "/donate    \u05ea\u05de\u05d9\u05db\u05d4 / \u05ea\u05e8\u05d5\u05de\u05d4\n"
    )

    footer_full = footer

    text = "```\n" + ASCII_BANNER.strip() + "\n```\n" + footer_full

    if is_admin(update):
        admin_tail = (
            "\n/admin     admin report\n/vars      Vars (SET/MISSING)\n/webhook   Webhook Info\n/diag      diagnostics\n/pingdb    DB latency\n/pingredis Redis latency\n/snapshot  snapshot\n"
            "\n\U0001f6ce\ufe0f Remote Support:\n"
            "/queue     pending requests\n"
            "/connect   start session\n"
            "/say       send message\n"
            "/guide     send guide step\n"
            "/checklist send checklist\n"
            "/screenshot request screenshot\n"
            "/sysinfo   request system info\n"
            "/quickfix  send fix template\n"
            "/sessions  active sessions\n"
            "/disconnect end session\n"
        )
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
    else:
        for r in reqs:
            rid = r.get("id")
            kind = r.get("kind")
            amt = r.get("amount")
            st = r.get("status")
            lines.append(f"- #{rid} {kind} {amt} ({st})")

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


# ------------------------------
# On-chain (read-only) helpers
# ------------------------------
def _bsc_web3():
    from web3 import Web3
    rpc = os.getenv("BSC_RPC_URL") or "https://bsc-dataseed.binance.org/"
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
    if not w3.is_connected():
        raise RuntimeError("BSC RPC not reachable")
    return w3

def _load_token_contract():
    import json
    from web3 import Web3
    token = os.getenv("BSC_TOKEN_ADDRESS")
    abi_path = os.getenv("BSC_ABI_PATH") or "bsc/abi/FullFeatureToken.json"
    if not token:
        raise RuntimeError("Missing BSC_TOKEN_ADDRESS")
    if not abi_path or not os.path.exists(abi_path):
        raise RuntimeError(f"Missing ABI file at {abi_path}")
    w3 = _bsc_web3()
    abi = json.load(open(abi_path, "r", encoding="utf-8"))
    c = w3.eth.contract(address=Web3.to_checksum_address(token), abi=abi)
    return w3, c

async def token_info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /token_info -> show token metadata from BSC (read-only)
    """
    try:
        _, c = _load_token_contract()
        name = c.functions.name().call()
        sym  = c.functions.symbol().call()
        dec  = c.functions.decimals().call()
        total = c.functions.totalSupply().call()

        token_addr = os.getenv("BSC_TOKEN_ADDRESS")
        msg = (
            "TOKEN INFO (BSC)\n"
            f"name: {name}\n"
            f"symbol: {sym}\n"
            f"decimals: {dec}\n"
            f"totalSupply(raw): {total}\n"
            f"contract: {token_addr}"
        )
        await update.effective_message.reply_text(msg)
    except Exception as e:
        await update.effective_message.reply_text(f"token_info error: {type(e).__name__}: {e}")

async def onchain_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /onchain_balance <0xAddress> -> show ERC20 balanceOf on BSC (read-only)
    """
    try:
        if not context.args or len(context.args) < 1:
            await update.effective_message.reply_text("Usage: /onchain_balance <0xAddress>")
            return
        addr = str(context.args[0]).strip()
        w3, c = _load_token_contract()
        dec = c.functions.decimals().call()
        bal = c.functions.balanceOf(w3.to_checksum_address(addr)).call()
        msg = (
            "ONCHAIN BALANCE (BSC)\n"
            f"address: {addr}\n"
            f"balance(raw): {bal}\n"
            f"balance: {bal / (10 ** dec)}"
        )
        await update.effective_message.reply_text(msg)
    except Exception as e:
        await update.effective_message.reply_text(f"onchain_balance error: {type(e).__name__}: {e}")

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

# ============================================================
# REMOTE SUPPORT MODULE — TeamViewer-like customer assistance
# ============================================================
# Active support sessions: {client_chat_id: {admin_id, started, notes, steps}}
_support_sessions = {}
_support_queue = []  # Waiting clients: [{chat_id, username, issue, ts}]

async def support_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Client: /support <issue> — request remote help from admin"""
    args = context.args or []
    issue = " ".join(args) if args else "General help needed"
    uid = update.effective_user.id
    uname = update.effective_user.username or str(uid)

    # Add to queue
    import time as _t
    entry = {"chat_id": uid, "username": uname, "issue": issue, "ts": _t.time()}
    # Remove existing entry for same user
    _support_queue[:] = [q for q in _support_queue if q["chat_id"] != uid]
    _support_queue.append(entry)

    await update.effective_message.reply_text(
        f"\U0001f6ce\ufe0f \u05d1\u05e7\u05e9\u05ea \u05ea\u05de\u05d9\u05db\u05d4 \u05e0\u05e9\u05dc\u05d7\u05d4!\n"
        f"\u05d1\u05e2\u05d9\u05d4: {issue}\n"
        f"\u05de\u05d7\u05db\u05d4 \u05dc\u05ea\u05e9\u05d5\u05d1\u05d4 \u05de\u05d4\u05ea\u05de\u05d9\u05db\u05d4...\n\n"
        f"\U0001f6ce\ufe0f Support request sent!\n"
        f"Issue: {issue}\n"
        f"Waiting for admin response..."
    )

    # Notify admin
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_CHAT_ID),
                text=f"\U0001f6a8 NEW SUPPORT REQUEST\n"
                     f"User: @{uname} ({uid})\n"
                     f"Issue: {issue}\n\n"
                     f"Use /connect {uid} to start session\n"
                     f"Use /queue to see all pending requests"
            )
        except Exception:
            pass

async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /queue — show pending support requests"""
    if not is_admin(update):
        await update.effective_message.reply_text("\u26d4 Admin only")
        return
    if not _support_queue:
        await update.effective_message.reply_text("\u2705 No pending support requests")
        return
    import time as _t
    lines = ["\U0001f4cb SUPPORT QUEUE:"]
    for i, q in enumerate(_support_queue, 1):
        age = int(_t.time() - q["ts"])
        age_str = f"{age//60}m" if age > 60 else f"{age}s"
        lines.append(f"{i}. @{q['username']} ({q['chat_id']}) — {q['issue']} [{age_str} ago]")
    lines.append(f"\nUse /connect <user_id> to start session")
    await update.effective_message.reply_text("\n".join(lines))

async def connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /connect <user_id> — start remote support session"""
    if not is_admin(update):
        await update.effective_message.reply_text("\u26d4 Admin only")
        return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /connect <user_id>")
        return
    import time as _t
    client_id = int(args[0])
    _support_sessions[client_id] = {
        "admin_id": update.effective_user.id,
        "started": _t.time(),
        "notes": [],
        "steps": []
    }
    # Remove from queue
    _support_queue[:] = [q for q in _support_queue if q["chat_id"] != client_id]

    await update.effective_message.reply_text(
        f"\U0001f50c SESSION STARTED with {client_id}\n\n"
        f"Commands:\n"
        f"/say {client_id} <msg> \u2014 Send message to client\n"
        f"/guide {client_id} <step> \u2014 Send numbered step\n"
        f"/checklist {client_id} <items> \u2014 Send troubleshooting checklist\n"
        f"/screenshot {client_id} \u2014 Request screenshot from client\n"
        f"/sysinfo {client_id} \u2014 Request system info\n"
        f"/note {client_id} <note> \u2014 Add internal note\n"
        f"/disconnect {client_id} \u2014 End session\n"
        f"/sessions \u2014 View active sessions"
    )

    try:
        await context.bot.send_message(
            chat_id=client_id,
            text="\U0001f50c \u05d4\u05ea\u05d7\u05d1\u05e8\u05ea \u05dc\u05e1\u05e9\u05df \u05ea\u05de\u05d9\u05db\u05d4 \u05de\u05e8\u05d7\u05d5\u05e7!\n"
                 "\U0001f50c Connected to remote support session!\n\n"
                 "\u05d4\u05d8\u05db\u05e0\u05d0\u05d9 \u05e9\u05dc\u05e0\u05d5 \u05de\u05d7\u05d5\u05d1\u05e8 \u05d5\u05d9\u05e1\u05d9\u05d9\u05e2 \u05dc\u05da.\n"
                 "Our technician is connected and will assist you.\n\n"
                 "\u05ea\u05d5\u05db\u05dc \u05dc\u05e9\u05dc\u05d5\u05d7 \u05d4\u05d5\u05d3\u05e2\u05d5\u05ea, \u05e6\u05d9\u05dc\u05d5\u05de\u05d9 \u05de\u05e1\u05da \u05d5\u05ea\u05de\u05d5\u05e0\u05d5\u05ea.\n"
                 "You can send messages, screenshots, and photos."
        )
    except Exception as e:
        await update.effective_message.reply_text(f"\u26a0\ufe0f Could not reach user {client_id}: {e}")

async def say_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /say <user_id> <message> — send message to client"""
    if not is_admin(update):
        return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /say <user_id> <message>")
        return
    client_id = int(args[0])
    msg = " ".join(args[1:])
    try:
        await context.bot.send_message(
            chat_id=client_id,
            text=f"\U0001f9d1\u200d\U0001f4bb \u05d8\u05db\u05e0\u05d0\u05d9 SLH:\n{msg}"
        )
        await update.effective_message.reply_text(f"\u2705 Sent to {client_id}")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c Failed: {e}")

async def guide_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /guide <user_id> <step instructions> — send numbered guide step"""
    if not is_admin(update):
        return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /guide <user_id> <step description>")
        return
    client_id = int(args[0])
    step_text = " ".join(args[1:])
    session = _support_sessions.get(client_id, {"steps": []})
    session.setdefault("steps", []).append(step_text)
    step_num = len(session["steps"])
    try:
        await context.bot.send_message(
            chat_id=client_id,
            text=f"\U0001f4cb \u05e9\u05dc\u05d1 {step_num}:\n{step_text}\n\nStep {step_num}:\n{step_text}"
        )
        await update.effective_message.reply_text(f"\u2705 Step {step_num} sent to {client_id}")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c Failed: {e}")

async def checklist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /checklist <user_id> <item1 | item2 | item3> — send troubleshooting checklist"""
    if not is_admin(update):
        return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /checklist <user_id> item1 | item2 | item3")
        return
    client_id = int(args[0])
    items_raw = " ".join(args[1:])
    items = [i.strip() for i in items_raw.split("|") if i.strip()]
    checklist = "\n".join([f"\u2610 {i}" for i in items])
    try:
        await context.bot.send_message(
            chat_id=client_id,
            text=f"\U0001f4dd \u05e8\u05e9\u05d9\u05de\u05ea \u05d1\u05d3\u05d9\u05e7\u05d4 / Troubleshooting Checklist:\n\n{checklist}\n\n\u05e1\u05de\u05df \u05db\u05dc \u05e4\u05e8\u05d9\u05d8 \u05e9\u05d1\u05d3\u05e7\u05ea \u05d1-\u2705 / Mark done items with \u2705"
        )
        await update.effective_message.reply_text(f"\u2705 Checklist ({len(items)} items) sent to {client_id}")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c Failed: {e}")

async def screenshot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /screenshot <user_id> — request screenshot from client"""
    if not is_admin(update):
        return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /screenshot <user_id>")
        return
    client_id = int(args[0])
    try:
        await context.bot.send_message(
            chat_id=client_id,
            text="\U0001f4f8 \u05d4\u05d8\u05db\u05e0\u05d0\u05d9 \u05de\u05d1\u05e7\u05e9 \u05e6\u05d9\u05dc\u05d5\u05dd \u05de\u05e1\u05da\n"
                 "\U0001f4f8 The technician requests a screenshot\n\n"
                 "\u05d0\u05e0\u05d0 \u05e6\u05dc\u05dd \u05e6\u05d9\u05dc\u05d5\u05dd \u05de\u05e1\u05da \u05d5\u05e9\u05dc\u05d7 \u05db\u05d0\u05df \u05db\u05ea\u05de\u05d5\u05e0\u05d4.\n"
                 "Please take a screenshot and send it here as a photo.\n\n"
                 "Windows: Win+Shift+S\nMac: Cmd+Shift+4"
        )
        await update.effective_message.reply_text(f"\u2705 Screenshot request sent to {client_id}")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c Failed: {e}")

async def sysinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /sysinfo <user_id> — request system info from client"""
    if not is_admin(update):
        return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /sysinfo <user_id>")
        return
    client_id = int(args[0])
    try:
        await context.bot.send_message(
            chat_id=client_id,
            text="\U0001f4bb \u05d4\u05d8\u05db\u05e0\u05d0\u05d9 \u05de\u05d1\u05e7\u05e9 \u05e4\u05e8\u05d8\u05d9 \u05de\u05e2\u05e8\u05db\u05ea\n"
                 "\U0001f4bb System info requested\n\n"
                 "\u05d0\u05e0\u05d0 \u05e4\u05ea\u05d7 CMD (\u05e9\u05d5\u05e8\u05ea \u05e4\u05e7\u05d5\u05d3\u05d4) \u05d5\u05d4\u05e8\u05e5:\n"
                 "Please open CMD (Command Prompt) and run:\n\n"
                 "`systeminfo | findstr /B /C:\"OS\" /C:\"System\" /C:\"Total Physical\"`\n\n"
                 "\u05d5\u05d2\u05dd / and also:\n"
                 "`ipconfig /all | findstr /i \"IPv4 DNS Default\"`\n\n"
                 "\u05d4\u05e2\u05ea\u05e7 \u05d0\u05ea \u05d4\u05ea\u05d5\u05e6\u05d0\u05d4 \u05db\u05d0\u05df / Paste the output here",
            parse_mode="Markdown"
        )
        await update.effective_message.reply_text(f"\u2705 System info request sent to {client_id}")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c Failed: {e}")

async def note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /note <user_id> <note> — add internal note to session"""
    if not is_admin(update):
        return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /note <user_id> <note text>")
        return
    client_id = int(args[0])
    note = " ".join(args[1:])
    session = _support_sessions.get(client_id)
    if not session:
        await update.effective_message.reply_text(f"\u26a0\ufe0f No active session for {client_id}")
        return
    import time as _t
    session["notes"].append({"text": note, "ts": _t.time()})
    await update.effective_message.reply_text(f"\U0001f4dd Note saved ({len(session['notes'])} total)")

async def disconnect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /disconnect <user_id> — end support session"""
    if not is_admin(update):
        return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /disconnect <user_id>")
        return
    client_id = int(args[0])
    session = _support_sessions.pop(client_id, None)
    if not session:
        await update.effective_message.reply_text(f"No active session for {client_id}")
        return
    import time as _t
    duration = int(_t.time() - session.get("started", _t.time()))
    dur_str = f"{duration//60}m {duration%60}s"

    try:
        await context.bot.send_message(
            chat_id=client_id,
            text="\u2705 \u05d4\u05e1\u05e9\u05df \u05d4\u05e1\u05ea\u05d9\u05d9\u05dd. \u05ea\u05d5\u05d3\u05d4 \u05e9\u05e4\u05e0\u05d9\u05ea \u05dc\u05e9\u05d9\u05e8\u05d5\u05ea SLH!\n"
                 "\u2705 Session ended. Thank you for using SLH support!\n\n"
                 "\u05d0\u05dd \u05e0\u05d3\u05e8\u05e9\u05ea \u05e2\u05d6\u05e8\u05d4 \u05e0\u05d5\u05e1\u05e4\u05ea, \u05e9\u05dc\u05d7 /support\n"
                 "Need more help? Send /support"
        )
    except Exception:
        pass

    summary = (
        f"\U0001f50c SESSION CLOSED\n"
        f"Client: {client_id}\n"
        f"Duration: {dur_str}\n"
        f"Steps sent: {len(session.get('steps', []))}\n"
        f"Notes: {len(session.get('notes', []))}"
    )
    await update.effective_message.reply_text(summary)

async def sessions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /sessions — list active support sessions"""
    if not is_admin(update):
        return
    if not _support_sessions:
        await update.effective_message.reply_text("\u2705 No active support sessions")
        return
    import time as _t
    lines = ["\U0001f50c ACTIVE SESSIONS:"]
    for cid, s in _support_sessions.items():
        dur = int(_t.time() - s.get("started", _t.time()))
        dur_str = f"{dur//60}m"
        lines.append(f"\u2022 {cid} \u2014 {dur_str} \u2014 {len(s.get('steps',[]))} steps, {len(s.get('notes',[]))} notes")
    lines.append(f"\nQueue: {len(_support_queue)} waiting")
    await update.effective_message.reply_text("\n".join(lines))

async def quickfix_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /quickfix <user_id> <template> — send pre-built fix templates"""
    if not is_admin(update):
        return
    args = context.args or []
    if len(args) < 2:
        templates = (
            "\U0001f527 QUICKFIX TEMPLATES:\n\n"
            "/quickfix <uid> restart \u2014 Restart instructions\n"
            "/quickfix <uid> cache \u2014 Clear cache/cookies\n"
            "/quickfix <uid> dns \u2014 Flush DNS\n"
            "/quickfix <uid> network \u2014 Network reset\n"
            "/quickfix <uid> update \u2014 Update software\n"
            "/quickfix <uid> safe \u2014 Safe mode boot\n"
            "/quickfix <uid> disk \u2014 Disk cleanup"
        )
        await update.effective_message.reply_text(templates)
        return

    client_id = int(args[0])
    template = args[1].lower()
    fixes = {
        "restart": "\U0001f504 \u05d4\u05e4\u05e2\u05dc\u05d4 \u05de\u05d7\u05d3\u05e9 / Restart:\n\n1. \u05e9\u05de\u05d5\u05e8 \u05d0\u05ea \u05db\u05dc \u05d4\u05e2\u05d1\u05d5\u05d3\u05d4\n   Save all work\n2. \u05dc\u05d7\u05e5 Start > Power > Restart\n   Click Start > Power > Restart\n3. \u05d4\u05de\u05ea\u05df \u05dc\u05d0\u05ea\u05d7\u05d5\u05dc \u05de\u05d7\u05d3\u05e9\n   Wait for full reboot\n4. \u05d1\u05d3\u05d5\u05e7 \u05d0\u05dd \u05d4\u05d1\u05e2\u05d9\u05d4 \u05e0\u05e4\u05ea\u05e8\u05d4\n   Check if the issue is resolved",
        "cache": "\U0001f9f9 \u05e0\u05d9\u05e7\u05d5\u05d9 \u05de\u05d8\u05de\u05d5\u05df / Clear Cache:\n\n\u05d1\u05d3\u05e4\u05d3\u05e4\u05df / In browser:\n1. \u05dc\u05d7\u05e5 Ctrl+Shift+Delete\n2. \u05e1\u05de\u05df \u05d4\u05db\u05dc / Select all\n3. \u05dc\u05d7\u05e5 Clear / \u05e0\u05e7\u05d4\n4. \u05e1\u05d2\u05d5\u05e8 \u05d0\u05ea \u05d4\u05d3\u05e4\u05d3\u05e4\u05df \u05d5\u05e4\u05ea\u05d7 \u05de\u05d7\u05d3\u05e9\n   Close browser and reopen",
        "dns": "\U0001f310 \u05e0\u05d9\u05e7\u05d5\u05d9 DNS / Flush DNS:\n\n1. \u05e4\u05ea\u05d7 CMD \u05db\u05de\u05e0\u05d4\u05dc / Open CMD as admin\n2. \u05d4\u05e8\u05e5 / Run:\n`ipconfig /flushdns`\n3. \u05d5\u05d2\u05dd / Also:\n`ipconfig /release`\n`ipconfig /renew`\n4. \u05d1\u05d3\u05d5\u05e7 \u05d7\u05d9\u05d1\u05d5\u05e8 / Check connection",
        "network": "\U0001f4e1 \u05d0\u05d9\u05e4\u05d5\u05e1 \u05e8\u05e9\u05ea / Network Reset:\n\n1. \u05e4\u05ea\u05d7 CMD \u05db\u05de\u05e0\u05d4\u05dc / Open CMD as admin\n2. \u05d4\u05e8\u05e5 / Run:\n`netsh winsock reset`\n`netsh int ip reset`\n3. \u05d4\u05e4\u05e2\u05dc \u05de\u05d7\u05d3\u05e9 / Restart PC\n4. \u05d7\u05d1\u05e8 \u05de\u05d7\u05d3\u05e9 \u05dc-WiFi / Reconnect WiFi",
        "update": "\U0001f4e6 \u05e2\u05d3\u05db\u05d5\u05e0\u05d9\u05dd / Updates:\n\n1. \u05e4\u05ea\u05d7 Settings > Update & Security\n2. \u05dc\u05d7\u05e5 Check for updates\n3. \u05d4\u05ea\u05e7\u05df \u05d4\u05db\u05dc / Install all\n4. \u05d4\u05e4\u05e2\u05dc \u05de\u05d7\u05d3\u05e9 \u05d0\u05dd \u05e0\u05d3\u05e8\u05e9 / Restart if needed",
        "safe": "\U0001f6e1\ufe0f \u05de\u05e6\u05d1 \u05d1\u05d8\u05d5\u05d7 / Safe Mode:\n\n1. \u05d4\u05e4\u05e2\u05dc \u05d0\u05ea \u05d4\u05de\u05d7\u05e9\u05d1 / Restart PC\n2. \u05dc\u05d7\u05e5 F8 \u05d1\u05d6\u05de\u05df \u05d4\u05d0\u05ea\u05d7\u05d5\u05dc\n   Press F8 during boot\n3. \u05d1\u05d7\u05e8 Safe Mode with Networking\n4. \u05d1\u05d3\u05d5\u05e7 \u05d0\u05ea \u05d4\u05d1\u05e2\u05d9\u05d4 / Test the issue\n\nWindows 10/11:\nSettings > Recovery > Restart now > Troubleshoot > Advanced > Startup Settings > Restart > F5",
        "disk": "\U0001f4be \u05e0\u05d9\u05e7\u05d5\u05d9 \u05d3\u05d9\u05e1\u05e7 / Disk Cleanup:\n\n1. \u05e4\u05ea\u05d7 / Open: cleanmgr\n2. \u05d1\u05d7\u05e8 \u05d3\u05d9\u05e1\u05e7 C: / Select C:\n3. \u05e1\u05de\u05df \u05d4\u05db\u05dc / Select all\n4. \u05dc\u05d7\u05e5 Clean up system files\n5. \u05e1\u05de\u05df \u05d4\u05db\u05dc \u05d5\u05d0\u05e9\u05e8 / Confirm & delete"
    }
    fix_text = fixes.get(template, f"\u26a0\ufe0f Unknown template: {template}")
    try:
        await context.bot.send_message(chat_id=client_id, text=fix_text, parse_mode="Markdown")
        await update.effective_message.reply_text(f"\u2705 Quickfix '{template}' sent to {client_id}")
    except Exception as e:
        await update.effective_message.reply_text(f"\u274c Failed: {e}")


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

    # === Remote Support commands ===
    app.add_handler(CommandHandler("support", with_latency("support", support_cmd)))
    app.add_handler(CommandHandler("queue", with_latency("queue", queue_cmd)))
    app.add_handler(CommandHandler("connect", with_latency("connect", connect_cmd)))
    app.add_handler(CommandHandler("say", with_latency("say", say_cmd)))
    app.add_handler(CommandHandler("guide", with_latency("guide", guide_cmd)))
    app.add_handler(CommandHandler("checklist", with_latency("checklist", checklist_cmd)))
    app.add_handler(CommandHandler("screenshot", with_latency("screenshot", screenshot_cmd)))
    app.add_handler(CommandHandler("sysinfo", with_latency("sysinfo", sysinfo_cmd)))
    app.add_handler(CommandHandler("note", with_latency("note", note_cmd)))
    app.add_handler(CommandHandler("disconnect", with_latency("disconnect", disconnect_cmd)))
    app.add_handler(CommandHandler("sessions", with_latency("sessions", sessions_cmd)))
    app.add_handler(CommandHandler("quickfix", with_latency("quickfix", quickfix_cmd)))

    # === Bot Manager commands ===
    try:
        from bot.bot_manager import register_bot_manager
        register_bot_manager(app, with_latency)
    except Exception as e:
        logging.warning(f"[BotManager] Failed to register: {e}")

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





