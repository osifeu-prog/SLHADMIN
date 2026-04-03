import asyncio
import logging
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application

from bot.infrastructure import init_infrastructure
from bot.app_factory import build_application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook_ingress")

app = FastAPI()
_tg_app: Optional[Application] = None


@app.on_event("startup")
async def _startup() -> None:
    await init_infrastructure(wait=False)

    global _tg_app
    _tg_app = build_application()

    await _tg_app.initialize()
    await _tg_app.start()
    logger.info("PTB application started")


@app.on_event("shutdown")
async def _shutdown() -> None:
    global _tg_app
    if _tg_app is None:
        return
    try:
        await _tg_app.stop()
        await _tg_app.shutdown()
    finally:
        _tg_app = None
    logger.info("PTB application stopped")


@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {"ok": True}


@app.get("/readyz")
async def readyz() -> Dict[str, Any]:
    return {"ok": True}


@app.post("/tg/webhook")
async def tg_webhook(req: Request):
    """
    Always returns 200 OK to Telegram.
    Update processing happens async, exceptions are logged.
    """
    global _tg_app

    try:
        payload = await req.json()
    except Exception:
        logger.exception("invalid JSON")
        return {"ok": True}

    if _tg_app is None:
        logger.error("app not ready yet")
        return {"ok": True}

    try:
        upd = Update.de_json(payload, _tg_app.bot)

        async def _run_update():
            try:
                await _tg_app.process_update(upd)
            except Exception:
                logger.exception("process_update failed")

        asyncio.create_task(_run_update())
    except Exception:
        logger.exception("failed to enqueue update")

    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("bot.webhook_ingress:app", host=host, port=port, log_level="info")
