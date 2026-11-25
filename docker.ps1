param(
    [ValidateSet('up', 'start', 'build', 'verify', 'test', 'seed', 'logs', 'stop')]
    [string]$Action = 'up',
    [switch]$LocalDevAuth,
    [string]$EnvFile = '.env'
)

$ErrorActionPreference = 'Stop'

function Invoke-Docker {
    param([string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker falló (código $LASTEXITCODE). Revisa el mensaje anterior."
    }
}

function Invoke-Compose {
    param([string[]]$Arguments)
    Invoke-Docker -Arguments ($script:ComposeFiles + $Arguments)
}

Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Instala Docker Desktop y abre su motor Linux.'
    }
    if (-not (Test-Path -LiteralPath $EnvFile)) {
        throw "Configura $EnvFile siguiendo una plantilla .env.*.example antes de ejecutar Docker."
    }
    $ComposeFiles = @('compose', '--env-file', $EnvFile, '-f', 'docker-compose.azure.yml')
    if ($LocalDevAuth) {
        throw 'Este flujo usa exclusivamente Microsoft Entra. No uses -LocalDevAuth para los accesos de clientes y voceros.'
    }
    Invoke-Compose -Arguments @('config', '--quiet')
    switch ($Action) {
        'up' {
            Invoke-Compose -Arguments @('up', '--build', '--no-deps', '--detach', '--wait', '--wait-timeout', '240', 'api', 'client')
            Invoke-Compose -Arguments @('ps')
        }
        'start' {
            # Arranca los mismos contenedores, sin construir ni recrear.
            Invoke-Compose -Arguments @('start', '--wait', '--wait-timeout', '240', 'api', 'client')
            Invoke-Compose -Arguments @('ps')
        }
        'build' { Invoke-Compose -Arguments @('build', 'api', 'client') }
        'verify' {
            Invoke-Compose -Arguments @('exec', '-T', 'api', 'python', 'scripts/verify_access_runtime.py')
        }
        'test' {
            Invoke-Compose -Arguments @('--profile', 'test', 'build', 'test-api', 'test-client', 'test-worker')
            Invoke-Compose -Arguments @('run', '--rm', '--no-deps', 'init', 'python', 'scripts/prepare_azure_database.py', '--verify-only')
            Invoke-Compose -Arguments @('--profile', 'test', 'run', '--rm', '--no-deps', 'test-api')
            Invoke-Compose -Arguments @('--profile', 'test', 'run', '--rm', '--no-deps', 'test-client')
            Invoke-Compose -Arguments @('--profile', 'test', 'run', '--rm', '--no-deps', 'test-worker')
        }
        'seed' {
            Invoke-Compose -Arguments @('run', '--rm', '--no-deps', 'init', 'python', 'scripts/prepare_azure_database.py', '--verify-only')
            Invoke-Compose -Arguments @('run', '--rm', '--no-deps', 'init', 'python', 'scripts/seed_master_topics.py')
            Invoke-Compose -Arguments @('run', '--rm', '--no-deps', 'init', 'python', 'scripts/seed_dev_users.py')
        }
        'logs' { Invoke-Compose -Arguments @('logs', '--follow', '--tail', '100', 'api', 'client') }
        'stop' { Invoke-Compose -Arguments @('stop', 'client', 'api') }
    }
}
finally {
    Pop-Location
}
