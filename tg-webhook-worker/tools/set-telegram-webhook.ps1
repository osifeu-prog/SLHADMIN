param(
  [Parameter(Mandatory=$false)][string]$WorkerWebhookUrl = "https://tg-webhook-worker.osif.workers.dev/tg/webhook",
  [Parameter(Mandatory=$false)][string]$VaultDir = ".vault",
  [Parameter(Mandatory=$false)][string]$SecretFileName = "tg_secret_token.secret"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Read-SecretFile {
  param([string]$Path)
  if (-not (Test-Path $Path)) { throw "Secret file not found: $Path" }
  $s = Get-Content -Raw -Encoding ascii $Path
  if ($s -match '[^a-z0-9]') { throw "Secret contains invalid characters (only a-z0-9 allowed)." }
  if ($s.Length -lt 32) { throw "Secret too short. Use 32+ chars." }
  return $s
}

function Assert-LooksLikeBotToken {
  param([string]$Token)
  if ($Token -notmatch '^\d{6,}:[A-Za-z0-9_-]{20,}$') {
    throw "BOT_TOKEN does not look like a Telegram bot token. Do NOT paste the secret here."
  }
}

$root = Get-Location
$secretPath = Join-Path (Join-Path $root $VaultDir) $SecretFileName
$secret = Read-SecretFile -Path $secretPath

$BOT_TOKEN = Read-Host "Paste TELEGRAM BOT TOKEN (digits:AA...)"
Assert-LooksLikeBotToken -Token $BOT_TOKEN

$api = "https://api.telegram.org/bot$BOT_TOKEN"

curl.exe -sS "$api/deleteWebhook?drop_pending_updates=true" | Out-Null
$resp = curl.exe -sS -X POST "$api/setWebhook" -d ("url={0}" -f $WorkerWebhookUrl) -d ("secret_token={0}" -f $secret) -d "max_connections=40"
$info = curl.exe -sS "$api/getWebhookInfo"

Write-Host "setWebhook response:" -ForegroundColor Cyan
Write-Host $resp
Write-Host "getWebhookInfo:" -ForegroundColor Cyan
Write-Host $info
