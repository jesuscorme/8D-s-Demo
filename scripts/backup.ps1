# Respaldo completo: base de datos (pg_dump formato custom) + archivos privados (storage/) + manifiesto SHA-256.
# Uso: powershell -File scripts/backup.ps1 [-OutDir backups]
# La base y los archivos deben respaldarse juntos: los documentos de la BD apuntan a archivos de storage/.
param([string]$OutDir)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib.ps1')
$cfg = Read-DotEnv
if (-not $OutDir) { $OutDir = Join-Path $script:RepoRoot 'backups' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$target = Join-Path $OutDir $stamp
New-Item -ItemType Directory -Force $target | Out-Null

$pgDump = Join-Path (Split-Path $script:Psql) 'pg_dump.exe'
$env:PGPASSWORD = $cfg.APP_DB_PASSWORD
$dump = Join-Path $target "$($cfg.APP_DB_NAME).dump"
& $pgDump -U $cfg.APP_DB_USER -h $cfg.POSTGRES_HOST -p $cfg.POSTGRES_PORT -d $cfg.APP_DB_NAME -Fc --no-owner -f $dump
if ($LASTEXITCODE -ne 0) { throw 'pg_dump falló' }

$storageDir = if ($cfg.STORAGE_DIR) { $cfg.STORAGE_DIR } else { 'storage' }
if (-not [IO.Path]::IsPathRooted($storageDir)) { $storageDir = Join-Path $script:RepoRoot $storageDir }
$zip = Join-Path $target 'storage.zip'
if (Test-Path $storageDir) {
    Compress-Archive -Path (Join-Path $storageDir '*') -DestinationPath $zip -CompressionLevel Optimal
}

$lines = Get-ChildItem $target -File | ForEach-Object { "$((Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower())  $($_.Name)" }
$lines | Set-Content -Encoding ascii (Join-Path $target 'SHA256SUMS.txt')
"Respaldo en $target"
Get-ChildItem $target -File | ForEach-Object { "  $($_.Name)  $([math]::Round($_.Length / 1KB)) KB" }
