# Restaura un respaldo de backup.ps1 en una base NUEVA (la borra si existe) y, opcionalmente, los archivos.
# Uso: powershell -File scripts/restore.ps1 -From backups\<fecha> [-Database d8_demo] [-SkipStorage]
# Atención: con la base por defecto se sustituye la base de trabajo. Detén la API antes.
# Usa el rol de la aplicación (CREATEDB); no necesita el superusuario.
param([Parameter(Mandatory = $true)][string]$From, [string]$Database, [switch]$SkipStorage)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib.ps1')
$cfg = Read-DotEnv
if (-not $Database) { $Database = $cfg.APP_DB_NAME }
if ($Database -notmatch '^[a-z0-9_]+$') { throw "Nombre de base no válido: $Database" }
$dump = Get-ChildItem $From -Filter '*.dump' | Select-Object -First 1
if (-not $dump) { throw "No hay archivo .dump en $From" }

# 1. Verificar el manifiesto antes de tocar nada.
$sums = Join-Path $From 'SHA256SUMS.txt'
if (Test-Path $sums) {
    foreach ($line in Get-Content $sums) {
        $hash, $name = $line -split '\s+', 2
        $actual = (Get-FileHash (Join-Path $From $name) -Algorithm SHA256).Hash.ToLower()
        if ($actual -ne $hash) { throw "El archivo $name del respaldo no coincide con su SHA-256" }
    }
    'Manifiesto SHA-256 verificado'
} else { Write-Warning 'Respaldo sin SHA256SUMS.txt: no se pudo verificar' }

$bin = Split-Path $script:Psql
$env:PGPASSWORD = $cfg.APP_DB_PASSWORD
$admin = @('-U', $cfg.APP_DB_USER, '-h', $cfg.POSTGRES_HOST, '-p', $cfg.POSTGRES_PORT, '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-q', '-tA')
& $script:Psql @admin -c "drop database if exists $Database with (force)" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'No se pudo borrar la base destino' }
& $script:Psql @admin -c "create database $Database encoding 'UTF8'" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la base destino' }
& (Join-Path $bin 'pg_restore.exe') -U $cfg.APP_DB_USER -h $cfg.POSTGRES_HOST -p $cfg.POSTGRES_PORT -d $Database --no-owner --exit-on-error $dump.FullName
if ($LASTEXITCODE -ne 0) { throw 'pg_restore falló' }

$zip = Join-Path $From 'storage.zip'
if (-not $SkipStorage -and (Test-Path $zip)) {
    $storageDir = if ($cfg.STORAGE_DIR) { $cfg.STORAGE_DIR } else { 'storage' }
    if (-not [IO.Path]::IsPathRooted($storageDir)) { $storageDir = Join-Path $script:RepoRoot $storageDir }
    # Los archivos tienen nombre único y nunca cambian: extraer encima es seguro.
    Expand-Archive -Path $zip -DestinationPath $storageDir -Force
    "Archivos restaurados en $storageDir"
}
$counts = & $script:Psql -U $cfg.APP_DB_USER -h $cfg.POSTGRES_HOST -p $cfg.POSTGRES_PORT -d $Database -tA -F ' / ' -c `
    "select (select count(*) from cases_8d), (select count(*) from documents), (select count(*) from audit_events), (select filename from schema_migrations order by 1 desc limit 1)"
"Restaurado en $Database (casos / documentos / eventos / última migración): $counts"
