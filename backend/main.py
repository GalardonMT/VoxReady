import os
import json
import logging
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from azure.servicebus import ServiceBusClient, ServiceBusMessage
import jwt
from jwt import PyJWKClient

# Cargar variables de entorno locales si existen
try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv("../.env")
except ImportError:
    pass

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="VoxReady Backend API", version="1.0.0")

# 1. Configuración de CORS
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Configuración desde variables de entorno
STORAGE_CONN_STR = os.getenv("STORAGE_CONNECTION_STRING", "")
CONTAINER_NAME = os.getenv("BLOB_CONTAINER_NAME", "recordings")
SERVICE_BUS_CONN_STR = os.getenv("SERVICE_BUS_CONNECTION_STRING", "")
QUEUE_NAME = os.getenv("SERVICE_BUS_QUEUE_NAME", "analysis-queue")
JWKS_URL = os.getenv("JWKS_URL", "")
JWT_ISSUER = os.getenv("JWT_ISSUER", "")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "")
DEV_AUTH = os.getenv("DEV_AUTH", "false").lower() == "true"

# 3. Dependencia de validación de JWT (Microsoft Entra External ID)
_jwks_client: PyJWKClient | None = None

def _get_jwks_client() -> PyJWKClient | None:
    global _jwks_client
    if _jwks_client is None and JWKS_URL:
        _jwks_client = PyJWKClient(JWKS_URL, cache_keys=True)
    return _jwks_client

def verify_token(authorization: str = Header(None)):
    if DEV_AUTH:
        return {
            "sub": "dev-user-001",
            "oid": "dev-user-001",
            "name": "Dev User",
            "email": "dev@voxready.io",
            "role": "spokesperson",
        }
    
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token no provisto o inválido")
    
    token = authorization.split(" ")[1]
    try:
        client = _get_jwks_client()
        if not client:
            raise HTTPException(status_code=500, detail="JWKS_URL no configurada en el servidor")

        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=JWT_AUDIENCE if JWT_AUDIENCE else None,
            issuer=JWT_ISSUER if JWT_ISSUER else None,
            options={
                "verify_aud": bool(JWT_AUDIENCE),
                "verify_iss": bool(JWT_ISSUER),
            },
        )
        return payload
    except Exception as e:
        logger.error(f"JWT Verification failed: {e}")
        raise HTTPException(status_code=401, detail=f"Token inválido: {str(e)}")

# 4. Esquemas de petición
class CreateSessionRequest(BaseModel):
    scenario_id: str
    tenant_id: str

class FinishSessionRequest(BaseModel):
    video_blob_name: str
    scenario_id: str
    tenant_id: str

# 5. Endpoints
@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "backend-api"}

@app.post("/dev/token")
def dev_token():
    return {"accessToken": "dev-token-voxready-dev"}

@app.get("/me")
@app.get("/v1/me")
def get_current_user_profile(user: dict = Depends(verify_token)):
    """Obtiene el perfil del usuario autenticado con Microsoft Entra CIAM."""
    user_id = user.get("oid") or user.get("sub", "")
    email = user.get("email") or user.get("preferred_username") or user.get("upn", "")
    if not email and isinstance(user.get("emails"), list) and user["emails"]:
        email = user["emails"][0]
    display_name = user.get("name") or (email.split("@")[0] if email else "Vocero")
    role = user.get("role") or user.get("extension_role") or "spokesperson"
    client_id = user.get("clientId") or user.get("client_id") or user.get("tid")

    return {
        "userId": str(user_id),
        "email": email,
        "displayName": display_name,
        "role": role,
        "clientId": str(client_id) if client_id else None,
        "preferredLanguage": user.get("preferredLanguage", "es"),
    }

@app.post("/api/sessions")
@app.post("/v1/api/sessions")
def create_session(payload: CreateSessionRequest, user: dict = Depends(verify_token)):
    session_id = f"session-{payload.scenario_id}-{int(datetime.now(timezone.utc).timestamp())}"
    return {"session_id": session_id, "status": "created", "scenario_id": payload.scenario_id}

@app.post("/api/sessions/{session_id}/upload-url")
@app.post("/v1/api/sessions/{session_id}/upload-url")
def get_upload_sas_url(session_id: str, user: dict = Depends(verify_token)):
    """Genera URL prefirmada temporal para subida directa desde el navegador (PUT)"""
    if not STORAGE_CONN_STR:
        raise HTTPException(status_code=500, detail="Storage Connection String no configurada")
    
    blob_name = f"recordings/{session_id}.webm"
    try:
        blob_service_client = BlobServiceClient.from_connection_string(STORAGE_CONN_STR)
        account_name = blob_service_client.account_name
        account_key = blob_service_client.credential.account_key

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=CONTAINER_NAME,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(create=True, write=True),
            expiry=datetime.now(timezone.utc) + timedelta(minutes=30)
        )
        upload_url = f"https://{account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}?{sas_token}"
        return {"upload_url": upload_url, "blob_name": blob_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando SAS token: {str(e)}")

@app.post("/api/sessions/{session_id}/finish")
@app.post("/v1/api/sessions/{session_id}/finish")
def finish_session(session_id: str, payload: FinishSessionRequest, user: dict = Depends(verify_token)):
    """Publica evento en Service Bus para iniciar pipeline del worker"""
    if not SERVICE_BUS_CONN_STR:
        raise HTTPException(status_code=500, detail="Service Bus Connection String no configurada")

    message_payload = {
        "event_type": "SESSION_RECORDING_COMPLETED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "session_id": session_id,
            "user_id": user.get("sub", "anonymous"),
            "scenario_id": payload.scenario_id,
            "tenant_id": payload.tenant_id,
            "media": {
                "video_blob_name": payload.video_blob_name,
                "storage_container": CONTAINER_NAME
            }
        }
    }

    try:
        with ServiceBusClient.from_connection_string(SERVICE_BUS_CONN_STR) as client:
            with client.get_queue_sender(queue_name=QUEUE_NAME) as sender:
                msg = ServiceBusMessage(json.dumps(message_payload), content_type="application/json")
                sender.send_messages(msg)
        return {"status": "queued", "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error encolando en Service Bus: {str(e)}")


@app.get("/api/sessions/{session_id}/report")
@app.get("/v1/api/sessions/{session_id}/report")
def get_session_report(session_id: str, user: dict = Depends(verify_token)):
    """Obtiene el reporte consolidado desde Blob Storage o retorna estado processing"""
    if not STORAGE_CONN_STR:
        raise HTTPException(status_code=500, detail="Storage Connection String no configurada")
    
    try:
        blob_service_client = BlobServiceClient.from_connection_string(STORAGE_CONN_STR)
        container_client = blob_service_client.get_container_client("reports")
        report_blob_name = f"{session_id}_report.json"
        blob_client = container_client.get_blob_client(report_blob_name)
        
        if not blob_client.exists():
            return {
                "session_id": session_id,
                "status": "processing",
                "message": "El análisis multimedia está en curso..."
            }
        
        content = blob_client.download_blob().readall()
        report_data = json.loads(content.decode("utf-8"))
        report_data["status"] = "completed"
        return report_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo reporte: {str(e)}")

