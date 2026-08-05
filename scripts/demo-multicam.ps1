<#
.SYNOPSIS
  Seed three demo cameras and optionally start MediaMTX publishers for the live grid.

.DESCRIPTION
  Creates/updates cameras:
    entrance     -> .../cam1
    parking-lot  -> .../cam2
    loading-dock -> .../cam3

  Then prints the Live Monitor grid steps. With -Publish, starts Docker profile
  multicam (publisher-cam2 / publisher-cam3) alongside the default publisher.

.EXAMPLE
  .\scripts\demo-multicam.cmd -Publish
  .\scripts\demo-multicam.ps1 -Publish
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
    [hashtable]$Body = $null
  )
  $headers = @{ "X-API-Key" = $ApiKey; "Content-Type" = "application/json" }
  $uri = "$ApiUrl$Path"
  if ($null -eq $Body) {
    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers
  }
  $json = $Body | ConvertTo-Json -Depth 6 -Compress
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -Body $json
}

function ConvertTo-FlatList {
  <#
    Windows PowerShell 5.1 quirk:
      @(Invoke-RestMethod ...)  -> nested Object[] (count 1) when JSON is an array
      $r = Invoke-RestMethod; @($r) -> flat list
    Also unwrap one level if we still receive a nested array.
  #>
  param($Response)
  $list = New-Object System.Collections.Generic.List[object]
  # Prefer foreach over @() around the cmdlet call itself.
  foreach ($item in $Response) {
    if ($item -is [System.Array]) {
      foreach ($nested in $item) { [void]$list.Add($nested) }
    } else {
      [void]$list.Add($item)
    }
  }
  # Unary comma prevents PowerShell from unraveling a single-element result on return.
  return , $list.ToArray()
}

function Get-CameraId {
  param($Camera)
  if ($null -eq $Camera) { return $null }
  $one = $Camera
  if ($Camera -is [System.Array]) { $one = $Camera[0] }
  $id = [string]$one.id
  if ($id -notmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$') {
    throw "Invalid camera id '$id' (refusing to PATCH)."
  }
  return $id
}

Write-Host "VisionOps multi-cam demo" -ForegroundColor Cyan
Write-Host "API: $ApiUrl"

try {
  $null = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 5
} catch {
  throw "API not reachable at $ApiUrl/health. Start the stack first: docker compose up -d"
}

try {
  # Assign first — do NOT wrap Invoke-RestMethod in @() under Windows PowerShell 5.1.
  $rawCameras = Invoke-VisionOpsApi -Method GET -Path "/api/v1/cameras"
  $existing = ConvertTo-FlatList $rawCameras
} catch {
  throw "Failed to list cameras (auth/API key?). $_"
}

Write-Host "Found $($existing.Count) camera(s) on API"

foreach ($cam in $cameras) {
  $camName = [string]$cam["name"]
  $camPath = [string]$cam["path"]
  $camLocation = [string]$cam["location"]
  $source = "rtsp://${rtspHost}:8554/$camPath"

  $match = $null
  foreach ($item in $existing) {
    if ([string]$item.name -eq $camName) {
      $match = $item
      break
    }
  }

  if ($null -ne $match) {
    $cameraId = Get-CameraId $match
    Write-Host "Update camera $camName ($cameraId) -> $source"
    Invoke-VisionOpsApi -Method PATCH -Path "/api/v1/cameras/$cameraId" -Body @{
      source_url = $source
      location   = $camLocation
      is_active  = $true
    } | Out-Null
  } else {
    Write-Host "Create camera $camName -> $source"
    $created = Invoke-VisionOpsApi -Method POST -Path "/api/v1/cameras" -Body @{
      name       = $camName
      source_url = $source
      location   = $camLocation
      is_active  = $true
    }
    $existing = @($existing + $created)
  }
}

if ($Publish) {
  Write-Host "Starting MediaMTX + 3 demo publishers (profile multicam)..." -ForegroundColor Yellow
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
2. Layout -> Grid  (preference saved as visionops.monitorLayout)
3. Video source -> WebRTC (or HLS / Demo MP4)
4. Click a tile to focus the full single-camera monitor

Capture README screenshot:
  .\scripts\capture-live-grid.cmd

"@ -ForegroundColor Green
