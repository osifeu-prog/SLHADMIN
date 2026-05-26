import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

TON_WALLET = os.getenv("TON_WALLET", "")

PLANS = {
    "basic": {
        "name": "בסיק",
        "price_usd": 9,
        "price_ton": 2.5,
        "features": ["בונוס יומי x2", "100 SLH לחודש", "סמל בסיק"],
    },
    "pro": {
        "name": "Pro",
        "price_usd": 29,
        "price_ton": 7.5,
        "features": ["בונוס יומי x5", "500 SLH לחודש", "סמל Pro", "עדיפות בלוח מובילים"],
    },
    "vip": {
        "name": "VIP",
        "price_usd": 99,
        "price_ton": 25,
        "features": ["בונוס יומי x10", "2000 SLH לחודש", "סמל VIP", "גישה ל-Alpha features", "20% רויילטיס"],
    },
}

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["⭐ *SLH Guardian Premium*
"]
    for key, plan in PLANS.items():
        lines.append(f"*{plan['name']}* — ${plan['price_usd']}/חודש ({plan['price_ton']} TON)")
        for f in plan['features']:
            lines.append(f"  • {f}")
        lines.append("")

    lines.append("כדי לשדרג, לחץ על התוכנית:")

    buttons = [
        [InlineKeyboardButton(f"⭐ {p['name']} — {p['price_ton']} TON", callback_data=f"premium_buy:{k}")]
        for k, p in PLANS.items()
    ]
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if not data.startswith("premium_buy:"):
        return
    key = data.split(":")[1]
    plan = PLANS.get(key)
    if not plan:
        return
    wallet = TON_WALLET or "UQ... (wallet not configured)"
    msg = (
        f"⭐ *תוכנית {plan['name']}*\n\n"
        f"מחיר: `{plan['price_ton']} TON` (~${plan['price_usd']}/חודש)\n\n"
        f"שלח `{plan['price_ton']} TON` לכתובת:\n"
        f"`{wallet}`\n\n"
        f"אחרי התשלום, שלח צילום אישור ל-@osifeu\_prog ויופעל ידנית."
    )
    await query.edit_message_text(msg, parse_mode="Markdown")

from telegram.ext import CallbackQueryHandler

def get_premium_handler():
    return CallbackQueryHandler(premium_callback, pattern=r"^premium_buy:")
