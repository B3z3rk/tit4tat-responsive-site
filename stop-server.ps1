<#
  Stops the Tit4Tat server started by start-server.ps1.
#>
param(
  [int]$Port = 8000
)

$root = $PSScriptRoot
$pidFile = Join-Path $root ".server.pid"

$stopped = $false

if (Test-Path $pidFile) {
  $processId = Get-Content $pidFile -ErrorAction SilentlyContinue
  if ($processId) {
    $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($proc) {
      Stop-Process -Id $processId -Force
      Write-Host "Stopped server (PID $processId)." -ForegroundColor Green
      $stopped = $true
    }
  }
  Remove-Item $pidFile -ErrorAction SilentlyContinue
}

if (-not $stopped) {
  # Fall back to whatever is actually listening on the port, but only kill it
  # if it's a python process -- never blind-kill an unrelated program.
  $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  foreach ($conn in $conns) {
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -match "python") {
      Stop-Process -Id $proc.Id -Force
      Write-Host "Stopped server (PID $($proc.Id), found listening on port $Port)." -ForegroundColor Green
      $stopped = $true
    } else {
      Write-Host "Port $Port is held by PID $($conn.OwningProcess) ($($proc.ProcessName)), which doesn't look like the Tit4Tat server - leaving it alone." -ForegroundColor Yellow
    }
  }
}

if (-not $stopped) {
  Write-Host "No running Tit4Tat server found on port $Port." -ForegroundColor Yellow
}
