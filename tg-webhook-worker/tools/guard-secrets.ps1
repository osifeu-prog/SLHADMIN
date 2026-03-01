param(
  [Parameter(Mandatory=$false)][string]$VaultDir = ".vault",
  [Parameter(Mandatory=$false)][string]$SecretFileName = "tg_secret_token.secret",
  [Parameter(Mandatory=$false)][int]$SecretLen = 48
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Ensure-GitIgnore {
  param([string]$GitIgnorePath)
  if (-not (Test-Path $GitIgnorePath)) { New-Item -ItemType File -Path $GitIgnorePath | Out-Null }
  $need = @(".vault/","*.secret","*.token","*.key",".tg_secret_token.txt")
  $existing = Get-Content $GitIgnorePath -ErrorAction SilentlyContinue
  foreach ($x in $need) {
    if ($existing -notcontains $x) { Add-Content -Encoding utf8 $GitIgnorePath $x }
  }
}

function New-TelegramSafeSecret {
  param([int]$Len)
  return -join ((97..122) + (48..57) | Get-Random -Count $Len | ForEach-Object {[char]$_})
}

function Save-SecretFile {
  param([string]$Path, [string]$Value)
  Set-Content -Encoding ascii -NoNewline $Path $Value
}

function Harden-Acl {
  param([string]$Path)
  # Make sure file exists first
  if (-not (Test-Path $Path)) { throw "Cannot harden ACL: file not found: $Path" }
  & icacls $Path /inheritance:r | Out-Null
  & icacls $Path /grant:r ("{0}:F" -f $env:USERNAME) | Out-Null
}

function Upload-WranglerSecret {
  param([string]$Key, [string]$Value)
  $null = $Value | wrangler secret put $Key
}

# --- main ---
$root = Get-Location
$vault = Join-Path $root $VaultDir
New-Item -ItemType Directory -Force -Path $vault | Out-Null

$gi = Join-Path $root ".gitignore"
Ensure-GitIgnore -GitIgnorePath $gi

$secretPath = Join-Path $vault $SecretFileName

$secret = New-TelegramSafeSecret -Len $SecretLen
Save-SecretFile -Path $secretPath -Value $secret
Harden-Acl -Path $secretPath
Upload-WranglerSecret -Key "TG_SECRET_TOKEN" -Value $secret

Write-Host "OK: TG secret generated, stored locally (vault), ACL-hardened, and uploaded to wrangler." -ForegroundColor Green
Write-Host ("Vault file: {0}" -f $secretPath) -ForegroundColor Green
