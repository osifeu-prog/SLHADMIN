param()

$ErrorActionPreference = "Stop"

function Wait-DnsReady([string]$DnsName,[int]$TimeoutSec=120){
  $t0 = Get-Date
  while(((Get-Date)-$t0).TotalSeconds -lt $TimeoutSec){
    $ok1 = $false; $ok2 = $false
    try { $ok1 = [bool](Resolve-DnsName -Name $DnsName -Server 1.1.1.1 -ErrorAction Stop | Where-Object { $_.IPAddress }) } catch {}
    try { $ok2 = [bool](Resolve-DnsName -Name $DnsName -Server 8.8.8.8 -ErrorAction Stop | Where-Object { $_.IPAddress }) } catch {}
    if($ok1 -or $ok2){ return $true }
    Start-Sleep -Seconds 2
  }
  return $false
}

$base = Read-Host "Paste https://xxxxx.trycloudflare.com from cloudflared window"
if(-not $base.StartsWith("http")){ throw "base must start with http/https" }

$dnsName = ([uri]$base).Host
if(-not (Wait-DnsReady -DnsName $dnsName -TimeoutSec 120)){
  throw "DNS not ready for $dnsName"
}

# verify tunnel is serving
$check = curl.exe -sS -m 5 -D - "$base/healthz2" 2>&1
if($LASTEXITCODE -ne 0){ throw "curl to $base/healthz2 failed: $check" }

# load .env for token
$envPath = Join-Path (Get-Location) ".env"
if(!(Test-Path $envPath)){ throw "Missing .env at $envPath" }
$envText = Get-Content $envPath -Raw -Encoding utf8

function Get-EnvVar([string]$name,[string]$text){
  $m = [regex]::Match($text, "(?m)^\s*$name\s*=\s*(.+?)\s*$")
  if(!$m.Success){ return $null }
  return $m.Groups[1].Value.Trim()
}

$token = (Get-EnvVar "BOT_TOKEN" $envText)
if(-not $token){ $token = (Get-EnvVar "TELEGRAM_TOKEN" $envText) }
if(-not $token){ throw "Missing BOT_TOKEN/TELEGRAM_TOKEN in .env" }

$api = "https://api.telegram.org/bot$token"
$webhook = "$base/tg/webhook"

"Setting webhook to: $webhook"
curl.exe -sS -X POST "$api/setWebhook" -d "url=$webhook"
"`nWebhook info:"
curl.exe -sS "$api/getWebhookInfo"
