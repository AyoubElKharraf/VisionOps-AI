<#
.SYNOPSIS
  Rollback Liquibase database changesets on PostgreSQL.

.DESCRIPTION
  Rolls back the specified number of changesets (rollbackCount) or to a specific tag (rollback <tag>).

.PARAMETER Count
  The number of changesets to roll back. Default is 1.

.PARAMETER Tag
  The target tag to rollback to. Overrides Count if supplied.

.PARAMETER Force
  Skip the confirmation prompt.

.EXAMPLE
  .\scripts\db-rollback.ps1 -Count 1
  .\scripts\db-rollback.ps1 -Tag v1.0
  .\scripts\db-rollback.ps1 -Count 3 -Force
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [int]$Count = 1,

    [Parameter()]
    [string]$Tag = "",

    [Parameter()]
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

if (-not $Force) {
    $targetMsg = if ($Tag) { "tag '$Tag'" } else { "$Count changeset(s)" }
    $confirmation = Read-Host "Are you sure you want to rollback $targetMsg? [y/N]"
    if ($confirmation -notmatch "^[yY](es)?$") {
        Write-Host "Rollback cancelled." -ForegroundColor Yellow
        exit 0
    }
}

Push-Location $ProjectRoot
try {
    if ($Tag) {
        Write-Host "[Liquibase] Rolling back to tag: $Tag..." -ForegroundColor Magenta
        docker compose run --rm liquibase rollback $Tag
    }
    else {
        Write-Host "[Liquibase] Rolling back $Count changeset(s)..." -ForegroundColor Magenta
        docker compose run --rm liquibase rollbackCount $Count
    }
}
finally {
    Pop-Location
}
