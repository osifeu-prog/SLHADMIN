# RESTORE_CHECKLIST (Telegram Guardian local)

## Restore steps
1) Extract ZIP to a fresh folder (e.g. D:\tg_guardian_restore)
2) Copy .env.template -> .env and fill:
   - TELEGRAM_TOKEN
   - WEBHOOK_SECRET (recommended)
3) Start stack:
   - docker compose up -d --build
4) Run automation:
   - .\RUN_ALL.cmd
5) Test in Telegram (@Grdian_bot):
   - /start
   - /health
   - /status

## Stop cloudflared
- .\tools\stop-cloudflared.ps1
