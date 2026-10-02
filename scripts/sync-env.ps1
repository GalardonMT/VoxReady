$ErrorActionPreference = "Stop"

Write-Host "==> [1/4] Verificando contexto de suscripcion..."
$CURRENT_SUB = az account show --query "name" -o tsv
Write-Host "Suscripcion activa: $CURRENT_SUB"

$RG_NAME = "rg-voxready-dev"
$KV_NAME = "kv-voxready-st"
$STORAGE_NAME = "stavoxreadyst"
$SB_NAME = "sb-voxready-st"

Write-Host "==> [2/4] Consultando Azure CLI y Azure Key Vault..."

Write-Host "Consultando conexion a Storage..."
$STORAGE_CONN = (az storage account show-connection-string --name $STORAGE_NAME --resource-group $RG_NAME --query "connectionString" -o tsv).Trim()

Write-Host "Consultando conexion a Service Bus..."
$SB_CONN = (az servicebus namespace authorization-rule keys list --resource-group $RG_NAME --namespace-name $SB_NAME --name RootManageSharedAccessKey --query "primaryConnectionString" -o tsv).Trim()

Write-Host "Consultando conexion a Azure SQL desde Key Vault..."
$SQL_CONN = (az keyvault secret show --vault-name $KV_NAME --name "SQL-CONNECTION-STRING" --query "value" -o tsv).Trim()

Write-Host "Consultando NVIDIA API Key desde Key Vault..."
$NVIDIA_KEY = (az keyvault secret show --vault-name $KV_NAME --name "NVIDIA-API-KEY" --query "value" -o tsv).Trim()

Write-Host "Consultando FQDN de ca-vision-service..."
$VISION_FQDN = (az containerapp show --name ca-vision-service --resource-group $RG_NAME --query "properties.configuration.ingress.fqdn" -o tsv).Trim()

Write-Host "Consultando FQDN de ca-backend-api..."
$BACKEND_FQDN = (az containerapp show --name ca-backend-api --resource-group $RG_NAME --query "properties.configuration.ingress.fqdn" -o tsv).Trim()

$TENANT_ID = (az account show --query "tenantId" -o tsv).Trim()

$CLIENT_APP_ID = ""
try {
    $CLIENT_APP_ID = (az ad app list --display-name "voxready" --query "[0].appId" -o tsv 2>$null).Trim()
} catch {}

if (-not $CLIENT_APP_ID) {
    try {
        $CLIENT_APP_ID = (az keyvault secret show --vault-name $KV_NAME --name "ENTRA-CLIENT-ID" --query "value" -o tsv 2>$null).Trim()
    } catch {}
}
if (-not $CLIENT_APP_ID) {
    $CLIENT_APP_ID = "5dd1bf8d-c0de-4f67-8131-df42e93dcf29"
}

Write-Host "==> [3/4] Generando archivos .env..."

# -------------------------------------------------------------
# A. Backend (.env)
# -------------------------------------------------------------
$backendDirs = @("voxready-backend", "backend")
$backendContent = @"
# Generado automaticamente por CLI Sync
SQL_CONNECTION_STRING="$SQL_CONN"
STORAGE_CONNECTION_STRING="$STORAGE_CONN"
STORAGE_CONTAINER_NAME="recordings"
SERVICE_BUS_CONNECTION_STRING="$SB_CONN"
SERVICE_BUS_QUEUE_NAME="analysis-queue"
DEV_AUTH=true
"@

foreach ($dir in $backendDirs) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [System.IO.File]::WriteAllText((Join-Path $dir ".env"), $backendContent, [System.Text.Encoding]::UTF8)
    Write-Host "[OK] $dir/.env generado exitosamente."
}

# -------------------------------------------------------------
# B. Worker (.env)
# -------------------------------------------------------------
$workerDirs = @("voxready-worker", "worker")
$workerContent = @"
# Generado automaticamente por CLI Sync
SQL_CONNECTION_STRING="$SQL_CONN"
STORAGE_CONNECTION_STRING="$STORAGE_CONN"
STORAGE_CONTAINER_NAME="recordings"
SERVICE_BUS_CONNECTION_STRING="$SB_CONN"
SERVICE_BUS_QUEUE_NAME="analysis-queue"

# Pipeline de Vision y Modelos Externos
VISION_SERVICE_URL="https://$VISION_FQDN"
NVIDIA_API_KEY="$NVIDIA_KEY"
NVIDIA_BASE_URL="https://integrate.api.nvidia.com/v1"
LLM_MODEL_NAME="meta/llama-3.2-11b-vision-instruct"
LLM_TIMEOUT="120.0"
"@

foreach ($dir in $workerDirs) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [System.IO.File]::WriteAllText((Join-Path $dir ".env"), $workerContent, [System.Text.Encoding]::UTF8)
    Write-Host "[OK] $dir/.env generado exitosamente."
}

# -------------------------------------------------------------
# C. Frontend (.env.local)
# -------------------------------------------------------------
$frontendDirs = @("voxready-frontend", "frontend")
$frontendContent = @"
# Generado automaticamente por CLI Sync
NEXT_PUBLIC_API_URL="https://$BACKEND_FQDN/v1"
NEXT_PUBLIC_AZURE_CLIENT_ID="$CLIENT_APP_ID"
NEXT_PUBLIC_AZURE_TENANT_ID="$TENANT_ID"
NEXT_PUBLIC_REDIRECT_URI="http://localhost:3000"
NEXT_PUBLIC_DEV_AUTH="true"
"@

foreach ($dir in $frontendDirs) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [System.IO.File]::WriteAllText((Join-Path $dir ".env.local"), $frontendContent, [System.Text.Encoding]::UTF8)
    Write-Host "[OK] $dir/.env.local generado exitosamente."
}

Write-Host "==> [4/4] Sincronizacion completada."
