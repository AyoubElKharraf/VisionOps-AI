<#
.SYNOPSIS
  Seed three demo cameras and optionally start MediaMTX publishers for the live grid.

.DESCRIPTION
  Creates/updates cameras:
    entrance     → …/cam1
    parking-lot  → …/cam2
    loading-dock → …/cam3

  Then prints the Live Monitor grid steps. With -Publish, starts Docker profile
  multicam (publisher-cam2 / publisher-cam3) alongside the default publisher.

.EXAMPLE
  .\scripts\demo-multicam.ps1
  .\scripts\demo-multicam.ps1 -Publish
  .\scripts\demo-multicam.ps1 -ApiUrl http://127.0.0.1:8001 -HostRtsp
#>
[CmdletBinding()]
param(
  [string]$ApiUrl = "http://127.0.0.1:8001",
  [string]$ApiKey = $(if ($env:VISIONOPS_API_KEY) { $env:VISIONOPS_API_KEY } else { "visionops-dev-key" }),
  [switch]$Publish,
  [switch]$HostRtsp,
  [string]$UiUrl = "http://localhost:3000/monitor"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

$rtspHost = if ($HostRtsp) { "127.0.0.1" } else { "mediamtx" }

$cameras = @(
  @{ name = "entrance"; path = "cam1"; location = "Main gate" },
  @{ name = "parking-lot"; path = "cam2"; location = "Lot A" },
  @{ name = "loading-dock"; path = "cam3"; location = "Dock 2" }
)

function Invoke-VisionOpsApi {
  param(
    [string]$Method,
    [string]$Path,
    [object]$Body = $null
  )
  $headers = @{ "X-API-Key" = $ApiKey; "Content-Type" = "application/json" }
  $uri = "$ApiUrl$Path"
  if ($null -eq $Body) {
    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers
  }
  $json = $Body | ConvertTo-Json -Depth 6
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -Body $json
}

Write-Host "VisionOps multi-cam demo" -ForegroundColor Cyan
Write-Host "API: $ApiUrl"

try {
  $null = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 5
} catch {
  throw "API not reachable at $ApiUrl/health. Start the stack first: docker compose up -d"
}

$existing = @()
try {
  $existing = @(Invoke-VisionOpsApi -Method GET -Path "/api/v1/cameras")
} catch {
  throw "Failed to list cameras (auth/API key?). $_"
}

foreach ($cam in $cameras) {
  $source = "rtsp://${rtspHost}:8554/$($cam.path)"
  $match = $existing | Where-Object { $_.name -eq $cam.name } | Select-Object -First 1
  if ($match) {
    Write-Host "Update camera $($cam.name) → $source"
    Invoke-VisionOpsApi -Method PATCH -Path "/api/v1/cameras/$($match.id)" -Body @{
      source_url = $source
      location   = $cam.location
      is_active  = $true
    } | Out-Null
  } else {
    Write-Host "Create camera $($cam.name) → $source"
    Invoke-VisionOpsApi -Method POST -Path "/api/v1/cameras" -Body @{
      name       = $cam.name
      source_url = $source
      location   = $cam.location
      is_active  = $true
    } | Out-Null
  }
}

if ($Publish) {
  Write-Host "Starting MediaMTX + 3 demo publishers (profile multicam)…" -ForegroundColor Yellow
  Push-Location $Root
  try {
    docker compose up -d mediamtx publisher
    docker compose --profile multicam up -d publisher-cam2 publisher-cam3
  } finally {
    Pop-Location
  }
  Write-Host "HLS tips:"
  Write-Host "  http://127.0.0.1:8888/cam1/index.m3u8"
  Write-Host "  http://127.0.0.1:8888/cam2/index.m3u8"
  Write-Host "  http://127.0.0.1:8888/cam3/index.m3u8"
}

Write-Host @"

Next steps
----------
1. Open $UiUrl
2. Layout → Grid  (preference saved as visionops.monitorLayout)
3. Video source → WebRTC (or HLS / Demo MP4)
4. Click a tile to focus the full single-camera monitor

Engine (Docker already runs multi_cam_runner against active cameras).
Local single-worker examples:
  python demo_roi.py --stream-detections --camera-name entrance --source rtsp://127.0.0.1:8554/cam1
  python demo_roi.py --stream-detections --camera-name parking-lot --source rtsp://127.0.0.1:8554/cam2
  python demo_roi.py --stream-detections --camera-name loading-dock --source rtsp://127.0.0.1:8554/cam3

Capture README screenshot (stack running):
  .\scripts\capture-live-grid.ps1

"@ -ForegroundColor Green
