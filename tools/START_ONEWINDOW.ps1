param([switch]$TailLogs = $true)

$ErrorActionPreference="Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$ROOT = Split-Path -Parent $ROOT
Set-Location $ROOT

function Read-EnvValue([string]$key){
  $envPath = Join-Path $ROOT ".env"
  if(-not (Test-Path $envPath)){ throw "Missing .env at $envPath" }
  $txt = Get-Content $envPath -Raw
  $m = [regex]::Match($txt, "(?m)^\s*$key\s*=\s*(?<v>.+?)\s*$")
  if($m.Success){ return $m.Groups["v"].Value.Trim() }
  return $null
}

function Wait-HttpOk([string]$url, [int]$seconds=90){
  for($i=0;$i -lt $seconds;$i++){
    try{
      $r = curl.exe -sS $url
      if($r -match '"ok"\s*:\s*true'){ return $true }
    } catch {}
    Start-Sleep -Seconds 1
  }
  return $false
}

Write-Host "=== 0) cleanup leftovers ==="
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "=== 1) docker compose up ==="
docker compose up -d --build | Out-Host

Write-Host "=== 2) wait local ready ==="
if(-not (Wait-HttpOk "http://127.0.0.1:8001/readyz" 90)){
  throw "Local /readyz not OK after 90s"
}
Write-Host "Local /readyz OK"

Write-Host "=== 3) local healthz2 ==="
curl.exe -sS http://127.0.0.1:8001/healthz2 | Out-Host

Write-Host "=== 4) start cloudflared (http2) background ==="
$logDir = Join-Path $ROOT ".runbook"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "cloudflared_onewindow.log"
Remove-Item -Force $log -ErrorAction SilentlyContinue

Start-Process -FilePath "cloudflared" -ArgumentList @(
  "tunnel","--protocol","http2","--url","http://127.0.0.1:8001",
  "--loglevel","info","--logfile",$log
) | Out-Null

Write-Host "=== 5) extract tunnel URL ==="
$base=$null
for($i=0;$i -lt 180;$i++){
  if(Test-Path $log){
    $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -AllMatches -ErrorAction SilentlyContinue | Select-Object -Last 1
    if($m){ $base = $m.Matches[0].Value; break }
  }
  Start-Sleep -Seconds 1
}
if(-not $base){ throw "No tunnel URL found in $log" }
Write-Host "Tunnel BASE: $base"

Write-Host "=== 6) set telegram webhook ==="
$token = Read-EnvValue "BOT_TOKEN"
if(-not $token){ $token = Read-EnvValue "TELEGRAM_TOKEN" }
if(-not $token){ throw "BOT_TOKEN/TELEGRAM_TOKEN missing in .env" }

$hook = "$base/tg/webhook"
curl.exe -sS "https://api.telegram.org/bot$token/setWebhook?url=$hook&drop_pending_updates=true" | Out-Host
curl.exe -sS "https://api.telegram.org/bot$token/getWebhookInfo" | Out-Host

Write-Host "=== 7) done ==="
Write-Host "Send /start in Telegram now."

if($TailLogs){
  docker compose logs -f guardian-api
}