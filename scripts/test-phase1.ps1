<#
.SYNOPSIS
  VisionOps AI — Phase 1 smoke test (Docker services + YOLO engine).

.EXAMPLE
  .\scripts\test-phase1.ps1
  .\scripts\test-phase1.ps1 -SkipDocker -MaxFrames 15
#>
[CmdletBinding()]
param(
  [switch]$SkipDocker,
  [switch]$SkipEngine,
  [int]$MaxFrames = 30
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Step($Message) {
  Write-Host ""
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-True($Condition, $Message) {
  if (-not $Condition) {
    throw $Message
  }
}

Write-Host "VisionOps AI — Phase 1 test" -ForegroundColor Green
Write-Host "Root: $Root"

# --- Docker services ---
if (-not $SkipDocker) {
  Write-Step "Checking Docker availability"
  docker version | Out-Null

  Write-Step "Starting docker compose (detached)"
  docker compose up -d

  Write-Step "Waiting for containers"
  Start-Sleep -Seconds 8

  $expected = @(
    "visionops-mediamtx",
    "visionops-postgres",
    "visionops-redis",
    "visionops-minio"
  )

  $psJson = docker compose ps --format json 2>$null
  $runningNames = @()

  if ($psJson) {
    # Docker Compose v2 may emit NDJSON (one object per line) or a JSON array
    $trimmed = $psJson.Trim()
    if ($trimmed.StartsWith("[")) {
      $items = $trimmed | ConvertFrom-Json
    }
    else {
      $items = $trimmed -split "`n" | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json }
    }
    foreach ($item in @($items)) {
      $name = $item.Name
      if (-not $name) { $name = $item.Service }
      $state = "$($item.State) $($item.Status)"
      Write-Host ("  {0}: {1}" -f $name, $state)
      if ($state -match "running|Up") {
        $runningNames += $name
      }
    }
  }
  else {
    # Fallback: plain text
    $plain = docker compose ps
    Write-Host $plain
    foreach ($name in $expected) {
      if ($plain -match $name) { $runningNames += $name }
    }
  }

  foreach ($name in $expected) {
    $ok = $runningNames | Where-Object { $_ -eq $name -or $_ -like "*$name*" -or $name -like "*$_*" }
    # Match by service name fragment as compose Name may vary
    $found = $false
    foreach ($rn in $runningNames) {
      if ($rn -match "mediamtx" -and $name -match "mediamtx") { $found = $true }
      if ($rn -match "postgres" -and $name -match "postgres") { $found = $true }
      if ($rn -match "redis" -and $name -match "redis") { $found = $true }
      if ($rn -match "minio" -and $name -match "minio") { $found = $true }
      if ($rn -eq $name) { $found = $true }
    }
    Assert-True $found "Container not running: $name"
  }

  Write-Host "Docker services OK" -ForegroundColor Green
}
else {
  Write-Step "Skipping Docker checks (-SkipDocker)"
}

# --- YOLO engine ---
if (-not $SkipEngine) {
  Write-Step "Preparing Python venv for visionops-engine"
  $engineDir = Join-Path $Root "visionops-engine"
  $venvDir = Join-Path $engineDir ".venv"
  $python = $null

  foreach ($candidate in @("py -3.12", "py -3.11", "python3.12", "python3.11", "python")) {
    try {
      if ($candidate -like "py -*") {
        $verArgs = $candidate.Substring(3).Trim()
        $ver = & py $verArgs -c "import sys; print('{0}.{1}'.format(sys.version_info[0], sys.version_info[1]))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver) {
          $python = $candidate
          Write-Host "Using Python launcher: $candidate ($ver)"
          break
        }
      }
      else {
        $ver = & $candidate -c "import sys; print('{0}.{1}'.format(sys.version_info[0], sys.version_info[1]))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver) {
          $python = $candidate
          Write-Host "Using interpreter: $candidate ($ver)"
          break
        }
      }
    }
    catch { }
  }

  Assert-True ($null -ne $python) "Python 3.11+ not found. Install Python 3.11 or 3.12 and retry."

  if (-not (Test-Path $venvDir)) {
    Write-Host "Creating venv at $venvDir"
    if ($python -like "py -*") {
      $verArgs = $python.Substring(3).Trim()
      & py $verArgs -m venv $venvDir
    }
    else {
      & $python -m venv $venvDir
    }
  }

  $venvPython = Join-Path $venvDir "Scripts\python.exe"
  Assert-True (Test-Path $venvPython) "venv python missing: $venvPython"

  Write-Step "Installing engine requirements (may take a few minutes)"
  & $venvPython -m pip install --upgrade pip
  & $venvPython -m pip install -r (Join-Path $engineDir "requirements.txt")

  $output = Join-Path $engineDir "data\annotated_phase1_test.mp4"
  Write-Step "Running YOLO inference (max $MaxFrames frames)"
  Push-Location $engineDir
  try {
    & $venvPython main.py --max-frames $MaxFrames --output $output --device cpu
    Assert-True ($LASTEXITCODE -eq 0) "Engine exited with code $LASTEXITCODE"
  }
  finally {
    Pop-Location
  }

  Write-Host "Engine OK" -ForegroundColor Green
}
else {
  Write-Step "Skipping engine test (-SkipEngine)"
}

Write-Host ""
Write-Host "Phase 1 smoke test PASSED" -ForegroundColor Green
exit 0
