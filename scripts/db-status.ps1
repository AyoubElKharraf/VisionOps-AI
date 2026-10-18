<#
.SYNOPSIS
  Check Liquibase database migration status against PostgreSQL.

.DESCRIPTION
  Runs `liquibase status --verbose` inside the dockerized Liquibase container.
  Reports pending changesets and current database changelog state.

.EXAMPLE
  .\scripts\db-status.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Push-Location $ProjectRoot
try {
    Write-Host "[Liquibase] Checking database migration status..." -ForegroundColor Cyan
    docker compose run --rm liquibase status --verbose
}
finally {
    Pop-Location
}
