# Crea el rol y la base de datos de la demo. Idempotente: se puede ejecutar varias veces.
# Uso: powershell -File scripts/setup-db.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib.ps1')

$cfg = Read-DotEnv
if (-not $cfg.ContainsKey('APP_DB_PASSWORD') -or -not $cfg.APP_DB_PASSWORD) {
    $appPassword = New-RandomSecret
    Add-Content -Path $script:EnvFile -Encoding utf8 -Value @(
        'APP_DB_NAME=d8_demo',
        'APP_DB_USER=d8_app',
        "APP_DB_PASSWORD=$appPassword",
        "DATABASE_URL=postgresql://d8_app:$appPassword@$($cfg.POSTGRES_HOST):$($cfg.POSTGRES_PORT)/d8_demo"
    )
    $cfg = Read-DotEnv
}

$db = $cfg.APP_DB_NAME
$user = $cfg.APP_DB_USER
$env:PGPASSWORD = $cfg.POSTGRES_SUPERPASSWORD
$superArgs = @('-U', $cfg.POSTGRES_SUPERUSER, '-h', $cfg.POSTGRES_HOST, '-p', $cfg.POSTGRES_PORT, '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-tA')

function Invoke-SuperSql([string]$sql) {
    $result = & $script:Psql @superArgs -c $sql
    if ($LASTEXITCODE -ne 0) { throw "psql falló: $sql" }
    $result
}

if ((Invoke-SuperSql "select 1 from pg_roles where rolname = '$user'") -ne '1') {
    # CREATEDB: las pruebas de integración crean y borran su propia BD temporal sin usar el superusuario.
    Invoke-SuperSql "create role $user login createdb password '$($cfg.APP_DB_PASSWORD)'" | Out-Null
    "Rol $user creado"
} else {
    "Rol $user ya existe"
}

if ((Invoke-SuperSql "select 1 from pg_database where datname = '$db'") -ne '1') {
    Invoke-SuperSql "create database $db owner $user encoding 'UTF8'" | Out-Null
    "Base de datos $db creada"
} else {
    "Base de datos $db ya existe"
}
