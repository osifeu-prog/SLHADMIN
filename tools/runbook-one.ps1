param([switch]$SetWebhook,[int]$Port=8001)

$ErrorActionPreference="Stop"
Set-Location "D:\telegram-guardian-DOCKER-COMPOSE-ENTERPRISE"

function Import-DotEnv([string]$Path){
  if(-not (Test-Path $Path)){ return }
  foreach($ln in (Get-Content $Path -Encoding utf8)){
    $s=$ln.Trim()
    if(-not $s -or $s.StartsWith("#")){ continue }
    if($s -notmatch "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$"){ continue }
    $k=$Matches[1]; $v=$Matches[2]
    if(($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'"))){ $v=$v.Substring(1,$v.Length-2) }
    Set-Item -Path "Env:$k" -Value $v
  }
}
Import-DotEnv ".\.env.secrets.local"
Import-DotEnv ".\.env"
if($SetWebhook -and (-not $env:TELEGRAM_TOKEN)){ throw "TELEGRAM_TOKEN missing" }

$base="http://127.0.0.1:$Port"
$runDir=".runbook"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$log = Join-Path $runDir "cloudflared.log"
Remove-Item $log -Force -ErrorAction SilentlyContinue | Out-Null

Write-Host "==== [1/5] docker compose up ===="
docker compose up -d --build
docker compose ps

Write-Host "==== [2/5] wait for healthz ===="
$ok=$false
for($i=1;$i -le 60;$i++){
  try {
    $r = curl.exe -sS "$base/healthz2"
    if($r -match '"ok"\s*:\s*true'){ $ok=$true; break }
  } catch {}
  Start-Sleep 2
}
if(-not $ok){
  docker compose logs --tail 200 guardian-api
  throw "guardian-api not healthy on $base"
}
Write-Host "API OK -> $base"
curl.exe -sS -D - "$base/readyz" | Out-Host

Write-Host "==== [3/5] start cloudflared (new window + logfile) ===="
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$cmd = "cloudflared.exe tunnel --url $base --loglevel info --logfile `"$log`""
Start-Process -FilePath "cmd.exe" -ArgumentList "/k",$cmd -WindowStyle Normal | Out-Null

Write-Host "Waiting for BASE in log: $log"
$BASE=$null
for($i=1;$i -le 90;$i++){
  if(Test-Path $log){
    $txt = Get-Content $log -Raw -ErrorAction SilentlyContinue
    if($txt){
      $m=[regex]::Match($txt,'https://[a-z0-9-]+\.trycloudflare\.com','IgnoreCase')
      if($m.Success){ $BASE=$m.Value; break }
    }
  }
  Start-Sleep 1
}
if(-not $BASE){ throw "Could not extract BASE from $log" }

Write-Host "BASE -> $BASE"

# ---- DNS warmup (Quick Tunnel sometimes not resolvable immediately) ----
$cfHost = ([uri]$BASE).Host
Write-Host "Waiting for DNS to resolve: $cfHost"
$dnsOk=$false
for($j=1;$j -le 90;$j++){
  try {
    Resolve-DnsName $cfHost -ErrorAction Stop | Out-Null
    $dnsOk=$true
    break
  } catch {}
  Start-Sleep 1
}
if(-not $dnsOk){
  throw "DNS did not resolve for $cfHost after 90s. Keep cloudflared window open and try again."
}
Write-Host "DNS OK -> $cfHost"
# ---------------------------------------------------------------
Write-Host "==== [4/5] verify tunnel ===="
curl.exe -sS -D - "$BASE/healthz2" | Out-Host
curl.exe -sS -D - "$BASE/readyz"  | Out-Host

if(-not $SetWebhook){
  Write-Host "Done. (Webhook not set)."
  exit 0
}

Write-Host "==== [5/5] set Telegram webhook ===="
$tok=$env:TELEGRAM_TOKEN
$HOOK="$BASE/tg/webhook"
$enc=[System.Uri]::EscapeDataString($HOOK)
curl.exe -sS "https://api.telegram.org/bot$tok/setWebhook?url=$enc&drop_pending_updates=true&max_connections=40" | Out-Host
curl.exe -sS "https://api.telegram.org/bot$tok/getWebhookInfo" | Out-Host

Write-Host "OK. Keep the cloudflared window OPEN."




