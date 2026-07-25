<#
.SYNOPSIS
  VisionOps AI — Phase 5 local validation (unit tests + optional ONNX bench).
#>
[CmdletBinding()]
param(
  [switch]$SkipBench,
  [int]$BenchFrames = 40
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

Write-Host "VisionOps AI — Phase 5" -ForegroundColor Green

Write-Step "Engine unit tests"
$engPy = Join-Path $Root "visionops-engine\.venv\Scripts\python.exe"
if (-not (Test-Path $engPy)) { throw "Engine venv missing" }
& $engPy -m pip install -q -r (Join-Path $Root "visionops-engine\requirements-dev.txt")
Push-Location (Join-Path $Root "visionops-engine")
try {
  & $engPy -m ruff check roi_manager.py onnx_engine.py export_onnx.py alert_client.py tests
  & $engPy -m pytest -q tests
  if ($LASTEXITCODE -ne 0) { throw "Engine tests failed" }
}
finally { Pop-Location }

Write-Step "Backend unit/API tests (needs Postgres on DATABASE_URL)"
$backPy = Join-Path $Root "visionops-backend\.venv\Scripts\python.exe"
if (-not (Test-Path $backPy)) { throw "Backend venv missing" }
& $backPy -m pip install -q -r (Join-Path $Root "visionops-backend\requirements-dev.txt")
$env:DATABASE_URL = "postgresql://visionops:visionops_secret@localhost:5434/visionops_db"
Push-Location (Join-Path $Root "visionops-backend")
try {
  & $backPy -m ruff check app tests
  & $backPy -m pytest -q tests
  if ($LASTEXITCODE -ne 0) { throw "Backend tests failed" }
}
finally { Pop-Location }

if (-not $SkipBench) {
  Write-Step "ONNX performance bench"
  Push-Location $Root
  try {
    & $engPy (Join-Path $Root "scripts\bench_phase5.py") --frames $BenchFrames
  }
  finally { Pop-Location }
}

Write-Host "`nPhase 5 local validation PASSED" -ForegroundColor Green
