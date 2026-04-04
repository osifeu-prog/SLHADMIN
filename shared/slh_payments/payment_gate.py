"""
Universal Payment Gate for SLH Bots.

Usage with aiogram:
    gate = PaymentGate("botshop", bot, dp)
    gate.register_handlers()

Usage with python-telegram-bot:
    gate = PaymentGate("wallet", bot_app=app)
    gate.register_ptb_handlers()
"""
import logging
from typing import Optional

from .config import BOT_PRICING, PAYMENT_INSTRUCTIONS, ADMIN_USER_ID, BotPricing
from . import db

logger = logging.getLogger("slh.payment_gate")


class PaymentGate:
    def __init__(self, bot_key: str, bot=None, dp=None, bot_app=None):
        self.bot_key = bot_key
        self.pricing: BotPricing = BOT_PRICING.get(bot_key, BotPricing(bot_name=bot_key, price_ils=41))
        self.bot = bot          # aiogram Bot
        self.dp = dp            # aiogram Dispatcher
        self.bot_app = bot_app  # python-telegram-bot Application

    # ---- aiogram handlers ----

    def register_handlers(self):
        """Register payment handlers with aiogram Dispatcher."""
        if not self.dp:
            return
        from aiogram import F
        from aiogram.filters import Command
        from aiogram.types import Message, CallbackQuery

        @self.dp.message(Command("premium"))
        async def premium_cmd(m: Message):
            await self._handle_premium(m.from_user.id, m.from_user.username, m)

        @self.dp.message(Command("pay"))
        async def pay_cmd(m: Message):
            await self._handle_premium(m.from_user.id, m.from_user.username, m)

        @self.dp.message(F.photo)
        async def photo_handler(m: Message):
            await self._handle_photo_proof(m)

        @self.dp.callback_query(F.data.startswith("pay_approve:"))
        async def approve_cb(cb: CallbackQuery):
            await self._handle_approve(cb)

        @self.dp.callback_query(F.data.startswith("pay_reject:"))
        async def reject_cb(cb: CallbackQuery):
            await self._handle_reject(cb)

    async def _handle_premium(self, user_id: int, username: str, message):
        """Show premium pricing and payment instructions."""
        is_paid = await db.is_premium(user_id, self.bot_key)
        if is_paid:
            await message.answer(
                "\u2705 \u05d0\u05ea\u05d4 \u05db\u05d1\u05e8 \u05de\u05e0\u05d5\u05d9/\u05d4 \u05e4\u05e8\u05d9\u05de\u05d9\u05d5\u05dd!\n"
                "\u05db\u05dc \u05d4\u05e4\u05d9\u05e6'\u05e8\u05d9\u05dd \u05d6\u05de\u05d9\u05e0\u05d9\u05dd \u05e2\u05d1\u05d5\u05e8\u05da."
            )
            return

        features_text = "\n".join(f"\u2022 {f}" for f in self.pricing.features) if self.pricing.features else ""
        text = (
            f"\u2b50 {self.pricing.bot_name} Premium\n\n"
            f"{self.pricing.description_he}\n\n"
            f"{features_text}\n\n"
            f"\U0001f4b0 \u05de\u05d7\u05d9\u05e8: {self.pricing.price_ils} \u20aa"
            f"{f' / {self.pricing.price_ton} TON' if self.pricing.price_ton else ''}\n\n"
            f"{PAYMENT_INSTRUCTIONS}"
        )
        await message.answer(text)
        await db.create_payment(user_id, username or "", self.bot_key,
                                self.pricing.price_ils, "ILS")
        await db.log_event("payment.started", self.bot_key, user_id)

    async def _handle_photo_proof(self, message):
        """Handle payment proof screenshot upload."""
        user_id = message.from_user.id
        username = message.from_user.username or ""
        file_id = message.photo[-1].file_id

        submitted = await db.submit_proof(user_id, self.bot_key, file_id)
        if not submitted:
            # No pending payment - create one first
            await db.create_payment(user_id, username, self.bot_key,
                                    self.pricing.price_ils, "ILS")
            await db.submit_proof(user_id, self.bot_key, file_id)

        await message.answer(
            "\u2705 \u05d0\u05d9\u05e9\u05d5\u05e8 \u05d4\u05ea\u05e9\u05dc\u05d5\u05dd \u05d4\u05ea\u05e7\u05d1\u05dc!\n"
            "\u05de\u05de\u05ea\u05d9\u05df \u05dc\u05d0\u05d9\u05e9\u05d5\u05e8 \u05d0\u05d3\u05de\u05d9\u05df..."
        )

        # Notify admin
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        pool = await db.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM premium_users WHERE user_id=$1 AND bot_name=$2",
                user_id, self.bot_key,
            )
        pid = row["id"] if row else 0

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="\u2705 \u05d0\u05e9\u05e8", callback_data=f"pay_approve:{pid}"),
                InlineKeyboardButton(text="\u274c \u05d3\u05d7\u05d4", callback_data=f"pay_reject:{pid}"),
            ]
        ])
        admin_text = (
            f"\U0001f4b3 *\u05ea\u05e9\u05dc\u05d5\u05dd \u05d7\u05d3\u05e9!*\n\n"
            f"\u05d1\u05d5\u05d8: {self.pricing.bot_name}\n"
            f"\u05de\u05e9\u05ea\u05de\u05e9: @{username} ({user_id})\n"
            f"\u05e1\u05db\u05d5\u05dd: {self.pricing.price_ils} \u20aa\n"
            f"ID: {pid}"
        )
        try:
            await self.bot.send_photo(
                ADMIN_USER_ID, file_id, caption=admin_text,
                parse_mode="Markdown", reply_markup=kb,
            )
        except Exception as e:
            logger.error("Failed to notify admin: %s", e)

        await db.log_event("payment.submitted", self.bot_key, user_id)

    async def _handle_approve(self, cb):
        """Admin approves payment."""
        if cb.from_user.id != ADMIN_USER_ID:
            await cb.answer("\u274c \u05e8\u05e7 \u05d0\u05d3\u05de\u05d9\u05df", show_alert=True)
            return

        pid = int(cb.data.split(":")[1])
        result = await db.approve_payment(pid, cb.from_user.id)
        if not result:
            await cb.answer("\u05dc\u05d0 \u05e0\u05de\u05e6\u05d0")
            return

        user_id = result["user_id"]
        bot_name = result["bot_name"]

        # Send premium group link if configured
        if self.pricing.premium_group_link:
            try:
                await self.bot.send_message(
                    user_id,
                    f"\u2705 *\u05d4\u05ea\u05e9\u05dc\u05d5\u05dd \u05d0\u05d5\u05e9\u05e8!*\n\n"
                    f"\u05d4\u05e0\u05d4 \u05d4\u05e7\u05d9\u05e9\u05d5\u05e8 \u05dc\u05e7\u05d1\u05d5\u05e6\u05ea \u05d4\u05e4\u05e8\u05d9\u05de\u05d9\u05d5\u05dd:\n"
                    f"{self.pricing.premium_group_link}\n\n"
                    f"\u05d1\u05e8\u05d5\u05da \u05d4\u05d1\u05d0 \u05dc-{self.pricing.bot_name} Premium! \U0001f680",
                    parse_mode="Markdown",
                )
                await db.mark_group_invited(user_id, bot_name)
            except Exception as e:
                logger.error("Failed to send group link: %s", e)
        else:
            try:
                await self.bot.send_message(
                    user_id,
                    f"\u2705 *\u05d4\u05ea\u05e9\u05dc\u05d5\u05dd \u05d0\u05d5\u05e9\u05e8!*\n\n"
                    f"\u05db\u05dc \u05d4\u05e4\u05d9\u05e6'\u05e8\u05d9\u05dd \u05d4\u05e4\u05e8\u05d9\u05de\u05d9\u05d5\u05dd \u05e9\u05dc {self.pricing.bot_name} \u05d6\u05de\u05d9\u05e0\u05d9\u05dd \u05e2\u05d1\u05d5\u05e8\u05da! \U0001f680",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error("Failed to send approval: %s", e)

        await cb.message.edit_caption(
            caption=f"\u2705 \u05d0\u05d5\u05e9\u05e8 \u05e2\u05dc \u05d9\u05d3\u05d9 \u05d0\u05d3\u05de\u05d9\u05df | {bot_name} | user {user_id}"
        )
        await cb.answer("\u05d0\u05d5\u05e9\u05e8!")
        await db.log_event("payment.approved", bot_name, user_id)

    async def _handle_reject(self, cb):
        """Admin rejects payment."""
        if cb.from_user.id != ADMIN_USER_ID:
            await cb.answer("\u274c \u05e8\u05e7 \u05d0\u05d3\u05de\u05d9\u05df", show_alert=True)
            return

        pid = int(cb.data.split(":")[1])
        result = await db.reject_payment(pid, cb.from_user.id)
        if not result:
            await cb.answer("\u05dc\u05d0 \u05e0\u05de\u05e6\u05d0")
            return

        user_id = result["user_id"]
        try:
            await self.bot.send_message(
                user_id,
                "\u274c *\u05d4\u05ea\u05e9\u05dc\u05d5\u05dd \u05e0\u05d3\u05d7\u05d4.*\n\n"
                "\u05d0\u05e0\u05d0 \u05e0\u05e1\u05d4 \u05e9\u05d5\u05d1 \u05d0\u05d5 \u05e4\u05e0\u05d4 \u05dc\u05ea\u05de\u05d9\u05db\u05d4.",
                parse_mode="Markdown",
            )
        except Exception:
            pass

        await cb.message.edit_caption(caption=f"\u274c \u05e0\u05d3\u05d7\u05d4 | user {user_id}")
        await cb.answer("\u05e0\u05d3\u05d7\u05d4")
        await db.log_event("payment.rejected", result["bot_name"], user_id)

    # ---- Check premium status ----

    async def check_premium(self, user_id: int) -> bool:
        return await db.is_premium(user_id, self.bot_key)

    async def require_premium(self, message, feature_name: str = "") -> bool:
        """Returns True if user has premium. If not, shows upsell and returns False."""
        if await self.check_premium(message.from_user.id):
            return True
        label = feature_name or "\u05ea\u05d5\u05db\u05df \u05e4\u05e8\u05d9\u05de\u05d9\u05d5\u05dd"
        text = (
            f"\U0001f512 *{label}*\n\n"
            "\u05e4\u05d9\u05e6'\u05e8 \u05d6\u05d4 \u05d6\u05de\u05d9\u05df \u05e8\u05e7 \u05dc\u05de\u05e0\u05d5\u05d9\u05d9 \u05e4\u05e8\u05d9\u05de\u05d9\u05d5\u05dd.\n"
            "\u05dc\u05e9\u05d3\u05e8\u05d5\u05d2 \u2192 /premium"
        )
        await message.answer(text, parse_mode="Markdown")
        return False
