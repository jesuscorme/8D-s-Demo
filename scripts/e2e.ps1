# Recorrido E2E en Edge (Playwright) sobre una BD y un almacenamiento temporales; no toca d8_demo.
# Requisitos: npm run build en apps\web. Uso: powershell -File scripts/e2e.ps1 [-ApiPort 8020] [-WebPort 3020]
param([int]$ApiPort = 8020, [int]$WebPort = 3020)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib.ps1')
$cfg = Read-DotEnv
$db = "$($cfg.APP_DB_NAME)_e2e"
$api = Join-Path $script:RepoRoot 'apps\api'
$web = Join-Path $script:RepoRoot 'apps\web'
$storage = Join-Path ([IO.Path]::GetTempPath()) "d8_e2e_storage_$PID"
$password = New-RandomSecret
$env:PGPASSWORD = $cfg.APP_DB_PASSWORD
$env:PGOPTIONS = '-c client_min_messages=warning'
$admin = @('-U', $cfg.APP_DB_USER, '-h', $cfg.POSTGRES_HOST, '-p', $cfg.POSTGRES_PORT, '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-q', '-tA')
$procs = @()
try {
    & $script:Psql @admin -c "drop database if exists $db with (force)" | Out-Null
    & $script:Psql @admin -c "create database $db encoding 'UTF8'" | Out-Null
    & (Join-Path $PSScriptRoot 'migrate.ps1') -Database $db | Out-Null
    $env:DATABASE_URL = "postgresql://$($cfg.APP_DB_USER):$($cfg.APP_DB_PASSWORD)@$($cfg.POSTGRES_HOST):$($cfg.POSTGRES_PORT)/$db"
    $env:DEMO_PASSWORD = $password
    $env:STORAGE_DIR = $storage
    $env:APP_BASE_URL = "http://127.0.0.1:$WebPort"
    Push-Location $api
    try { & .\.venv\Scripts\python.exe -m app.seed | Out-Null } finally { Pop-Location }

    $procs += Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory $api -FilePath (Join-Path $api '.venv\Scripts\python.exe') `
        -ArgumentList '-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1', '--port', $ApiPort
    $env:API_URL = "http://127.0.0.1:$ApiPort"
    $env:NEXT_TELEMETRY_DISABLED = '1'
    $procs += Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory $web -FilePath 'cmd.exe' `
        -ArgumentList '/c', 'npx', 'next', 'start', '-p', $WebPort
    $ready = $false
    for ($i = 0; $i -lt 60 -and -not $ready; $i++) {
        try { $ready = (Invoke-RestMethod "http://127.0.0.1:$WebPort/api/health" -TimeoutSec 2).status -eq 'ok' } catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ready) { throw 'La aplicación no arrancó para el E2E' }

    $env:E2E_BASE_URL = "http://127.0.0.1:$WebPort"
    $env:E2E_PASSWORD = $password
    Push-Location $web
    try { npx playwright test; $code = $LASTEXITCODE } finally { Pop-Location }
    if ($code -ne 0) { throw "E2E falló (código $code)" }
    'E2E correcto'
}
finally {
    foreach ($p in $procs) { if ($p -and -not $p.HasExited) { & taskkill /PID $p.Id /T /F 2>$null | Out-Null } }
    $env:PGPASSWORD = $cfg.APP_DB_PASSWORD
    & $script:Psql @admin -c "drop database if exists $db with (force)" 2>$null | Out-Null
    if (Test-Path $storage) { Remove-Item -Recurse -Force $storage }
}
