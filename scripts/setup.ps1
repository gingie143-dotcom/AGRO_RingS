$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$target = Join-Path $root '.env'
if (Test-Path $target) { throw '.env already exists. No changes made.' }
function New-Secret {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).Replace('+','-').Replace('/','_')
}
$content = [IO.File]::ReadAllText((Join-Path $root '.env.example'))
foreach ($key in @('POSTGRES_PASSWORD','SECRET_KEY','SERVICE_TOKEN','ADMIN_PASSWORD','ARI_PASSWORD','BACKUP_KEY')) {
    $value = New-Secret
    if ($key -ne 'BACKUP_KEY') { $value = $value.TrimEnd('=') }
    $content = [regex]::Replace($content, "(?m)^${key}=\r?$", "${key}=$value")
}
[IO.File]::WriteAllText($target,$content,(New-Object Text.UTF8Encoding($false)))
Write-Host 'Created .env. Read ADMIN_PASSWORD locally. Keep BACKUP_KEY in a separate secure location.'
