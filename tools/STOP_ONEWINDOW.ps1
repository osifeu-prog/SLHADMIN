param()
$ErrorActionPreference="Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$ROOT = Split-Path -Parent $ROOT
Set-Location $ROOT
Write-Host "=== STOP: docker compose down ==="
docker compose down | Out-Host
Write-Host "=== STOP: kill cloudflared ==="
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "OK: stopped"