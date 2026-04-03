# Guardian Ops Roadmap

## Current (Telegram Ops)
- /health /vars /webhook /diag /pingdb /pingredis
- Command logging into Railway logs

## Next (HTTP Ops API)
Move webhook hosting to FastAPI:
- POST /tg/webhook  (Telegram)
- GET /healthz
- GET /readyz
- GET /version

Keep bot logic identical; only transport changes.
