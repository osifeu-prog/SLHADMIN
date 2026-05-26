import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine

async def run():
    url = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(__import__("sqlalchemy").text(
            """CREATE TABLE IF NOT EXISTS tickets (
                id SERIAL PRIMARY KEY,
                ticket_id VARCHAR(8) UNIQUE NOT NULL,
                user_id BIGINT NOT NULL,
                username VARCHAR(64),
                description TEXT NOT NULL,
                status VARCHAR(16) DEFAULT 'open',
                created_at TIMESTAMP DEFAULT NOW()
            )"""
        ))
    print("tickets table OK")
    await engine.dispose()

asyncio.run(run())
