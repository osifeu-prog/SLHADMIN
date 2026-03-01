param(
  [string]$WorkerWebhookUrl = "https://tg-webhook-worker.osif.workers.dev/tg/webhook",
  [string]$VaultDirName = ".vault_guardian",
  [string]$SecretFileName = "tg_webhook_secret.token",
  [int]$SecretLen = 48
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-Secret {
  param([int]$Len)
  $alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
  $bytes = New-Object byte[] 256
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $chars = New-Object char[] $Len
  for ($i=0; $i -lt $Len; $i++) { $chars[$i] = $alphabet[ $bytes[$i] % $alphabet.Length ] }
  -join $chars
}

function Assert-BotToken {
  param([string]$Token)
  if ($Token -notmatch '^\d{6,}:[A-Za-z0-9_-]{20,}$') { throw "BOT_TOKEN invalid format. Do NOT paste secret here." }
}

$root = Get-Location
$vaultDir = Join-Path $root $VaultDirName
New-Item -ItemType Directory -Force -Path $vaultDir | Out-Null
$secretPath = Join-Path $vaultDir $SecretFileName

# rotate secret
$secret = New-Secret -Len $SecretLen
if ($secret.Length -ne $SecretLen) { throw ("Secret length must be {0} (got {1})" -f $SecretLen, $secret.Length) }
[System.IO.File]::WriteAllText($secretPath, $secret, [System.Text.Encoding]::ASCII)

# ACL harden
icacls $secretPath /inheritance:r | Out-Null
icacls $secretPath /grant:r ("{0}:F" -f $env:USERNAME) | Out-Null

# upload to Cloudflare Worker secret
$null = $secret | wrangler secret put TG_SECRET_TOKEN

# apply to Telegram webhook
$BOT_TOKEN = Read-Host "Paste TELEGRAM BOT TOKEN (digits:AA...)"
Assert-BotToken -Token $BOT_TOKEN
$api = "https://api.telegram.org/bot$BOT_TOKEN"

curl.exe -sS "$api/deleteWebhook?drop_pending_updates=true" | Out-Null
curl.exe -sS -X POST "$api/setWebhook" -d ("url={0}" -f $WorkerWebhookUrl) -d ("secret_token={0}" -f $secret) -d "max_connections=40" | Out-Null
curl.exe -sS "$api/getWebhookInfo"
