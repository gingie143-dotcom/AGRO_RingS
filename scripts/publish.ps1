param([Parameter(Mandatory=$true)][string]$Repository)
$ErrorActionPreference = 'Stop'
if ($Repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { throw 'Use owner/repository' }
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required' }
    gh auth status
    if ($LASTEXITCODE -ne 0) { throw 'Run gh auth login first' }
    if (-not (Test-Path '.git')) {
        git init -b main
        if ($LASTEXITCODE -ne 0) { throw 'git init failed' }
        git add .
        if ($LASTEXITCODE -ne 0) { throw 'git add failed' }
        git commit -m 'Initial AI Caller implementation; see docs/status.md for gates'
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed; configure Git identity' }
    }
    gh repo create $Repository --private --source . --remote origin --push
    if ($LASTEXITCODE -ne 0) { throw 'GitHub publication failed; existing repositories were not overwritten' }
} finally { Pop-Location }
