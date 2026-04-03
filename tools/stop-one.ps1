$ErrorActionPreference="Stop"
Set-Location "D:\telegram-guardian-DOCKER-COMPOSE-ENTERPRISE"
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
docker compose down
"Stopped cloudflared + docker compose."