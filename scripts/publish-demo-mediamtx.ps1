<#
.SYNOPSIS
  Publish the VisionOps demo MP4 to MediaMTX as RTSP path /cam1 (loop).
  Required for Live Monitor WebRTC / HLS playback.

.EXAMPLE
  .\scripts\publish-demo-mediamtx.ps1
  .\scripts\publish-demo-mediamtx.ps1 -RtspUrl rtsp://127.0.0.1:8554/cam1
#>
[CmdletBinding()]
param(
  [string]$RtspUrl = "rtsp://127.0.0.1:8554/cam1",
  [string]$VideoPath = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

if (-not $VideoPath) {
  $VideoPath = Join-Path $Root "visionops-engine\data\demo.mp4"
}

if (-not (Test-Path $VideoPath)) {
  Write-Host "Demo video missing — downloading…" -ForegroundColor Yellow
  $enginePy = Join-Path $Root "visionops-engine\.venv\Scripts\python.exe"
  if (Test-Path $enginePy) {
    & $enginePy -c "from main import ensure_demo_video; print(ensure_demo_video())"
  }
  if (-not (Test-Path $VideoPath)) {
    throw "Cannot find demo video at $VideoPath. Run the engine once to download it."
  }
}

$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
  Write-Host @"
ffmpeg not found in PATH.

Install options:
  1) winget install Gyan.FFmpeg
  2) Or download from https://ffmpeg.org and add to PATH

Then re-run this script.
"@ -ForegroundColor Red
  exit 1
}

Write-Host "Publishing $VideoPath → $RtspUrl (loop, Ctrl+C to stop)" -ForegroundColor Cyan
Write-Host "WebRTC play URL (via UI proxy): /api/mediamtx/whep?path=cam1"
Write-Host "HLS: http://127.0.0.1:8888/cam1/index.m3u8"

# ultrafast + zerolatency for low-latency WebRTC relay through MediaMTX
& ffmpeg -hide_banner -loglevel info `
  -re -stream_loop -1 -i $VideoPath `
  -an `
  -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p `
  -g 30 -keyint_min 30 `
  -f rtsp -rtsp_transport tcp `
  $RtspUrl
