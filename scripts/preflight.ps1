param(
    [switch]$RunTests
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $root '.env'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker no está instalado o no está disponible en PATH.'
}
docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'El motor Linux de Docker no está disponible.'
}
if (-not (Test-Path -LiteralPath $envPath)) {
    throw 'Falta .env. Copia .env.example y configura el ambiente.'
}

$required = @(
    'NEXT_PUBLIC_AZURE_TENANT_ID', 'NEXT_PUBLIC_AZURE_CLIENT_ID',
    'NEXT_PUBLIC_AZURE_AUTHORITY', 'NEXT_PUBLIC_AZURE_API_SCOPE',
    'VOXREADY_DOCKER_API_URL', 'VOXREADY_DOCKER_REDIRECT_URI',
    'SQL_CONNECTION_STRING', 'CORS_ORIGINS', 'JWKS_URL', 'JWT_ISSUER',
    'JWT_AUDIENCE', 'STORAGE_CONNECTION_STRING', 'STORAGE_CONTAINER_NAME',
    'STORAGE_RECORDING_PREFIX', 'STORAGE_MICROLESSON_PREFIX',
    'STORAGE_REPORT_CONTAINER_NAME', 'WORKER_INTERNAL_URL',
    'INTERNAL_SERVICE_TOKEN', 'VISION_SERVICE_URL', 'VISION_SERVICE_TOKEN',
    'NVIDIA_API_KEY', 'NVIDIA_BASE_URL', 'LLM_MODEL_NAME',
    'NVIDIA_RIVA_SERVER', 'NVIDIA_FUNCTION_ID', 'NVIDIA_LANGUAGE_CODE',
    'MAX_UPLOAD_SIZE_BYTES', 'MICROLESSON_VIDEO_MAX_BYTES',
    'UPLOAD_URL_TTL_MINUTES', 'READ_URL_TTL_MINUTES',
    'VISION_MAX_FRAME_BYTES', 'VISION_MAX_BATCH_FRAMES'
)

$configured = @{}
foreach ($line in Get-Content -LiteralPath $envPath) {
    if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
    $name, $value = $line -split '=', 2
    $configured[$name.Trim()] = $value.Trim().Trim('"').Trim("'")
}

$invalid = @()
foreach ($name in $required) {
    $value = $configured[$name]
    if ([string]::IsNullOrWhiteSpace($value) -or
        $value -match 'your-|replace-with|example\.invalid|<[^>]+>') {
        $invalid += $name
    }
}
if ($invalid.Count -gt 0) {
    throw ('Faltan valores reales para: ' + ($invalid -join ', '))
}

Push-Location -LiteralPath $root
try {
    docker compose -f docker-compose.azure.yml config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'La configuración Docker Compose no es válida.' }
    Write-Host 'Preflight correcto: configuración y Docker Compose válidos.' -ForegroundColor Green
    if ($RunTests) {
        & (Join-Path $root 'docker.ps1') test
    }
}
finally {
    Pop-Location
}
