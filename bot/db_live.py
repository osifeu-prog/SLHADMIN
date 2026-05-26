# bot/db_live.py - שכבת DB אמיתית לבוט
import asyncpg
import os
from dotenv import load_dotenv
load_dotenv()

async def get_conn():
    return await asyncpg.connect(os.getenv("DATABASE_URL"))

async def ensure_user(telegram_id: int, username: str | None):
    conn = await get_conn()
    try:
        row = await conn.fetchrow("SELECT user_id FROM users WHERE user_id = $1", telegram_id)
        if not row:
            await conn.execute(
                "INSERT INTO users (user_id, username, first_seen) VALUES ($1, $2, NOW()::text) ON CONFLICT DO NOTHING",
                telegram_id, username or ""
            )
    finally:
        await conn.close()

async def get_referrer(telegram_id: int):
    conn = await get_conn()
    try:
        row = await conn.fetchrow("SELECT referrer_id FROM referrals WHERE user_id = $1 LIMIT 1", telegram_id)
        return row["referrer_id"] if row else None
    finally:
        await conn.close()

async def register_referral(user_id: int, referrer_id: int):
    if user_id == referrer_id:
        return False
    conn = await get_conn()
    try:
        existing = await conn.fetchrow("SELECT id FROM referrals WHERE user_id = $1", user_id)
        if existing:
            return False
        await conn.execute(
            "INSERT INTO referrals (user_id, referrer_id, depth, created_at) VALUES ($1, $2, 1, NOW())",
            user_id, referrer_id
        )
        return True
    finally:
        await conn.close()

async def get_token_balance(user_id: int, token: str = "SLH"):
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT balance FROM token_balances WHERE user_id = $1 AND token = $2",
            user_id, token
        )
        return float(row["balance"]) if row else 0.0
    finally:
        await conn.close()

async def get_royalties(user_id: int):
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT COALESCE(SUM(amount), 0) as total FROM royalties WHERE user_id = $1",
            user_id
        )
        return float(row["total"]) if row else 0.0
    finally:
        await conn.close()

async def get_referral_count(user_id: int):
    conn = await get_conn()
    try:
        count = await conn.fetchval("SELECT COUNT(*) FROM referrals WHERE referrer_id = $1", user_id)
        return int(count or 0)
    finally:
        await conn.close()

async def get_referral_earnings(user_id: int):
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT COALESCE(SUM(commission_amount), 0) as total FROM referral_earnings WHERE earner_id = $1",
            user_id
        )
        return float(row["total"]) if row else 0.0
    finally:
        await conn.close()

async def get_leaderboard(limit: int = 10):
    conn = await get_conn()
    try:
        rows = await conn.fetch("""
            SELECT u.username, u.user_id, COALESCE(tb.balance, 0) as balance
            FROM users u
            LEFT JOIN token_balances tb ON tb.user_id = u.user_id AND tb.token = 'SLH'
            ORDER BY balance DESC
            LIMIT $1
        """, limit)
        return rows
    finally:
        await conn.close()

async def get_stats():
    conn = await get_conn()
    try:
        users = await conn.fetchval("SELECT COUNT(*) FROM users")
        referrals = await conn.fetchval("SELECT COUNT(*) FROM referrals")
        return {"users": int(users or 0), "referrals": int(referrals or 0)}
    finally:
        await conn.close()
