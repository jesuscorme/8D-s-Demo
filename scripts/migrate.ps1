# Aplica db/migrations/NNNN_*.sql en orden. Idempotente: registra cada archivo en
# schema_migrations con su SHA-256 y se niega a continuar si uno aplicado cambió.
# Uso: powershell -File scripts/migrate.ps1 [-Database <nombre>]
param([string]$Database)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib.ps1')

$cfg = Read-DotEnv
if (-not $Database) { $Database = $cfg.APP_DB_NAME }
$env:PGPASSWORD = $cfg.APP_DB_PASSWORD
$env:PGCLIENTENCODING = 'UTF8'
$env:PGOPTIONS = '-c client_min_messages=warning'
$dbArgs = @('-U', $cfg.APP_DB_USER, '-h', $cfg.POSTGRES_HOST, '-p', $cfg.POSTGRES_PORT, '-d', $Database, '-v', 'ON_ERROR_STOP=1', '-q', '-tA')

function Invoke-DbSql([string[]]$extra) {
    $result = & $script:Psql @dbArgs @extra
    if ($LASTEXITCODE -ne 0) { throw "psql falló en $Database ($($extra -join ' '))" }
    $result
}

Invoke-DbSql @('-c', @'
create table if not exists schema_migrations (
    filename   text primary key check (filename ~ '^\d{4}_[a-z0-9_]+\.sql$'),
    sha256     text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    applied_at timestamptz not null default now()
)
'@) | Out-Null

$applied = @{}
Invoke-DbSql @('-F', '|', '-c', 'select filename, sha256 from schema_migrations') | Where-Object { $_ } | ForEach-Object {
    $name, $hash = $_ -split '\|', 2
    $applied[$name] = $hash
}

$dir = Join-Path $script:RepoRoot 'db\migrations'
$files = Get-ChildItem $dir -Filter '*.sql' | Where-Object { $_.Name -match '^\d{4}_[a-z0-9_]+\.sql$' } | Sort-Object Name
$count = 0
foreach ($file in $files) {
    # SHA-256 con finales de línea normalizados a LF: el checkout de Git no cambia la suma.
    $bytes = [IO.File]::ReadAllBytes($file.FullName)
    $text = [Text.Encoding]::UTF8.GetString($bytes) -replace "`r`n", "`n"
    $sha = [Security.Cryptography.SHA256]::Create()
    $hash = -join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text)) | ForEach-Object { $_.ToString('x2') })
    if ($applied.ContainsKey($file.Name)) {
        if ($applied[$file.Name] -ne $hash) {
            throw "La migración ya aplicada $($file.Name) cambió en disco. No se editan migraciones aplicadas: crea una nueva."
        }
        continue
    }
    # Archivo e inserción en una sola transacción: o se aplica entero o no se registra.
    Invoke-DbSql @('-1', '-f', $file.FullName, '-c', "insert into schema_migrations (filename, sha256) values ('$($file.Name)', '$hash')") | Out-Null
    "Aplicada $($file.Name)"
    $count++
}
"$count migración(es) aplicada(s) en $Database; $($files.Count) en total"
