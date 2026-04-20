"""
Guardian Operations commands — admin-only bridge between TG and the slh-api Guardian endpoints.

Commands added:
    /gr_check <user_id>              Check ZUZ/ban status
    /gr_report <user_id> <reason>    File a fraud report (severity=medium)
    /gr_report_high <user_id> <reason>    File with severity=high
    /gr_blacklist                    Show top 10 flagged users
    /gr_scan <text>                  Scan a message for scam patterns
    /gr_stats                        Show aggregate fraud intel
    /gr_ping                         Quick API health ping

All results echoed in Hebrew (user-facing) with English keys for the data.
"""
from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import ContextTypes

from bot import slh_api_client as api
from bot.main import is_admin, _log_cmd

logger = logging.getLogger(__name__)


def _fmt_status(data: dict) -> str:
    if not data:
        return "❌ אין תגובה מהשרת"
    if not data.get("flagged"):
        return f"✅ נקי · ZUZ {data.get('zuz_score', 0):.0f}"
    parts = [
        f"🚨 מסומן · ZUZ {data.get('zuz_score', 0):.0f}",
        f"דיווחים סה\"כ: {data.get('total_reports', 0)}",
        f"חסום פעיל: {'כן' if data.get('ban_active') else 'לא'}",
    ]
    if data.get("ban_reason"):
        parts.append(f"סיבה: {data['ban_reason']}")
    recent = data.get("recent_reports") or []
    if recent:
        parts.append("דיווחים אחרונים:")
        for r in recent[:3]:
            parts.append(f"  • [{r.get('severity','?')}] {r.get('reason','')[:60]}")
    return "\n".join(parts)


async def gr_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "gr_ping")
    if not is_admin(update):
        return await update.message.reply_text("❌ מוגבל לאדמין")
    ok = await api.health_check()
    await update.message.reply_text(f"slh-api: {'✅ חי' if ok else '❌ מת'}\n{api.API_URL}/api/health")


async def gr_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "gr_check")
    if not is_admin(update):
        return await update.message.reply_text("❌ מוגבל לאדמין")
    if not context.args:
        return await update.message.reply_text("שימוש: /gr_check <user_id>")
    try:
        uid = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("user_id חייב להיות מספר")
    data = await api.check_user(uid)
    await update.message.reply_text(f"👤 User {uid}\n{_fmt_status(data or {})}")


async def _gr_report_impl(update: Update, context: ContextTypes.DEFAULT_TYPE, severity: str):
    if not is_admin(update):
        return await update.message.reply_text("❌ מוגבל לאדמין")
    if len(context.args or []) < 2:
        return await update.message.reply_text(
            f"שימוש: /gr_report{'_high' if severity=='high' else ''} <user_id> <reason>"
        )
    try:
        uid = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("user_id חייב להיות מספר")
    reason = " ".join(context.args[1:])[:500]
    reporter = update.effective_user.id
    data = await api.report_fraud(
        reporter_id=reporter,
        reported_user_id=uid,
        reason=reason,
        severity=severity,
    )
    if not data:
        return await update.message.reply_text("❌ שליחה נכשלה — בדוק SLH_ADMIN_KEY ולוגים")
    msg = data.get("message", "דיווח נרשם")
    await update.message.reply_text(f"✅ {msg}\nReport ID: {data.get('report_id','?')}")


async def gr_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "gr_report")
    await _gr_report_impl(update, context, "medium")


async def gr_report_high(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "gr_report_high")
    await _gr_report_impl(update, context, "high")


async def gr_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "gr_blacklist")
    if not is_admin(update):
        return await update.message.reply_text("❌ מוגבל לאדמין")
    users = await api.fetch_blacklist(limit=10, min_zuz=0)
    if users is None:
        return await update.message.reply_text("❌ שליחה נכשלה")
    if not users:
        return await update.message.reply_text("✨ רשימה ריקה — אין משתמשים מסומנים")
    lines = ["🚨 10 הרשומים העליונים:"]
    for u in users[:10]:
        uid = u.get("user_id", "?")
        zuz = u.get("zuz_score", 0)
        ban = "🔒" if u.get("ban_active") else "⚠️"
        lines.append(f"{ban} {uid} · ZUZ {float(zuz):.0f}")
    await update.message.reply_text("\n".join(lines))


async def gr_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "gr_scan")
    if not context.args:
        return await update.message.reply_text("שימוש: /gr_scan <טקסט>")
    text = " ".join(context.args)[:2000]
    data = await api.scan_message(text)
    if not data:
        return await update.message.reply_text("❌ שליחה נכשלה")
    risk = data.get("risk_score", 0)
    flags = data.get("flags") or []
    lines = [
        f"🔍 ניתוח הודעה:",
        f"Risk score: {risk}/100",
    ]
    if flags:
        lines.append("דגלים: " + ", ".join(flags[:5]))
    await update.message.reply_text("\n".join(lines))


async def gr_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_cmd(update, "gr_stats")
    data = await api.get_stats()
    if not data:
        return await update.message.reply_text("❌ שליחה נכשלה")
    lines = [
        "📊 Guardian Stats:",
        f"סה\"כ דיווחים: {data.get('total_reports', 0)}",
        f"משתמשים מסומנים: {data.get('flagged_users', 0)}",
        f"משתמשים חסומים: {data.get('banned_users', 0)}",
        f"ZUZ ממוצע: {data.get('avg_zuz', 0):.1f}",
    ]
    await update.message.reply_text("\n".join(lines))


def register_handlers(app):
    """Wire all /gr_* commands into the Application."""
    from telegram.ext import CommandHandler
    app.add_handler(CommandHandler("gr_ping", gr_ping))
    app.add_handler(CommandHandler("gr_check", gr_check))
    app.add_handler(CommandHandler("gr_report", gr_report))
    app.add_handler(CommandHandler("gr_report_high", gr_report_high))
    app.add_handler(CommandHandler("gr_blacklist", gr_blacklist))
    app.add_handler(CommandHandler("gr_scan", gr_scan))
    app.add_handler(CommandHandler("gr_stats", gr_stats))
    logger.info("guardian_ops: 7 handlers registered")
