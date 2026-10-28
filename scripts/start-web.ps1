# Arranca la interfaz compilada (npm run build previo) apuntando a la API. Ctrl+C para parar.
# Uso: powershell -File scripts/start-web.ps1 [-Port 3010] [-ApiPort 8010]
# Por defecto 3010/8010 para no chocar con otras demos locales en 3000/8000.
param([int]$Port = 3010, [int]$ApiPort = 8010)
$ErrorActionPreference = 'Stop'
$web = Join-Path (Split-Path $PSScriptRoot -Parent) 'apps\web'
if (-not (Test-Path (Join-Path $web '.next\BUILD_ID'))) { throw 'Falta la compilación: ejecuta npm run build en apps\web' }
$env:API_URL = "http://127.0.0.1:$ApiPort"
$env:NEXT_TELEMETRY_DISABLED = '1'
Push-Location $web
try { npx next start -p $Port }
finally { Pop-Location }
