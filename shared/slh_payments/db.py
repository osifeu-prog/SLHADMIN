"""Shared payment database operations - works with any bot's Postgres."""
import os
import asyncpg
from typing import Optional

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            os.getenv("DATABASE_URL", "postgresql://postgres:slh_secure_2026@postgres:5432/slh_main"),
            min_size=1,
            max_size=5,
        )
    return _pool


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS premium_users (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username TEXT,
    bot_name TEXT NOT NULL,
    payment_status TEXT DEFAULT 'pending',
    payment_proof_file_id TEXT,
    payment_amount NUMERIC(18,2),
    payment_currency TEXT DEFAULT 'ILS',
    payment_method TEXT DEFAULT 'bank',
    approved_by BIGINT,
    approved_at TIMESTAMP,
    premium_group_invited BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, bot_name)
);

CREATE TABLE IF NOT EXISTS system_events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    bot_name TEXT,
    user_id BIGINT,
    payload TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_premium_users_status ON premium_users(payment_status);
CREATE INDEX IF NOT EXISTS idx_premium_users_bot ON premium_users(bot_name);
CREATE INDEX IF NOT EXISTS idx_system_events_type ON system_events(event_type, created_at DESC);
"""


async def init_schema():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)


async def is_premium(user_id: int, bot_name: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT payment_status FROM premium_users WHERE user_id=$1 AND bot_name=$2",
            user_id, bot_name,
        )
    return row is not None and row["payment_status"] == "approved"


async def create_payment(user_id: int, username: str, bot_name: str,
                         amount: float, currency: str = "ILS") -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO premium_users (user_id, username, bot_name, payment_amount, payment_currency)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (user_id, bot_name) DO UPDATE
               SET payment_status='pending', payment_amount=$4, payment_currency=$5
               RETURNING id""",
            user_id, username, bot_name, amount, currency,
        )
    return row["id"]


async def submit_proof(user_id: int, bot_name: str, file_id: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE premium_users
               SET payment_proof_file_id=$3, payment_status='submitted'
               WHERE user_id=$1 AND bot_name=$2""",
            user_id, bot_name, file_id,
        )
    return "UPDATE 1" in result


async def approve_payment(payment_id: int, admin_id: int) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE premium_users
               SET payment_status='approved', approved_by=$2, approved_at=CURRENT_TIMESTAMP
               WHERE id=$1
               RETURNING user_id, bot_name, username""",
            payment_id, admin_id,
        )
    return dict(row) if row else None


async def reject_payment(payment_id: int, admin_id: int) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE premium_users
               SET payment_status='rejected', approved_by=$2, approved_at=CURRENT_TIMESTAMP
               WHERE id=$1
               RETURNING user_id, bot_name, username""",
            payment_id, admin_id,
        )
    return dict(row) if row else None


async def mark_group_invited(user_id: int, bot_name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE premium_users SET premium_group_invited=TRUE WHERE user_id=$1 AND bot_name=$2",
            user_id, bot_name,
        )


async def get_pending_payments() -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, user_id, username, bot_name, payment_amount, payment_currency,
                      payment_proof_file_id, created_at
               FROM premium_users
               WHERE payment_status='submitted'
               ORDER BY created_at""",
        )
    return [dict(r) for r in rows]


async def get_stats() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM premium_users")
        approved = await conn.fetchval("SELECT COUNT(*) FROM premium_users WHERE payment_status='approved'")
        pending = await conn.fetchval("SELECT COUNT(*) FROM premium_users WHERE payment_status='submitted'")
        revenue = await conn.fetchval(
            "SELECT COALESCE(SUM(payment_amount), 0) FROM premium_users WHERE payment_status='approved'"
        )
        by_bot = await conn.fetch(
            """SELECT bot_name, COUNT(*) as cnt,
                      COALESCE(SUM(CASE WHEN payment_status='approved' THEN payment_amount ELSE 0 END), 0) as revenue
               FROM premium_users GROUP BY bot_name ORDER BY revenue DESC"""
        )
    return {
        "total_users": total,
        "approved": approved,
        "pending": pending,
        "total_revenue": float(revenue),
        "by_bot": [dict(r) for r in by_bot],
    }


async def log_event(event_type: str, bot_name: str, user_id: int = 0, payload: str = ""):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO system_events (event_type, bot_name, user_id, payload) VALUES ($1,$2,$3,$4)",
            event_type, bot_name, user_id, payload,
        )
