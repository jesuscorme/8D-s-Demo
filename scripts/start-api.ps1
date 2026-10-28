# Arranca la API de 8D PRO en primer plano (Ctrl+C para parar). Lee DATABASE_URL de .env.
# Uso: powershell -File scripts/start-api.ps1 [-Port 8000]
param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$api = Join-Path (Split-Path $PSScriptRoot -Parent) 'apps\api'
Push-Location $api
try { & (Join-Path $api '.venv\Scripts\python.exe') -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $Port }
finally { Pop-Location }
