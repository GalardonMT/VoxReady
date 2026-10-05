#!/usr/bin/env bash
set -euo pipefail

echo "==> [1/4] Verificando contexto de suscripción..."
CURRENT_SUB=$(az account show --query "name" -o tsv)
echo "Suscripción activa: $CURRENT_SUB"

RG_NAME="rg-voxready-dev"
KV_NAME="kv-voxready-st"
STORAGE_NAME="stavoxreadyst"
SB_NAME="sb-voxready-st"

echo "==> [2/4] Consultando Azure CLI y Azure Key Vault..."

# 1. Cadenas de conexión compartidas
echo "Consultando conexión a Storage..."
STORAGE_CONN=$(az storage account show-connection-string \
  --name "$STORAGE_NAME" \
  --resource-group "$RG_NAME" \
  --query "connectionString" -o tsv)

echo "Consultando conexión a Service Bus..."
SB_CONN=$(az servicebus namespace authorization-rule keys list \
  --resource-group "$RG_NAME" \
  --namespace-name "$SB_NAME" \
  --name RootManageSharedAccessKey \
  --query "primaryConnectionString" -o tsv)

echo "Consultando conexión a Azure SQL desde Key Vault..."
SQL_CONN=$(az keyvault secret show \
  --vault-name "$KV_NAME" \
  --name "SQL-CONNECTION-STRING" \
  --query "value" -o tsv || echo "")

# 2. Secretos y credenciales de IA
echo "Consultando NVIDIA API Key desde Key Vault..."
NVIDIA_KEY=$(az keyvault secret show \
  --vault-name "$KV_NAME" \
  --name "NVIDIA-API-KEY" \
  --query "value" -o tsv || echo "")

# 3. FQDNs de Azure Container Apps
echo "Consultando FQDN de ca-vision-service..."
VISION_FQDN=$(az containerapp show \
  --name ca-vision-service \
  --resource-group "$RG_NAME" \
  --query "properties.configuration.ingress.fqdn" -o tsv || echo "")

echo "Consultando FQDN de ca-backend-api..."
BACKEND_FQDN=$(az containerapp show \
  --name ca-backend-api \
  --resource-group "$RG_NAME" \
  --query "properties.configuration.ingress.fqdn" -o tsv || echo "")

# 4. Parámetros de Tenant y Auth
TENANT_ID=$(az account show --query "tenantId" -o tsv)

# Intentar extraer Client ID de Entra ID registrado para VoxReady (o consultar Key Vault)
CLIENT_APP_ID=$(az ad app list --display-name "voxready" --query "[0].appId" -o tsv 2>/dev/null || echo "")
if [ -z "$CLIENT_APP_ID" ]; then
  CLIENT_APP_ID=$(az keyvault secret show --vault-name "$KV_NAME" --name "ENTRA-CLIENT-ID" --query "value" -o tsv 2>/dev/null || echo "5dd1bf8d-c0de-4f67-8131-df42e93dcf29")
fi

echo "==> [3/4] Generando archivos .env..."

# -------------------------------------------------------------
# A. voxready-backend/.env y backend/.env
# -------------------------------------------------------------
for dir in "voxready-backend" "backend"; do
  mkdir -p "$dir"
  cat <<EOF > "$dir/.env"
# Generado automáticamente por CLI Sync
SQL_CONNECTION_STRING="${SQL_CONN}"
STORAGE_CONNECTION_STRING="${STORAGE_CONN}"
STORAGE_CONTAINER_NAME="recordings"
SERVICE_BUS_CONNECTION_STRING="${SB_CONN}"
SERVICE_BUS_QUEUE_NAME="analysis-queue"
EOF
  echo "✔ $dir/.env generado exitosamente."
done

# -------------------------------------------------------------
# B. voxready-worker/.env y worker/.env
# -------------------------------------------------------------
for dir in "voxready-worker" "worker"; do
  mkdir -p "$dir"
  cat <<EOF > "$dir/.env"
# Generado automáticamente por CLI Sync
SQL_CONNECTION_STRING="${SQL_CONN}"
STORAGE_CONNECTION_STRING="${STORAGE_CONN}"
STORAGE_CONTAINER_NAME="recordings"
SERVICE_BUS_CONNECTION_STRING="${SB_CONN}"
SERVICE_BUS_QUEUE_NAME="analysis-queue"

# Pipeline de Visión y Modelos Externos
VISION_SERVICE_URL="https://${VISION_FQDN}"
NVIDIA_API_KEY="${NVIDIA_KEY}"
NVIDIA_BASE_URL="https://integrate.api.nvidia.com/v1"
LLM_MODEL_NAME="meta/llama-3.2-90b-vision-instruct"
EOF
  echo "✔ $dir/.env generado exitosamente."
done

# -------------------------------------------------------------
# C. voxready-frontend/.env.local y frontend/.env.local
# -------------------------------------------------------------
for dir in "voxready-frontend" "frontend"; do
  mkdir -p "$dir"
  cat <<EOF > "$dir/.env.local"
# Generado automáticamente por CLI Sync
NEXT_PUBLIC_API_URL="https://${BACKEND_FQDN}/v1"
NEXT_PUBLIC_AZURE_CLIENT_ID="${CLIENT_APP_ID}"
NEXT_PUBLIC_AZURE_TENANT_ID="${TENANT_ID}"
NEXT_PUBLIC_REDIRECT_URI="http://localhost:3000"
EOF
  echo "✔ $dir/.env.local generado exitosamente."
done

echo "==> [4/4] Sincronización completada."
