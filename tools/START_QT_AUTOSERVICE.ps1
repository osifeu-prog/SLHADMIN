param()

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$ROOT = Split-Path -Parent $ROOT  # repo root

function Log($m){ Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }

function Wait-HttpOk([string]$url,[int]$timeoutSec=90){
  $t0 = Get-Date
  while(((Get-Date)-$t0).TotalSeconds -lt $timeoutSec){
    try{
      $r = curl.exe -sS -m 5 -D - $url 2>$null
      if($LASTEXITCODE -eq 0 -and $r -match "HTTP/1\.1 200"){ return $true }
    } catch {}
    Start-Sleep -Seconds 2
  }
  return $false
}

function Wait-DnsReady([string]$host,[int]$timeoutSec=120){
  $t0 = Get-Date
  while(((Get-Date)-$t0).TotalSeconds -lt $timeoutSec){
    $ok1=$false;$ok2=$false
    try { $ok1 = [bool](Resolve-DnsName -Name $host -Server 1.1.1.1 -ErrorAction Stop | Where-Object {$_.IPAddress}) } catch {}
    try { $ok2 = [bool](Resolve-DnsName -Name $host -Server 8.8.8.8 -ErrorAction Stop | Where-Object {$_.IPAddress}) } catch {}
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

Log "Repo: $ROOT"
Set-Location $ROOT

Log "Docker compose up"
docker compose up -d

Log "Wait local readyz"
if(-not (Wait-HttpOk "http://127.0.0.1:8001/readyz" 120)){ throw "guardian-api not ready locally" }

# start cloudflared quick tunnel in background
$logDir = Join-Path $ROOT "_tunnel"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ("cloudflared_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

Log "Start cloudflared quick tunnel, log: $logFile"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cloudflared"
$psi.Arguments = "tunnel --protocol http2 --url http://127.0.0.1:8001"
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError  = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$p = New-Object System.Diagnostics.Process
$p.StartInfo = $psi
[void]$p.Start()

$stdout = $p.StandardOutput
$stderr = $p.StandardError
$sw = New-Object System.IO.StreamWriter($logFile, $false, (New-Object System.Text.UTF8Encoding($false)))
$sw.AutoFlush = $true

$base = $null
$t0 = Get-Date
Log "Waiting for trycloudflare URL..."
while(((Get-Date)-$t0).TotalSeconds -lt 60){
  while(-not $stdout.EndOfStream){
    $line = $stdout.ReadLine()
    $sw.WriteLine($line)
    if($line -match "https://[a-z0-9-]+\.trycloudflare\.com"){
      $base = $Matches[0]
      break
    }
  }
  while(-not $stderr.EndOfStream){
    $line = $stderr.ReadLine()
    $sw.WriteLine($line)
  }
  if($base){ break }
  Start-Sleep -Milliseconds 200
}
if(-not $base){ throw "Did not capture trycloudflare URL. See $logFile" }

Log "Base=$base"
$host = ([uri]$base).Host

Log "Wait DNS for $host"
if(-not (Wait-DnsReady $host 180)){ throw "DNS not ready for $host" }

Log "Verify tunnel healthz2"
if(-not (Wait-HttpOk ($base + "/healthz2") 120)){ throw "Tunnel not serving healthz2" }

Log "Update .env WEBHOOK_URL"
$envPath = Join-Path $ROOT ".env"
if(-not (Test-Path $envPath)){ throw "Missing .env at $envPath" }
Upsert-EnvVar $envPath "WEBHOOK_URL" $base

Log "Set Telegram webhook directly"
$raw = Get-Content $envPath -Raw -Encoding utf8
$m = [regex]::Match($raw, '(?m)^\s*(?:BOT_TOKEN|TELEGRAM_TOKEN)\s*=\s*(.+?)\s*$')
if(-not $m.Success){ throw "BOT_TOKEN/TELEGRAM_TOKEN missing in .env" }
$tok = $m.Groups[1].Value.Trim()
$tok = $tok -replace '^[\x22\x27]+|[\x22\x27]+$',''  # trim " or '

$hook = $base + "/tg/webhook"
$encHook = [System.Uri]::EscapeDataString($hook)

$r1 = curl.exe -sS ("https://api.telegram.org/bot" + $tok + "/setWebhook?url=" + $encHook)
Log ("setWebhook: " + $r1)
$r2 = curl.exe -sS ("https://api.telegram.org/bot" + $tok + "/getWebhookInfo")
Log ("getWebhookInfo: " + $r2)

Log "DONE. Keep this window open to keep the tunnel alive."
Log "Try in Telegram: /start /status /points"
