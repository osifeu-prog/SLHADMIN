import os
import logging
import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
import redis.asyncio as redis
from alembic import command
from alembic.config import Config

logger = logging.getLogger("guardian_infra")

engine = None
SessionLocal: Optional[async_sessionmaker] = None
redis_client = None


def _to_asyncpg_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def _retry(name: str, fn, attempts: int, delay_s: float):
    last = None
    for i in range(1, attempts + 1):
        try:
            await fn()
            logger.info("%s: OK (attempt %d/%d)", name, i, attempts)
            return
        except Exception as e:
            last = e
            logger.warning("%s: not ready (attempt %d/%d): %s: %s", name, i, attempts, type(e).__name__, e)
            await asyncio.sleep(delay_s)
    raise RuntimeError(f"{name} not ready after {attempts} attempts: {type(last).__name__}: {last}")


async def init_infrastructure(wait: bool = True):
    global engine, SessionLocal, redis_client
    db_url = (os.getenv("ASYNC_DATABASE_URL") or "").strip() or (os.getenv("DATABASE_URL") or "").strip()
    redis_url = os.getenv("REDIS_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL missing")
    if not redis_url:
        redis_url = (os.getenv("REDIS_URL") or "").strip()
    if not redis_url:
        # Redis is optional for local/dev; DB must still work
        redis_client = None
    else:
        redis_client = redis.from_url(redis_url, decode_responses=True)

    engine = create_async_engine(_to_asyncpg_url(db_url), echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    # Redis optional (local/dev): only accept valid schemes
    redis_client = None
    if redis_url:
        redis_url = redis_url.strip()
        if redis_url.startswith(("redis://", "rediss://", "unix://")):
            try:
                redis_client = redis.from_url(redis_url)
            except Exception:
                redis_client = None
    if wait:
        await _retry(
            "Postgres",
            check_postgres,
            attempts=int(os.getenv("DB_WAIT_ATTEMPTS", "40")),
            delay_s=float(os.getenv("DB_WAIT_DELAY_S", "1")),
        )
        if redis_client is not None:
            await _retry(
                "Redis",
                check_redis,
                attempts=int(os.getenv("REDIS_WAIT_ATTEMPTS", "40")),
                delay_s=float(os.getenv("REDIS_WAIT_DELAY_S", "1")),
            )

    logger.info("Infrastructure initialized (wait=%s)", wait)


async def check_postgres():
    if engine is None:
        raise RuntimeError("Postgres not initialized")
    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT 1"))
        if r.scalar() != 1:
            raise RuntimeError("Postgres healthcheck failed")


async def check_redis():
    if redis_client is None:
        raise RuntimeError("Redis not initialized")
    ok = await redis_client.ping()
    if not ok:
        raise RuntimeError("Redis ping failed")


async def runtime_report(full: bool = False) -> str:
    lines = []
    lines.append("SLH Guardian — Runtime Report")
    lines.append(f"ENV: {os.getenv('ENV', 'production')}")
    lines.append(f"MODE: {os.getenv('MODE', 'webhook')}")
    lines.append("")
    lines.append(f"Postgres: {'OK' if engine else 'NOT INIT'}")
    lines.append(f"Redis: {'OK' if redis_client else 'NOT INIT'}")

    if full:
        lines.append("")
        for k in ("TELEGRAM_TOKEN", "DATABASE_URL", "REDIS_URL", "ADMIN_CHAT_ID", "WEBHOOK_URL"):
            lines.append(f"{k}: {'SET' if os.getenv(k) else 'MISSING'}")

    return "\n".join(lines)


async def get_db_session():
    if SessionLocal is None:
        raise RuntimeError("DB session factory not initialized")
    async with SessionLocal() as session:
        yield session


async def run_migrations_safe():
    db_url = (os.getenv("ASYNC_DATABASE_URL") or "").strip() or (os.getenv("DATABASE_URL") or "").strip()
    if not db_url:
        logger.warning("DATABASE_URL missing, skipping migrations")
        return
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        logger.info("Alembic migrations applied")
    except Exception as e:
        logger.error("Migration failed: %s: %s", type(e).__name__, e)
