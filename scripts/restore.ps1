param([Parameter(Mandatory=$true)][string]$File,[Parameter(Mandatory=$true)][string]$Database)
$ErrorActionPreference = 'Stop'
if ($Database -notmatch '^restore_[A-Za-z0-9_]+$') { throw 'Use a NEW database named restore_*' }
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    docker compose exec -T maintenance python -m app.backups restore --file $File --database $Database
    if ($LASTEXITCODE -ne 0) { throw 'Restore failed; live database was not replaced' }
} finally { Pop-Location }
