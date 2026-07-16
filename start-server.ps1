<#
  Starts the Tit4Tat server bound to 0.0.0.0 so it's reachable from other
  devices on the current network, not just this machine (127.0.0.1) - over
  HTTPS with a self-signed cert generated on first run, so traffic (session
  cookies, temporary passwords relayed to new members, etc.) isn't sent
  across the network in plain text.
  Run stop-server.ps1 to shut it down cleanly.
#>
param(
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$pidFile = Join-Path $root ".server.pid"
$logFile = Join-Path $root "server.log"
$certFile = Join-Path $root "backend\certs\dev-cert.pem"
$keyFile = Join-Path $root "backend\certs\dev-key.pem"

# Refuse to start a second instance on the same port.
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
  Write-Host "Port $Port is already in use (PID $($existing[0].OwningProcess)). Run stop-server.ps1 first, or pass -Port to use a different one." -ForegroundColor Yellow
  exit 1
}

# Load .env (SMTP credentials, etc.) into this process's environment, if
# present, so the child python process inherits them - see .env.example.
# Never committed (see .gitignore); safe to be missing entirely.
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
      $key, $value = $line.Split("=", 2)
      [System.Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process")
    }
  }
}

# Find a LAN-reachable IPv4 address (skip loopback and link-local 169.254.x.x).
$lanIp = (
  Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -ne "127.0.0.1" } |
  Select-Object -First 1 -ExpandProperty IPAddress
)

# Self-signed cert covering localhost/127.0.0.1 and the detected LAN IP -
# generated once and reused; delete backend\certs\ to force a fresh one
# (e.g. if the LAN IP changes and browsers start warning about a SAN mismatch
# on top of the expected self-signed warning).
$certArgs = @((Join-Path $root "backend\generate_dev_cert.py"))
if ($lanIp) { $certArgs += $lanIp }
python @certArgs
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $certFile)) {
  Write-Host "Could not generate the dev TLS certificate - check that the 'cryptography' package is installed (pip install -r backend\requirements.txt)." -ForegroundColor Red
  exit 1
}

$env:TIT4TAT_HTTPS = "1"

Push-Location (Join-Path $root "backend")
try {
  $proc = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$Port", `
      "--ssl-keyfile", $keyFile, "--ssl-certfile", $certFile `
    -RedirectStandardOutput $logFile -RedirectStandardError "$logFile.err" `
    -WindowStyle Hidden -PassThru
} finally {
  Pop-Location
}

$proc.Id | Out-File -FilePath $pidFile -Encoding utf8 -NoNewline

Start-Sleep -Seconds 2
if ($proc.HasExited) {
  Write-Host "Server failed to start - check $logFile and $logFile.err" -ForegroundColor Red
  Remove-Item $pidFile -ErrorAction SilentlyContinue
  exit 1
}

Write-Host "Tit4Tat server started (PID $($proc.Id))." -ForegroundColor Green
if ($env:SMTP_HOST) {
  Write-Host "  SMTP configured : approval emails will actually be sent via $($env:SMTP_HOST)" -ForegroundColor Green
} else {
  Write-Host "  SMTP not configured - approval emails will be logged to $logFile.err instead of sent (see .env.example)" -ForegroundColor Yellow
}
Write-Host "  On this machine : https://localhost:$Port/"
if ($lanIp) {
  Write-Host "  On the network  : https://${lanIp}:${Port}/"
} else {
  Write-Host "  Could not detect a LAN IP address - check ipconfig for one manually." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "This uses a self-signed certificate, so browsers will show a one-time" -ForegroundColor Yellow
Write-Host "'connection is not private' warning - click through it (Advanced > Proceed)." -ForegroundColor Yellow
Write-Host "The connection is still genuinely encrypted; it just isn't backed by a" -ForegroundColor Yellow
Write-Host "certificate authority browsers trust automatically." -ForegroundColor Yellow
Write-Host ""
Write-Host "If other devices can't connect, allow inbound traffic on port $Port through Windows Firewall:"
Write-Host "  New-NetFirewallRule -DisplayName 'Tit4Tat' -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow"
Write-Host ""
Write-Host "Logs: $logFile"
Write-Host "Stop with: .\stop-server.ps1"
