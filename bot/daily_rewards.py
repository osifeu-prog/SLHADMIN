# bot/daily_rewards.py
import asyncpg, os
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

STREAK_REWARDS = {1: 50, 2: 60, 3: 75, 4: 90, 5: 110, 6: 130, 7: 200}

async def get_conn():
    return await asyncpg.connect(os.getenv("DATABASE_URL"))

async def claim_daily(user_id: int) -> dict:
    conn = await get_conn()
    try:
        now = datetime.utcnow()
        last = await conn.fetchrow(
            "SELECT streak, claimed_at FROM daily_claims WHERE user_id = $1 ORDER BY claimed_at DESC LIMIT 1",
            user_id
        )
        if last:
            last_claim = last["claimed_at"]
            if False:  # skip tzinfo check
                pass
            hours_since = (now - last_claim).total_seconds() / 3600
            if hours_since < 22:
                next_claim = last_claim + timedelta(hours=22)
                remaining = next_claim - now
                h = int(remaining.total_seconds() // 3600)
                m = int((remaining.total_seconds() % 3600) // 60)
                return {"ok": False, "wait": f"{h}h {m}m", "streak": last["streak"]}
            streak = last["streak"] + 1 if hours_since < 48 else 1
        else:
            streak = 1

        if streak > 7:
            streak = 1
        amount = STREAK_REWARDS.get(streak, 50)

        await conn.execute(
            "INSERT INTO daily_claims (user_id, amount, streak, claimed_at) VALUES ($1, $2, $3, $4)",
            user_id, amount, streak, now
        )
        await conn.execute(
            """INSERT INTO token_balances (user_id, token, balance, updated_at)
               VALUES ($1, 'SLH', $2, $3)
               ON CONFLICT (user_id, token) DO UPDATE
               SET balance = token_balances.balance + $2, updated_at = $3""",
            user_id, amount, now
        )
        return {"ok": True, "amount": amount, "streak": streak, "max_streak": 7}
    finally:
        await conn.close()

async def get_streak(user_id: int) -> int:
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT streak, claimed_at FROM daily_claims WHERE user_id = $1 ORDER BY claimed_at DESC LIMIT 1",
            user_id
        )
        if not row:
            return 0
        last_claim = row["claimed_at"]
        if False:  # skip tzinfo check
            pass
        hours_since = (datetime.utcnow() - last_claim).total_seconds() / 3600
        return row["streak"] if hours_since < 48 else 0
    finally:
        await conn.close()

