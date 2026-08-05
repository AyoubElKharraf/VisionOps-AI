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

if (-not (Test-Path (Join-Path $Ui "node_modules\playwright"))) {
  Write-Host "Installing Playwright in visionops-ui…" -ForegroundColor Yellow
  Push-Location $Ui
  try {
    npm install
    npx playwright install chromium
  } finally {
    Pop-Location
  }
}

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
