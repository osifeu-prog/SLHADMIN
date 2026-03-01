param(
  [ValidateSet("rotate-all","rotate-bot","rotate-webhook","status")]
  [string]$Action = "status"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-Secret48 {
  $alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
  $bytes = New-Object byte[] 256
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $chars = New-Object char[] 48
  for ($i=0; $i -lt 48; $i++) {
    $chars[$i] = $alphabet[ $bytes[$i] % $alphabet.Length ]
  }
  -join $chars
}

function Rotate-Bot {
  $BOT = Read-Host "Paste NEW Telegram BOT_TOKEN"
  if ($BOT -notmatch '^\d{6,}:[A-Za-z0-9_-]{20,}$') {
    throw "Invalid BOT_TOKEN format"
  }
  $BOT | wrangler secret put BOT_TOKEN
  Write-Host "BOT_TOKEN updated"
}

function Rotate-Webhook {
  $secret = New-Secret48
  $secret | wrangler secret put TG_SECRET_TOKEN
  Write-Host "TG_SECRET_TOKEN rotated"
}

function Sync-Webhook {
  $BOT = Read-Host "Paste Telegram BOT_TOKEN"
  $secret = Read-Host "Paste CURRENT TG_SECRET_TOKEN"
  $api = "https://api.telegram.org/bot$BOT"

  curl.exe -sS "$api/deleteWebhook?drop_pending_updates=true" | Out-Null
  curl.exe -sS -X POST "$api/setWebhook" `
    -d "url=https://tg-webhook-worker.osif.workers.dev/tg/webhook" `
    -d "secret_token=$secret" `
    -d "max_connections=40" | Out-Null

  curl.exe -sS "$api/getWebhookInfo"
}

switch ($Action) {
  "rotate-bot" { Rotate-Bot; wrangler deploy }
  "rotate-webhook" { Rotate-Webhook; wrangler deploy }
  "rotate-all" { Rotate-Bot; Rotate-Webhook; wrangler deploy }
  "status" { wrangler secret list }
}
