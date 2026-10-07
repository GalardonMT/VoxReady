param(
    [ValidateSet('up', 'build', 'verify', 'test', 'seed', 'logs', 'stop')]
    [string]$Action = 'up'
)

$ErrorActionPreference = 'Stop'

function Invoke-Docker {
    param([string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker falló (código $LASTEXITCODE). Revisa el mensaje anterior."
    }
}

Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Instala Docker Desktop y abre su motor Linux.'
    }
    if (-not (Test-Path -LiteralPath '.env')) {
        throw 'Configura .env en la raíz siguiendo .env.example antes de ejecutar Docker.'
    }
    Invoke-Docker -Arguments @('compose', 'config', '--quiet')
    switch ($Action) {
        'up' {
            Invoke-Docker -Arguments @('compose', 'up', '--build', '--detach', '--wait', '--wait-timeout', '240')
            Invoke-Docker -Arguments @('compose', 'ps')
        }
        'build' { Invoke-Docker -Arguments @('compose', 'build', 'api', 'client') }
        'verify' {
            Invoke-Docker -Arguments @('compose', 'run', '--rm', '--no-deps', 'init', 'python', 'scripts/prepare_azure_database.py', '--verify-only')
        }
        'test' {
            Invoke-Docker -Arguments @('compose', '--profile', 'test', 'build', 'test-api', 'test-client')
            Invoke-Docker -Arguments @('compose', 'run', '--rm', '--no-deps', 'init', 'python', 'scripts/prepare_azure_database.py', '--verify-only')
            Invoke-Docker -Arguments @('compose', '--profile', 'test', 'run', '--rm', '--no-deps', 'test-api')
            Invoke-Docker -Arguments @('compose', '--profile', 'test', 'run', '--rm', '--no-deps', 'test-client')
        }
        'seed' {
            Invoke-Docker -Arguments @('compose', 'run', '--rm', '--no-deps', 'init', 'python', 'scripts/prepare_azure_database.py', '--verify-only')
            Invoke-Docker -Arguments @('compose', 'run', '--rm', '--no-deps', 'init', 'python', 'scripts/seed_master_topics.py')
        }
        'logs' { Invoke-Docker -Arguments @('compose', 'logs', '--follow', '--tail', '100', 'api', 'client') }
        'stop' { Invoke-Docker -Arguments @('compose', 'stop') }
    }
}
finally {
    Pop-Location
}
