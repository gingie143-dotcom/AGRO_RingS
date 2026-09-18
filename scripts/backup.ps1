$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    docker compose exec -T maintenance python -m app.backups backup
    if ($LASTEXITCODE -ne 0) { throw 'Backup failed' }
} finally { Pop-Location }
