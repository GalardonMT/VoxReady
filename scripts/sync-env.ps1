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

# 4. Parametros de Tenant y Auth (Microsoft Entra External ID - CIAM)
$CIAM_TENANT_ID = "7f50eae1-4ea8-45eb-9ff7-02f82b2781a5"
$CIAM_SPA_CLIENT_ID = "e219fd4b-3686-45dd-9656-b582d1fb0698"
$CIAM_API_CLIENT_ID = "5dd1bf8d-c0de-4f67-8131-df42e93dcf29"
$CIAM_AUTHORITY = "https://voxreadydev.ciamlogin.com/$CIAM_TENANT_ID"
$CIAM_API_SCOPE = "api://$CIAM_API_CLIENT_ID/access_as_user"

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
DEV_AUTH_SECRET="cambia-este-secreto-dev"
DEV_TOKEN_TTL_HOURS=8
CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"
JWKS_URL="https://voxreadydev.ciamlogin.com/$CIAM_TENANT_ID/discovery/v2.0/keys"
JWT_ISSUER="https://voxreadydev.ciamlogin.com/$CIAM_TENANT_ID/v2.0"
JWT_AUDIENCE="$CIAM_SPA_CLIENT_ID"
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
NEXT_PUBLIC_AUTH_MODE="azure"
NEXT_PUBLIC_AZURE_CLIENT_ID="$CIAM_SPA_CLIENT_ID"
NEXT_PUBLIC_AZURE_TENANT_ID="$CIAM_TENANT_ID"
NEXT_PUBLIC_AZURE_AUTHORITY="$CIAM_AUTHORITY"
NEXT_PUBLIC_AZURE_REDIRECT_URI="http://localhost:3000"
NEXT_PUBLIC_AZURE_API_SCOPE="$CIAM_API_SCOPE"
NEXT_PUBLIC_DEV_AUTH="true"
"@

foreach ($dir in $frontendDirs) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [System.IO.File]::WriteAllText((Join-Path $dir ".env.local"), $frontendContent, [System.Text.Encoding]::UTF8)
    Write-Host "[OK] $dir/.env.local generado exitosamente."
}

Write-Host "==> [4/4] Sincronizacion completada."
