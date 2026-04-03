param()
$ErrorActionPreference="Stop"
Write-Host "Stopping cloudflared..."
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "Stopping docker compose..."
docker compose down
Write-Host "OK"
