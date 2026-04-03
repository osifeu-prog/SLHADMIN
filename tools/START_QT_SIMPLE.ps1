param()

$ErrorActionPreference="Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$ROOT = Split-Path -Parent $ROOT

function Log($m){ Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }
function Wait-DnsReady([string]$dnsHost,[int]$timeoutSec=180){
  $t0 = Get-Date
  while(((Get-Date)-$t0).TotalSeconds -lt $timeoutSec){
    $ok1=$false;$ok2=$false
    try { $ok1 = [bool](Resolve-DnsName -Name $dnsHost -Server 1.1.1.1 -ErrorAction Stop | Where-Object {$_.IPAddress}) } catch {}
    try { $ok2 = [bool](Resolve-DnsName -Name $dnsHost -Server 8.8.8.8 -ErrorAction Stop | Where-Object {$_.IPAddress}) } catch {}
    if($ok1 -or $ok2){ return $true }
    Start-Sleep -Seconds 2
  }
  return $false
}
function Upsert-EnvVar([string]$envPath,[string]$key,[string]$value){
  $txt = Get-Content $envPath -Raw -Encoding utf8
  if($txt -match ("(?m)^\s*" + [regex]::Escape($key) + "\s*=")){
    $txt = [regex]::Replace($txt, ("(?m)^\s*" + [regex]::Escape($key) + "\s*=.*$"), ($key + "=" + $value))
  } else {
    if($txt.Length -gt 0 -and -not $txt.EndsWith("`n")){ $txt += "`n" }
    $txt += ($key + "=" + $value + "`n")
  }
  Set-Content -Path $envPath -Value $txt -Encoding utf8
}

Set-Location $ROOT
Log "Docker compose up"
docker compose up -d

# read token from .env
$envPath = Join-Path $ROOT ".env"
$raw = Get-Content $envPath -Raw -Encoding utf8
$m = [regex]::Match($raw, '(?m)^\s*(?:BOT_TOKEN|TELEGRAM_TOKEN)\s*=\s*(.+?)\s*$')
if(-not $m.Success){ throw "BOT_TOKEN/TELEGRAM_TOKEN missing in .env" }
$tok = $m.Groups[1].Value.Trim()
$tok = $tok -replace '^[\x22\x27]+|[\x22\x27]+$',''

$base = Read-Host "Paste https://xxxxx.trycloudflare.com from tunnel window"
$dnsHost = ([uri]$base).Host
Log "Wait DNS for $dnsHost"
if(-not (Wait-DnsReady $dnsHost 180)){ throw "DNS not ready for $dnsHost" }

Log "Update .env WEBHOOK_URL"
Upsert-EnvVar $envPath "WEBHOOK_URL" $base

Log "Set webhook"
$hook = $base + "/tg/webhook"
$encHook = [System.Uri]::EscapeDataString($hook)
$r1 = curl.exe -sS ("https://api.telegram.org/bot" + $tok + "/setWebhook?url=" + $encHook)
Log ("setWebhook: " + $r1)
$r2 = curl.exe -sS ("https://api.telegram.org/bot" + $tok + "/getWebhookInfo")
Log ("getWebhookInfo: " + $r2)

Log "DONE"
Log "Try in Telegram: /start /status /points"

