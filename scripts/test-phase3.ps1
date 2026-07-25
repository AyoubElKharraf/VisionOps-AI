<#
.SYNOPSIS
  VisionOps AI — Phase 3 smoke test (API + Celery + MinIO alert pipeline).

.EXAMPLE
  .\scripts\test-phase3.ps1
#>
[CmdletBinding()]
param(
  [int]$ApiPort = 8001,
  [int]$MaxFrames = 45
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Step($Message) {
  Write-Host ""
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-True($Condition, $Message) {
  if (-not $Condition) { throw $Message }
}

Write-Host "VisionOps AI — Phase 3 test" -ForegroundColor Green

Write-Step "Docker services"
docker compose up -d
Start-Sleep -Seconds 6
docker compose ps

$backendVenv = Join-Path $Root "visionops-backend\.venv\Scripts\python.exe"
if (-not (Test-Path $backendVenv)) {
  Write-Step "Creating backend venv"
  py -3.12 -m venv (Join-Path $Root "visionops-backend\.venv")
  & $backendVenv -m pip install -q --upgrade pip
  & $backendVenv -m pip install -q -r (Join-Path $Root "visionops-backend\requirements.txt")
}

Write-Step "Starting API on port $ApiPort"
$api = Start-Process -PassThru -WindowStyle Hidden `
  -FilePath $backendVenv `
  -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","$ApiPort" `
  -WorkingDirectory (Join-Path $Root "visionops-backend")

Write-Step "Starting Celery worker (solo pool)"
$celery = Start-Process -PassThru -WindowStyle Hidden `
  -FilePath $backendVenv `
  -ArgumentList "-m","celery","-A","app.celery_app.celery_app","worker","--loglevel=info","--pool=solo" `
  -WorkingDirectory (Join-Path $Root "visionops-backend")

try {
  $healthy = $false
  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
      $h = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 2
      if ($h.status -eq "ok") { $healthy = $true; break }
    } catch { }
  }
  Assert-True $healthy "API health check failed on port $ApiPort"
  Write-Host "API OK: $($h | ConvertTo-Json -Compress)" -ForegroundColor Green

  Write-Step "Create camera"
  $camBody = @{ name = "phase3-cam"; source_url = "file://demo"; location = "lab" } | ConvertTo-Json
  try {
    $cam = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$ApiPort/api/v1/cameras" -ContentType "application/json" -Body $camBody
  } catch {
    # already exists is fine
    $cam = (Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/cameras") | Where-Object { $_.name -eq "phase3-cam" } | Select-Object -First 1
  }
  Write-Host "Camera: $($cam.id)"

  Write-Step "Engine demo with --post-alerts"
  $enginePy = Join-Path $Root "visionops-engine\.venv\Scripts\python.exe"
  Assert-True (Test-Path $enginePy) "Engine venv missing"
  Push-Location (Join-Path $Root "visionops-engine")
  try {
    & $enginePy demo_roi.py --skip-benchmark --max-frames $MaxFrames --post-alerts --api-url "http://127.0.0.1:$ApiPort" --device cpu
    Assert-True ($LASTEXITCODE -eq 0) "demo_roi failed"
  }
  finally {
    Pop-Location
  }

  Write-Step "Waiting for Celery media processing"
  Start-Sleep -Seconds 12
  $alerts = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/alerts?limit=10"
  Assert-True ($alerts.Count -gt 0) "No alerts stored in PostgreSQL"
  Write-Host ("Alerts stored: {0}" -f $alerts.Count) -ForegroundColor Green
  $ready = @($alerts | Where-Object { $_.status -eq "ready" })
  Write-Host ("Alerts ready (media uploaded): {0}" -f $ready.Count) -ForegroundColor Green
  if ($ready.Count -gt 0) {
    $sample = $ready[0]
    Write-Host ("sample snapshot_key={0}" -f $sample.snapshot_object_key)
    Write-Host ("sample clip_key={0}" -f $sample.clip_object_key)
  }
}
finally {
  if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue }
  if ($celery -and -not $celery.HasExited) { Stop-Process -Id $celery.Id -Force -ErrorAction SilentlyContinue }
}

Write-Host ""
Write-Host "Phase 3 smoke test PASSED" -ForegroundColor Green
exit 0
