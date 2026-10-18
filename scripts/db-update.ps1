<#
.SYNOPSIS
  Apply pending Liquibase migrations to PostgreSQL.

.DESCRIPTION
  Runs `liquibase update` inside the dockerized Liquibase container.

.EXAMPLE
  .\scripts\db-update.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Push-Location $ProjectRoot
try {
    Write-Host "[Liquibase] Applying pending database migrations..." -ForegroundColor Green
    docker compose run --rm liquibase update
}
finally {
    Pop-Location
}
