<#
.SYNOPSIS
    Script interactivo y modular para compilar, subir y desplegar contenedores en Azure Container Apps.

.DESCRIPTION
    Automatiza el flujo completo:
    1. Verifica que el daemon de Docker esté activo.
    2. Autentica en Azure Container Registry (crvoxreadyst.azurecr.io).
    3. Compila la imagen Docker con el tag especificado (o auto-incrementado).
    4. Sube la imagen a Azure Container Registry (ACR).
    5. Actualiza la Container App en Azure (rg-voxready-dev).
    6. Muestra el estado final de la revisión.

.EXAMPLE
    .\deploy-azure.ps1 worker
    .\deploy-azure.ps1 backend
    .\deploy-azure.ps1 vision
    .\deploy-azure.ps1 all
    .\deploy-azure.ps1 worker -Tag v2.16
#>

param (
    [Parameter(Position = 0)]
    [ValidateSet("worker", "backend", "vision", "all", "menu", "status")]
    [string]$Service = "menu",

    [Parameter(Position = 1)]
    [string]$Tag = ""
)

$ErrorActionPreference = "Stop"

$ACR_NAME = "crvoxreadyst"
$ACR_REGISTRY = "$ACR_NAME.azurecr.io"
$RESOURCE_GROUP = "rg-voxready-dev"

$CONFIG = @{
    worker = @{
        Name       = "Worker de Análisis"
        Folder     = "worker"
        Target     = "runtime"
        Repo       = "analysis-worker"
        App        = "ca-analysis-worker"
        Prefix     = "v2."
    }
    backend = @{
        Name       = "Backend API"
        Folder     = "backend"
        Target     = "runtime"
        Repo       = "backend-api"
        App        = "ca-backend-api"
        Prefix     = "v"
    }
    vision = @{
        Name       = "Servicio de Visión"
        Folder     = "voxready-vision"
        Target     = ""
        Repo       = "vision-service"
        App        = "ca-vision-service"
        Prefix     = "v"
    }
}

function Show-Header {
    Clear-Host
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "          VOXREADY - DESPLIEGUE A AZURE CONTAINER APPS    " -ForegroundColor Yellow
    Write-Host "==========================================================" -ForegroundColor Cyan
}

function Ensure-Docker {
    Write-Host "`n[1/5] Verificando Docker daemon..." -ForegroundColor Cyan
    try {
        $null = docker ps 2>&1
        Write-Host "  Docker está activo y respondiendo." -ForegroundColor Green
    }
    catch {
        Write-Host "  Docker no responde. Intentando iniciar Docker Desktop..." -ForegroundColor Yellow
        $dockerPath = "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
        if (Test-Path $dockerPath) {
            Start-Process $dockerPath
        } else {
            Start-Process "Docker Desktop" -ErrorAction SilentlyContinue
        }

        $retries = 30
        while ($retries -gt 0) {
            Start-Sleep -Seconds 2
            try {
                $null = docker ps 2>&1
                Write-Host "  Docker daemon iniciado correctamente." -ForegroundColor Green
                return
            } catch {
                $retries--
                Write-Host "  Esperando a que Docker inicie... ($retries intentos restantes)" -ForegroundColor Gray
            }
        }
        throw "No se pudo conectar a Docker. Asegúrate de que Docker Desktop esté abierto."
    }
}

function Ensure-AcrLogin {
    Write-Host "`n[2/5] Autenticando en Azure Container Registry ($ACR_REGISTRY)..." -ForegroundColor Cyan
    az acr login -n $ACR_NAME
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo al autenticar en ACR. Verifica que hayas iniciado sesión con 'az login'."
    }
    Write-Host "  Login en ACR exitoso." -ForegroundColor Green
}

function Get-NextTag([string]$serviceKey) {
    $cfg = $CONFIG[$serviceKey]
    try {
        $currentImage = az containerapp show -n $cfg.App -g $RESOURCE_GROUP --query "properties.template.containers[0].image" -o tsv 2>$null
        if ($currentImage -and $currentImage -match ":(v[\d\.]+)$") {
            $currTag = $matches[1]
            if ($currTag -match "^v(\d+)$") {
                $num = [int]$matches[1] + 1
                return "v$num"
            } elseif ($currTag -match "^v(\d+)\.(\d+)$") {
                $maj = $matches[1]
                $min = [int]$matches[2] + 1
                return "v$maj.$min"
            }
        }
    } catch {
        # Si falla consulta de Azure, proponer por defecto
    }

    if ($serviceKey -eq "worker") { return "v2.16" }
    if ($serviceKey -eq "backend") { return "v18" }
    if ($serviceKey -eq "vision") { return "v2.2" }
    return "v1"
}

