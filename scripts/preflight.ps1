$ErrorActionPreference = 'Stop'
Write-Host 'Checking local tools and Docker Engine...'
foreach ($tool in @('git','docker')) { if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool not found in PATH" } }
git --version
docker version
if ($LASTEXITCODE -ne 0) { throw 'Docker Engine unavailable. Start Docker Desktop.' }
docker compose version
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose unavailable' }
docker run --rm hello-world
if ($LASTEXITCODE -ne 0) { throw 'Container smoke test failed' }
Write-Host 'Available disk space:'
Get-PSDrive -PSProvider FileSystem | Select-Object Name, Used, Free
$conflicts = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -eq 3000
if ($conflicts) { throw 'Port 3000 is already in use' }
Write-Host 'PREFLIGHT PASSED. This does not verify SIP, AI, backup restoration or GPU.'
