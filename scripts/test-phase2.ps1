<#
.SYNOPSIS
  VisionOps AI — Phase 2 smoke test (ONNX export + ROI demo + latency metrics).

.EXAMPLE
  .\scripts\test-phase2.ps1
  .\scripts\test-phase2.ps1 -MaxFrames 60 -BenchmarkFrames 20
#>
[CmdletBinding()]
param(
  [int]$MaxFrames = 60,
  [int]$BenchmarkFrames = 20
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

Write-Host "VisionOps AI — Phase 2 test" -ForegroundColor Green
Write-Host "Root: $Root"

$engineDir = Join-Path $Root "visionops-engine"
$venvPython = Join-Path $engineDir ".venv\Scripts\python.exe"
Assert-True (Test-Path $venvPython) "venv missing. Run Phase 1 setup first (create .venv + pip install)."

# Ensure onnx package present for Ultralytics export
Write-Step "Ensuring onnx + onnxruntime installed"
& $venvPython -m pip install -q "onnx>=1.16.0" "onnxruntime>=1.19.0" "shapely>=2.0.0" "pydantic>=2.8.0"

Write-Step "Exporting YOLOv8n → ONNX (skip if exists)"
Push-Location $engineDir
try {
  & $venvPython export_onnx.py --model yolov8n.pt --output yolov8n.onnx
  Assert-True ($LASTEXITCODE -eq 0) "export_onnx.py failed with code $LASTEXITCODE"
  Assert-True (Test-Path (Join-Path $engineDir "yolov8n.onnx")) "yolov8n.onnx not found after export"
}
finally {
  Pop-Location
}

Write-Step "Running demo_roi.py (ONNX + ROI + benchmark)"
Push-Location $engineDir
try {
  & $venvPython demo_roi.py `
    --max-frames $MaxFrames `
    --benchmark-frames $BenchmarkFrames `
    --device cpu `
    --output data\annotated_phase2_roi.mp4
  Assert-True ($LASTEXITCODE -eq 0) "demo_roi.py failed with code $LASTEXITCODE"
}
finally {
  Pop-Location
}

Write-Step "Quick ONNX path via main.py --use-onnx"
Push-Location $engineDir
try {
  & $venvPython main.py --use-onnx --max-frames 15 --device cpu
  Assert-True ($LASTEXITCODE -eq 0) "main.py --use-onnx failed"
}
finally {
  Pop-Location
}

Write-Host ""
Write-Host "Phase 2 smoke test PASSED" -ForegroundColor Green
Write-Host "Check latency METRICS lines above (PyTorch vs ONNX avg_infer / FPS)." -ForegroundColor Yellow
exit 0
