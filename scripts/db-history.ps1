<#
.SYNOPSIS
  View history of deployed Liquibase changesets on PostgreSQL.

.DESCRIPTION
  Runs `liquibase history` inside the dockerized Liquibase container.

.EXAMPLE
  .\scripts\db-history.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Push-Location $ProjectRoot
try {
    Write-Host "[Liquibase] Retrieving deployed migration history..." -ForegroundColor Cyan
    docker compose run --rm liquibase history
}
finally {
    Pop-Location
}
