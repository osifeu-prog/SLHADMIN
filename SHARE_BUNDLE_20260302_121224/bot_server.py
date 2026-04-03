import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, Header
from fastapi.responses import JSONResponse

from telegram import Update

from bot.app_factory import build_application
from bot.infrastructure import init_infrastructure, run_migrations_safe, runtime_report

APP_START = time.time()
ptb_app = None


def uptime_s() -> int:
    return int(time.time() - APP_START)


def git_sha() -> str:
    return (
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("GIT_COMMIT_SHA")
        or os.getenv("COMMIT_SHA")
        or ""
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Infra (do not crash app)
    try:
        await init_infrastructure(wait=True)
    except Exception as e:
        logging.getLogger(__name__).error(
            "infra init failed (startup continues): %s: %s", type(e).__name__, e
        )

    # Migrations (safe)
    try:
        await run_migrations_safe()
    except Exception as e:
        logging.getLogger(__name__).error(
            "migrations failed (startup continues): %s: %s", type(e).__name__, e
        )

    # Telegram PTB embedded
    global ptb_app
    if ptb_app is None:
        if os.getenv("TELEGRAM_TOKEN"):
            ptb_app = build_application()
            logging.getLogger(__name__).info("PTB application initialized")
        else:
            logging.getLogger(__name__).warning("TELEGRAM_TOKEN missing; PTB disabled")

    if ptb_app is not None:
        await ptb_app.initialize()
        await ptb_app.start()

    yield

    if ptb_app is not None:
        await ptb_app.stop()
        await ptb_app.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"ok": True, "service": "guardian", "uptime_s": uptime_s()}


@app.get("/healthz")
async def healthz():
    return {
        "ok": True,
        "uptime_s": uptime_s(),
        "git_sha": (git_sha()[:12] if git_sha() else None),
    }

@app.get("/health")
async def health():
    # alias for legacy clients
    return await healthz()


@app.get("/readyz")
async def readyz():
    t0 = time.perf_counter()
    try:
        _ = await runtime_report(full=False)
        return {"ok": True, "elapsed_ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as e:
        return JSONResponse(
            {
                "ok": False,
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "error": f"{type(e).__name__}: {e}",
            },
            status_code=503,
        )


@app.get("/version")
async def version():
    return {"service": "guardian", "git_sha": git_sha(), "uptime_s": uptime_s()}


@app.post("/tg/webhook")
async def tg_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    # Secret guard (optional)
    secret = os.getenv("WEBHOOK_SECRET")
    if secret:
        if (x_telegram_bot_api_secret_token or "") != secret:
            return JSONResponse({"ok": False, "error": "BAD_SECRET"}, status_code=403)

    if ptb_app is None:
        return JSONResponse({"ok": False, "error": "PTB_DISABLED"}, status_code=503)

    payload = await request.json()
    update = Update.de_json(payload, ptb_app.bot)
    await ptb_app.process_update(update)
    return {"ok": True}


# Optional Prometheus metrics (best-effort)
try:
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

except Exception:
    pass
