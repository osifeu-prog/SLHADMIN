"""Payment configuration shared across all SLH bots."""
import os
import json
from dataclasses import dataclass, field
from typing import Optional

ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "224223270"))

TON_WALLET = "UQCr743gEr_nqV_0SBkSp3CtYS_15R3LDLBvLmKeEv7XdGvp"

# Payment instructions - TON only
PAYMENT_INSTRUCTIONS = (
    "\u05e9\u05dc\u05d7 \u05ea\u05e9\u05dc\u05d5\u05dd \u05d1-TON \u05dc\u05db\u05ea\u05d5\u05d1\u05ea:\n"
    f"`{TON_WALLET}`\n\n"
    "\u05dc\u05d0\u05d7\u05e8 \u05d4\u05ea\u05e9\u05dc\u05d5\u05dd, \u05e9\u05dc\u05d7 \u05db\u05d0\u05df \u05e6\u05d9\u05dc\u05d5\u05dd \u05de\u05e1\u05da \u05e9\u05dc \u05d0\u05d9\u05e9\u05d5\u05e8 \u05d4\u05e2\u05d1\u05e8\u05d4.\n"
    "\u05d0\u05e9\u05dc\u05d7 \u05dc\u05da \u05d0\u05d9\u05e9\u05d5\u05e8/\u05d3\u05d7\u05d9\u05d9\u05d4 \u05d1\u05d4\u05ea\u05d0\u05dd."
)


@dataclass
class BotPricing:
    """Pricing configuration for a single bot."""
    bot_name: str
    price_ils: float
    price_ton: float = 0.0
    description_he: str = ""
    premium_group_chat_id: Optional[int] = None
    premium_group_link: Optional[str] = None
    features: list = field(default_factory=list)


# Per-bot pricing with group links
BOT_PRICING = {
    "botshop": BotPricing(
        bot_name="GATE BotShop",
        price_ils=99, price_ton=5.0,
        description_he="\u05de\u05e1\u05d7\u05e8 AI + \u05e0\u05d9\u05ea\u05d5\u05d7\u05d9 \u05e9\u05d5\u05e7 + \u05e1\u05d9\u05de\u05d5\u05dc\u05e6\u05d9\u05d4",
        premium_group_link="https://t.me/+Hl1TEpkVLws2MTQ8",
        features=["\u05e0\u05d9\u05ea\u05d5\u05d7\u05d9 \u05e9\u05d5\u05e7 \u05d7\u05db\u05de\u05d9\u05dd", "\u05e1\u05d9\u05de\u05d5\u05dc\u05e6\u05d9\u05d9\u05ea \u05de\u05e1\u05d7\u05e8", "\u05e7\u05d1\u05d5\u05e6\u05ea VIP"],
    ),
    "wallet": BotPricing(
        bot_name="SLH Wallet",
        price_ils=79, price_ton=4.0,
        description_he="\u05e0\u05d9\u05d4\u05d5\u05dc \u05d0\u05e8\u05e0\u05e7 TON/BNB",
        premium_group_link="https://t.me/+trsYaT1UVI8yY2Y0",
        features=["\u05d0\u05e8\u05e0\u05e7 TON/BNB", "\u05d4\u05e2\u05d1\u05e8\u05d5\u05ea", "\u05de\u05e2\u05e7\u05d1 \u05d9\u05ea\u05e8\u05d5\u05ea"],
    ),
    "factory": BotPricing(
        bot_name="BOT Factory",
        price_ils=149, price_ton=7.5,
        description_he="\u05d4\u05e9\u05e7\u05e2\u05d5\u05ea + \u05e1\u05d8\u05d9\u05d9\u05e7\u05d9\u05e0\u05d2",
        premium_group_link="https://t.me/+yWzrEaA41rRhNjVk",
        features=["\u05d4\u05e9\u05e7\u05e2\u05d5\u05ea \u05d7\u05db\u05de\u05d5\u05ea", "\u05e1\u05d8\u05d9\u05d9\u05e7\u05d9\u05e0\u05d2 \u05d0\u05de\u05d9\u05ea\u05d9", "\u05e4\u05d0\u05e0\u05dc \u05d0\u05d3\u05de\u05d9\u05df"],
    ),
    "academia": BotPricing(
        bot_name="SLH Academia",
        price_ils=41, price_ton=2.0,
        description_he="\u05d7\u05d9\u05e0\u05d5\u05da + Airdrop + XP",
        premium_group_link="https://t.me/+JSGStjREEs43MzZk",
        features=["Airdrop \u05d9\u05d5\u05de\u05d9", "\u05de\u05e9\u05d9\u05de\u05d5\u05ea XP", "\u05dc\u05d5\u05d7 \u05de\u05d5\u05d1\u05d9\u05dc\u05d9\u05dd"],
    ),
    "guardian": BotPricing(
        bot_name="SLH Guardian",
        price_ils=59, price_ton=3.0,
        description_he="\u05d0\u05d1\u05d8\u05d7\u05d4 + \u05e0\u05d9\u05d8\u05d5\u05e8 \u05de\u05e2\u05e8\u05db\u05ea",
        premium_group_link="https://t.me/+_l9XZ77Bbb5kZTM0",
        features=["\u05e0\u05d9\u05d8\u05d5\u05e8 DB/Redis", "\u05d3\u05d5\u05d7\u05d5\u05ea \u05d0\u05d3\u05de\u05d9\u05df", "\u05d4\u05ea\u05e8\u05d0\u05d5\u05ea \u05d0\u05de\u05ea"],
    ),
    "community": BotPricing(
        bot_name="SLH Community",
        price_ils=41, price_ton=2.0,
        description_he="\u05e7\u05d4\u05d9\u05dc\u05d4 + \u05e4\u05e8\u05d5\u05de\u05d5",
        premium_group_link="https://t.me/+e8GeOmh0CD82ZmI0",
        features=["\u05e7\u05d4\u05d9\u05dc\u05ea \u05e4\u05e8\u05d9\u05de\u05d9\u05d5\u05dd", "\u05e2\u05d3\u05db\u05d5\u05e0\u05d9\u05dd \u05d1\u05dc\u05e2\u05d3\u05d9\u05d9\u05dd", "\u05ea\u05d5\u05db\u05df VIP"],
    ),
}

# System bus group
SYSTEM_BUS_LINK = "https://t.me/+qon4jktYobA3Mjlk"
