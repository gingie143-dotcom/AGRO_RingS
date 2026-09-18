$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if (-not (Test-Path '.env')) { & "$PSScriptRoot/setup.ps1" }
    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose configuration invalid' }
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Startup failed; inspect docker compose logs' }
    Write-Host 'Open http://localhost:3000 when backend is healthy. Credentials are in .env.'
} finally { Pop-Location }