function Deploy-Service([string]$serviceKey, [string]$customTag) {
    $cfg = $CONFIG[$serviceKey]
    $svcName = $cfg.Name
    $app = $cfg.App
    $repo = $cfg.Repo
    $folder = Join-Path $PSScriptRoot $cfg.Folder

    if (-not (Test-Path $folder)) {
        throw "No se encuentra el directorio '$folder'."
    }

    $finalTag = $customTag
    if (-not $finalTag) {
        $suggestedTag = Get-NextTag $serviceKey
        Write-Host "`nTag sugerido para ${svcName}: " -NoNewline -ForegroundColor Yellow
        Write-Host "$suggestedTag" -ForegroundColor Cyan
        $inputTag = Read-Host "Presione Enter para aceptar [$suggestedTag] o ingrese un tag personalizado"
        $finalTag = if ($inputTag.Trim()) { $inputTag.Trim() } else { $suggestedTag }
    }

    $imageTag = "$ACR_REGISTRY/${repo}:${finalTag}"
    $imageLatest = "$ACR_REGISTRY/${repo}:latest"

    Write-Host "`n----------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "Desplegando: $svcName" -ForegroundColor Yellow
    Write-Host "Imagen:      $imageTag" -ForegroundColor Cyan
    Write-Host "App destino: $app ($RESOURCE_GROUP)" -ForegroundColor Cyan
    Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray

    # 3. Docker build
    Write-Host "`n[3/5] Compilando imagen Docker..." -ForegroundColor Cyan
    $buildArgs = @("build")
    if ($cfg.Target) {
        $buildArgs += @("--target", $cfg.Target)
    }
    $buildArgs += @("-t", $imageTag, "-t", $imageLatest, $folder)

    & docker @buildArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Error al compilar la imagen Docker para $svcName."
    }
    Write-Host "  Compilación exitosa." -ForegroundColor Green

    # 4. Docker push
    Write-Host "`n[4/5] Subiendo imagen a Azure Container Registry ($ACR_NAME)..." -ForegroundColor Cyan
    & docker push $imageTag
    if ($LASTEXITCODE -ne 0) {
        throw "Error al hacer push de $imageTag."
    }
    & docker push $imageLatest
    Write-Host "  Push a ACR completado." -ForegroundColor Green

    # 5. Azure Container App update
    Write-Host "`n[5/5] Actualizando Azure Container App ($app)..." -ForegroundColor Cyan
    az containerapp update -n $app -g $RESOURCE_GROUP --image $imageTag
    if ($LASTEXITCODE -ne 0) {
        throw "Error al actualizar la Container App $app."
    }

    Write-Host "`nDespliegue de $svcName completado con éxito." -ForegroundColor Green
}

function Show-Status {
    Write-Host "`nEstado actual de Container Apps en ${RESOURCE_GROUP}:`n" -ForegroundColor Cyan
    az containerapp list -g $RESOURCE_GROUP --query "[].{Name: name, Image: properties.template.containers[0].image, Status: properties.runningStatus, Provisioning: properties.provisioningState}" -o table
}

# --- EJECUCIÓN PRINCIPAL ---

if ($Service -eq "menu") {
    Show-Header
    Write-Host " Seleccione el servicio que desea compilar y desplegar:`n"
    Write-Host " 1. Worker de Análisis   (ca-analysis-worker)" -ForegroundColor Magenta
    Write-Host " 2. Backend API          (ca-backend-api)" -ForegroundColor Blue
    Write-Host " 3. Servicio de Visión   (ca-vision-service)" -ForegroundColor DarkYellow
    Write-Host " 4. Todos los servicios  (Worker + Backend + Visión)" -ForegroundColor Green
    Write-Host " 5. Ver estado actual de Container Apps en Azure" -ForegroundColor Cyan
    Write-Host " 6. Salir" -ForegroundColor Gray
    Write-Host "==========================================================" -ForegroundColor Cyan
    $opt = Read-Host "Seleccione una opción [1-6]"

    switch ($opt) {
        "1" { $Service = "worker" }
        "2" { $Service = "backend" }
        "3" { $Service = "vision" }
        "4" { $Service = "all" }
        "5" { Show-Status; exit 0 }
        default { exit 0 }
    }
}

if ($Service -eq "status") {
    Show-Status
    exit 0
}

Ensure-Docker
Ensure-AcrLogin

if ($Service -eq "all") {
    Deploy-Service "worker" $Tag
    Deploy-Service "backend" $Tag
    Deploy-Service "vision" $Tag
} else {
    Deploy-Service $Service $Tag
}

Show-Status
Write-Host "`n¡Proceso finalizado exitosamente!`n" -ForegroundColor Green
