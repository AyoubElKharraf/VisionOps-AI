<#
.SYNOPSIS
  Capture docs/screenshots/live-grid.png via Playwright.

.EXAMPLE
  .\scripts\capture-live-grid.ps1
  .\scripts\capture-live-grid.ps1 -Live
#>
[CmdletBinding()]
param(
  [switch]$Live
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Ui = Join-Path $Root "visionops-ui"

function Ensure-Playwright {
  $pkg = Join-Path $Ui "node_modules\playwright"
  if (-not (Test-Path $pkg)) {
    Write-Host "Installing npm deps + Playwright Chromium in visionops-ui..." -ForegroundColor Yellow
    Push-Location $Ui
    try {
      npm install
      npx playwright install chromium
    } finally {
      Pop-Location
    }
    return
  }

  # Browsers may be missing even when the npm package is present (fresh machine / different cache).
  Push-Location $Ui
  try {
    $probe = npx playwright install chromium 2>&1
    if ($probe) { Write-Host $probe }
  } finally {
    Pop-Location
  }
}

Ensure-Playwright

if ($Live) {
  $env:CAPTURE_LIVE = "1"
} else {
  Remove-Item Env:CAPTURE_LIVE -ErrorAction SilentlyContinue
}

Push-Location $Root
try {
  node .\scripts\capture-live-grid.mjs
} finally {
  Pop-Location
}
