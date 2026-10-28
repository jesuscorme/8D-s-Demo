# Utilidades compartidas por los scripts de la demo.

$script:RepoRoot = Split-Path $PSScriptRoot -Parent
$script:EnvFile = Join-Path $script:RepoRoot '.env'
$script:Psql = 'C:\Program Files\PostgreSQL\16\bin\psql.exe'

function Read-DotEnv {
    $values = @{}
    if (-not (Test-Path $script:EnvFile)) { throw "No existe $script:EnvFile. Copia .env.example a .env." }
    Get-Content $script:EnvFile | Where-Object { $_ -match '^\s*[A-Za-z_][A-Za-z0-9_]*\s*=' } | ForEach-Object {
        $key, $value = $_ -split '=', 2
        $values[$key.Trim()] = $value.Trim()
    }
    $values
}

function New-RandomSecret {
    $chars = (48..57) + (65..90) + (97..122)
    -join ($chars | Get-Random -Count 24 | ForEach-Object { [char]$_ })
}
