$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    docker compose run --rm -v "${PWD}/tests:/tests:ro" -v "${PWD}/voice-gateway/gateway:/gateway:ro" -e PYTHONPATH=/app:/ backend python -m pytest /tests -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
} finally { Pop-Location }
