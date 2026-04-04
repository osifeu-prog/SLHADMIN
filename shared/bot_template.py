"""
SLH Minimal Bot Template - used for bots without dedicated code.
Provides: /start, /premium, payment proof handling, admin approve/reject.

Usage:
    BOT_KEY=campaign BOT_DESCRIPTION="קמפיינים שיווקיים" python bot_template.py
"""
import os
import sys
import asyncio
import logging

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command

sys.path.insert(0, "/app/shared")
from slh_payments.payment_gate import PaymentGate
from slh_payments.config import ADMIN_USER_ID, BotPricing
from slh_payments import db as pay_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("slh.bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_KEY = os.getenv("BOT_KEY", "generic").strip()
BOT_DISPLAY_NAME = os.getenv("BOT_DISPLAY_NAME", "SLH Bot").strip()
BOT_DESCRIPTION = os.getenv("BOT_DESCRIPTION", "\u05e9\u05d9\u05e8\u05d5\u05ea SLH").strip()
PRICE_ILS = float(os.getenv("PRICE_ILS", "41"))
PRICE_TON = float(os.getenv("PRICE_TON", "2.0"))

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN missing")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# Create pricing
pricing = BotPricing(
    bot_name=BOT_DISPLAY_NAME,
    price_ils=PRICE_ILS,
    price_ton=PRICE_TON,
    description_he=BOT_DESCRIPTION,
    features=[],
)

# Register payment gate
gate = PaymentGate(BOT_KEY, bot=bot, dp=dp)
gate.pricing = pricing
gate.register_handlers()


@dp.message(Command("start"))
async def start_cmd(m: types.Message):
    is_paid = await pay_db.is_premium(m.from_user.id, BOT_KEY)
    status = "\u2705 Premium" if is_paid else "\U0001f512 Free"

    await m.answer(
        f"\U0001f680 {BOT_DISPLAY_NAME}\n\n"
        f"{BOT_DESCRIPTION}\n\n"
        f"\u05de\u05e6\u05d1: {status}\n\n"
        "\u05e4\u05e7\u05d5\u05d3\u05d5\u05ea:\n"
        "/premium - \u05e9\u05d3\u05e8\u05d5\u05d2 \u05dc\u05e4\u05e8\u05d9\u05de\u05d9\u05d5\u05dd\n"
        "/status  - \u05de\u05e6\u05d1 \u05d7\u05e9\u05d1\u05d5\u05df\n"
        "/help    - \u05e2\u05d6\u05e8\u05d4",
    )
    await pay_db.log_event("user.start", BOT_KEY, m.from_user.id)


@dp.message(Command("status"))
async def status_cmd(m: types.Message):
    is_paid = await pay_db.is_premium(m.from_user.id, BOT_KEY)
    uname = m.from_user.username or "?"
    premium_str = "\u2705 \u05db\u05df" if is_paid else "\u274c \u05dc\u05d0"
    await m.answer(
        f"\U0001f4ca {BOT_DISPLAY_NAME}\n\n"
        f"User ID: {m.from_user.id}\n"
        f"Username: {uname}\n"
        f"Premium: {premium_str}\n\n"
        f"\U0001f4b0 \u05de\u05d7\u05d9\u05e8: {PRICE_ILS} \u20aa / {PRICE_TON} TON\n"
        "\u05dc\u05e9\u05d3\u05e8\u05d5\u05d2 \u2192 /premium",
    )


@dp.message(Command("help"))
async def help_cmd(m: types.Message):
    await m.answer(
        f"{BOT_DISPLAY_NAME} - \u05e2\u05d6\u05e8\u05d4\n\n"
        "/start   - \u05d4\u05ea\u05d7\u05dc\u05d4\n"
        "/premium - \u05e9\u05d3\u05e8\u05d5\u05d2 \u05dc\u05e4\u05e8\u05d9\u05de\u05d9\u05d5\u05dd\n"
        "/status  - \u05de\u05e6\u05d1 \u05d7\u05e9\u05d1\u05d5\u05df\n"
        "/help    - \u05e2\u05d6\u05e8\u05d4\n\n"
        "\u05e9\u05dc\u05d7 \u05e6\u05d9\u05dc\u05d5\u05dd \u05de\u05e1\u05da \u05e9\u05dc \u05ea\u05e9\u05dc\u05d5\u05dd \u05db\u05d3\u05d9 \u05dc\u05d4\u05e4\u05e2\u05d9\u05dc \u05e4\u05e8\u05d9\u05de\u05d9\u05d5\u05dd.",
    )


async def main():
    await pay_db.init_schema()
    logger.info("=" * 50)
    logger.info("SLH SPARK | %s (%s)", BOT_DISPLAY_NAME, BOT_KEY)
    logger.info("=" * 50)
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
