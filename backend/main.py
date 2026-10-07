import os
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from azure.servicebus import ServiceBusClient, ServiceBusMessage
import jwt
from jwt import PyJWKClient
import pyodbc

# Cargar variables de entorno locales si existen
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
    load_dotenv("../.env", override=False)
except ImportError:
    pass

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="VoxReady Backend API", version="1.0.0")

# 1. Configuración de CORS
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
env_origins = os.getenv("CORS_ORIGINS", "")
if env_origins:
    origins.extend([o.strip() for o in env_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(set(origins)),
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://.*\.azurestaticapps\.net$|^https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# 2. Configuración desde variables de entorno
STORAGE_CONN_STR = os.getenv("STORAGE_CONNECTION_STRING", "")
CONTAINER_NAME = os.getenv("STORAGE_CONTAINER_NAME") or os.getenv("BLOB_CONTAINER_NAME", "recordings")
SERVICE_BUS_CONN_STR = os.getenv("SERVICE_BUS_CONNECTION_STRING", "")
QUEUE_NAME = os.getenv("SERVICE_BUS_QUEUE_NAME", "analysis-queue")
SQL_CONN_STR = os.getenv("SQL_CONNECTION_STRING") or os.getenv("DATABASE_URL", "")
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
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]

    # 1. Si no hay token o es token explícito de dev local:
    if (not token or token.startswith("dev-")) and DEV_AUTH:
        return {
            "sub": "dev-user-001",
            "oid": "dev-user-001",
            "name": "Dev User",
            "email": "dev@voxready.io",
            "role": "spokesperson",
        }

    if not token:
        raise HTTPException(status_code=401, detail="Token no provisto o inválido")

    # 2. Si viene un token real JWT (ej. de Microsoft Entra CIAM):
    try:
        client = _get_jwks_client()
        if client:
            try:
                signing_key = client.get_signing_key_from_jwt(token)
                allowed_audiences = [a for a in [
                    JWT_AUDIENCE,
                    "e219fd4b-3686-45dd-9656-b582d1fb0698",
                    "5dd1bf8d-c0de-4f67-8131-df42e93dcf29",
                    "api://5dd1bf8d-c0de-4f67-8131-df42e93dcf29"
                ] if a]
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=allowed_audiences if allowed_audiences else None,
                    options={
                        "verify_aud": bool(allowed_audiences),
                        "verify_iss": False,
                    },
                )
                return payload
            except Exception as e_jwks:
                logger.warning(f"Validación con firma JWKS falló ({e_jwks}).")
                if not DEV_AUTH:
                    raise e_jwks

        # Si DEV_AUTH está activo y falló JWKS, o en desarrollo local:
        # decodificamos el payload de Microsoft para extraer los datos reales del usuario
        if DEV_AUTH:
            payload = jwt.decode(token, options={"verify_signature": False})
            return payload

        raise HTTPException(status_code=401, detail="Error validando token con Microsoft")
    except Exception as e:
        logger.error(f"JWT Verification failed: {e}")
        raise HTTPException(status_code=401, detail=f"Token inválido: {str(e)}")


# 4. Esquemas de petición
class CreateSessionRequest(BaseModel):
    scenarioId: str | None = None
    scenario_id: str | None = None
    language: str = "es"
    tenant_id: str | None = "tenant-voxready-dev"

class ConsentRequest(BaseModel):
    acceptRecording: bool | None = None
    acknowledgeDeletion: bool | None = None
    acceptAudioVideoRecording: bool | None = None
    acceptAiEvaluation: bool | None = None
    policyVersion: str | None = "1.0"

try:
    from schemas.session import TurnInterval, FinishSessionRequest, WorkerTriggerPayload
    from services.worker_client import trigger_worker_analysis
except (ImportError, ValueError):
    from backend.schemas.session import TurnInterval, FinishSessionRequest, WorkerTriggerPayload
    from backend.services.worker_client import trigger_worker_analysis

# 5. Servicios de persistencia de usuarios (Azure SQL)
def _normalize_sql_conn_str(conn_str: str) -> str:
    """Normaliza la cadena de conexión para el driver ODBC Driver 18 en Azure SQL."""
    if "DRIVER=" not in conn_str.upper():
        conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};{conn_str}"
    if "Encrypt=" not in conn_str and "ENCRYPT=" not in conn_str:
        conn_str += ";Encrypt=yes;TrustServerCertificate=no;Connection Timeout=15;"
    return conn_str

def _safe_uuid(val: str | None) -> str | None:
    if not val:
        return None
    try:
        return str(uuid.UUID(str(val)))
    except (ValueError, TypeError, AttributeError):
        return None

def sync_or_get_user(
    user_id: str,
    email: str,
    display_name: str,
    client_id: str | None,
    token_role: str | None
) -> dict:
    """
    Sincroniza el usuario autenticado con la base de datos Azure SQL (tabla app_user).
    - Si existe, devuelve su perfil con el rol asignado en base de datos.
    - Si no existe, lo registra automáticamente con rol 'spokesperson'.
    - Permite cambiar roles directamente en Azure SQL y ver el cambio reflejado.
    - Es resiliente: ante caídas de BD o cold-starts, no interrumpe el acceso.
    """
    if not SQL_CONN_STR:
        return {}

    user_uuid = _safe_uuid(user_id)
    clean_email = email.strip() if email else ""

    try:
        conn_str = _normalize_sql_conn_str(SQL_CONN_STR)
        with pyodbc.connect(conn_str, timeout=10) as conn:
            cursor = conn.cursor()

            # 1. Asegurar tabla app_user si no existiese
            try:
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'app_user')
                    BEGIN
                        CREATE TABLE app_user (
                            id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
                            client_id UNIQUEIDENTIFIER NULL,
                            email NVARCHAR(256) NULL,
                            display_name NVARCHAR(150) NULL,
                            role NVARCHAR(50) DEFAULT 'spokesperson',
                            preferred_language CHAR(2) DEFAULT 'es',
                            created_at DATETIME2 DEFAULT SYSUTCDATETIME(),
                            updated_at DATETIME2 DEFAULT SYSUTCDATETIME(),
                            is_deleted BIT DEFAULT 0,
                            deleted_at DATETIME2 NULL
                        );
                        CREATE INDEX idx_app_user_email ON app_user(email);
                    END
                """)
                conn.commit()
            except Exception as e_tbl:
                logger.debug(f"Verificación de tabla app_user: {e_tbl}")

            # 2. Buscar si el usuario ya existe en app_user (por UUID o por email)
            row = None
            cols = []
            if user_uuid:
                cursor.execute(
                    "SELECT id, client_id, email, display_name, role, preferred_language FROM app_user WHERE id = ? AND (is_deleted IS NULL OR is_deleted = 0)",
                    (user_uuid,)
                )
                row = cursor.fetchone()
                if row:
                    cols = [c[0].lower() for c in cursor.description]

            if not row and clean_email:
                cursor.execute(
                    "SELECT id, client_id, email, display_name, role, preferred_language FROM app_user WHERE LOWER(email) = LOWER(?) AND (is_deleted IS NULL OR is_deleted = 0)",
                    (clean_email,)
                )
                row = cursor.fetchone()
                if row:
                    cols = [c[0].lower() for c in cursor.description]

            # 3. Si ya existe, retornar sus datos de la base de datos (con su rol asignado)
            if row:
                user_data = dict(zip(cols, row))
                logger.info(f"Usuario '{clean_email}' resuelto desde Azure SQL con rol: '{user_data.get('role')}'.")
                return user_data

            # 4. Auto-provisioning: Registrar usuario nuevo en app_user
            resolved_id = user_uuid or str(uuid.uuid5(uuid.NAMESPACE_DNS, user_id or clean_email or "default-user"))

            # Asociar al cliente activo si existe
            db_client_id = None
            try:
                cursor.execute("SELECT TOP 1 id FROM client WHERE status = 'active'")
                c_row = cursor.fetchone()
                if not c_row:
                    cursor.execute("SELECT TOP 1 id FROM client")
                    c_row = cursor.fetchone()
                if c_row:
                    db_client_id = c_row[0]
            except Exception:
                pass

            if not db_client_id:
                db_client_id = _safe_uuid(client_id)

            initial_role = token_role if token_role and token_role != "None" else "spokesperson"

            cursor.execute(
                """
                INSERT INTO app_user (id, client_id, email, display_name, role, preferred_language, is_deleted)
                VALUES (?, ?, ?, ?, ?, 'es', 0)
                """,
                (resolved_id, db_client_id, clean_email, display_name or "Vocero", initial_role)
            )
            conn.commit()
            logger.info(f"Usuario '{clean_email}' auto-registrado en Azure SQL (app_user) con rol: '{initial_role}'.")

            return {
                "id": resolved_id,
                "client_id": db_client_id,
                "email": clean_email,
                "display_name": display_name,
                "role": initial_role,
                "preferred_language": "es"
            }

    except Exception as e:
        logger.warning(f"No se pudo sincronizar usuario en Azure SQL: {e}. Continuando con datos del token.")
        return {}

# 6. Endpoints
@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "backend-api"}

@app.post("/dev/token")
def dev_token():
    return {"accessToken": "dev-token-voxready-dev"}

@app.get("/me")
@app.get("/v1/me")
def get_current_user_profile(user: dict = Depends(verify_token)):
    """Obtiene el perfil del usuario autenticado y sincroniza roles con Azure SQL."""
    user_id = user.get("oid") or user.get("sub", "")
    email = (
        user.get("email")
        or user.get("preferred_username")
        or user.get("upn")
        or user.get("unique_name", "")
    )
    if not email and isinstance(user.get("emails"), list) and user["emails"]:
        email = user["emails"][0]
    display_name = (
        user.get("name")
        or (f"{user.get('given_name', '')} {user.get('family_name', '')}".strip())
        or (email.split("@")[0] if email else "Vocero")
    )
    token_role = user.get("role") or user.get("extension_role") or "spokesperson"
    client_id = user.get("clientId") or user.get("client_id") or user.get("tid")

    # Sincronización con Azure SQL (auto-provisioning y lectura de roles en base de datos)
    db_user = sync_or_get_user(
        user_id=str(user_id),
        email=email or "",
        display_name=display_name,
        client_id=str(client_id) if client_id else None,
        token_role=token_role,
    )

    role = db_user.get("role") or token_role or "spokesperson"
    resolved_client_id = db_user.get("client_id") or (str(client_id) if client_id else "client-default")

    return {
        "userId": str(user_id),
        "email": email,
        "displayName": db_user.get("display_name") or display_name,
        "role": role,
        "clientId": str(resolved_client_id) if resolved_client_id else None,
        "preferredLanguage": db_user.get("preferred_language") or user.get("preferredLanguage", "es"),
    }

@app.get("/scenarios")
@app.get("/v1/scenarios")
def list_scenarios(category: str = "", q: str = "", page: int = 1, pageSize: int = 20, user: dict = Depends(verify_token)):
    items = [
        {
            "id": "crisis-voceria-01",
            "title": "Retiro Masivo de Alimentos Infantiles",
            "context": "Falla de calidad en la planta norte detectada durante control rutinario.",
            "category": "health",
            "audience": "Medios nacionales y familias afectadas",
            "difficulty": "hard",
            "estimatedMinutes": 15,
            "questionCount": 8,
            "languages": ["es"]
        },
        {
            "id": "crisis-operativa-02",
            "title": "Interrupción Crítica de Plataforma Transaccional",
            "context": "Caída del sistema central afectando transacciones de clientes corporativos.",
            "category": "operational",
            "audience": "Clientes B2B e inversionistas",
            "difficulty": "intermediate",
            "estimatedMinutes": 10,
            "questionCount": 6,
            "languages": ["es"]
        },
        {
            "id": "crisis-reputacional-03",
            "title": "Filtración No Autorizada de Datos Internos",
            "context": "Incidente de ciberseguridad con publicación parcial de registros confidenciales.",
            "category": "reputational",
            "audience": "Prensa especializada y reguladores",
            "difficulty": "hard",
            "estimatedMinutes": 12,
            "questionCount": 7,
            "languages": ["es"]
        }
    ]
    if category:
        items = [i for i in items if i["category"] == category]
    if q:
        items = [i for i in items if q.lower() in i["title"].lower() or q.lower() in i["context"].lower()]
    return {
        "items": items,
        "page": page,
        "pageSize": pageSize,
        "total": len(items)
    }

@app.get("/scenarios/{scenario_id}")
@app.get("/v1/scenarios/{scenario_id}")
def get_scenario(scenario_id: str, user: dict = Depends(verify_token)):
    return {
        "id": scenario_id,
        "title": "Retiro Masivo de Alimentos Infantiles",
        "context": "Falla de calidad en la planta norte detectada durante control rutinario.",
        "category": "health",
        "audience": "Medios nacionales y familias afectadas",
        "difficulty": "hard",
        "estimatedMinutes": 15,
        "questionCount": 8,
        "languages": ["es"]
    }

@app.post("/sessions", status_code=201)
@app.post("/v1/sessions", status_code=201)
@app.post("/api/sessions")
@app.post("/v1/api/sessions")
def create_session(payload: CreateSessionRequest, user: dict = Depends(verify_token)):
    sc_id = payload.scenarioId or payload.scenario_id or "crisis-voceria-01"
    session_uuid = str(uuid.uuid4())
    session_id = session_uuid

    # Persistir en Azure SQL para garantizar integridad referencial con tabla report
    if SQL_CONN_STR:
        try:
            conn_str = _normalize_sql_conn_str(SQL_CONN_STR)
            with pyodbc.connect(conn_str, timeout=10) as conn:
                cur = conn.cursor()
                # Resolver escenario activo
                cur.execute("SELECT TOP 1 id FROM scenario WHERE status = 'active'")
                sc_row = cur.fetchone()
                scenario_uuid = sc_row[0] if sc_row else None

                # Resolver rúbrica publicada
                cur.execute("SELECT TOP 1 id FROM rubric_version WHERE status = 'published'")
                rub_row = cur.fetchone()
                rubric_uuid = rub_row[0] if rub_row else None

                DEFAULT_CLIENT_ID = "7D8C0575-196C-40D1-AD7C-08AA2843B4C3"
                DEFAULT_USER_ID = "4CC52B91-3A9C-5659-8363-4F069CC39F9B"

                # Resolver cliente
                cur.execute("SELECT TOP 1 id FROM client WHERE status = 'active'")
                c_row = cur.fetchone()
                client_uuid = c_row[0] if c_row else DEFAULT_CLIENT_ID

                # Resolver usuario válido para evitar violación de FK con app_user
                user_db_id = _safe_uuid(user.get("user_id_in_db") or user.get("id"))
                if not user_db_id:
                    cur.execute("SELECT TOP 1 id FROM app_user WHERE is_deleted = 0")
                    u_row = cur.fetchone()
                    user_db_id = u_row[0] if u_row else DEFAULT_USER_ID

                user_db_id = user_db_id or DEFAULT_USER_ID
                client_uuid = client_uuid or DEFAULT_CLIENT_ID

                cur.execute("""
                    INSERT INTO session (
                        id, client_id, user_id, scenario_id, rubric_version_id,
                        language, status, started_at, created_at, updated_at, is_deleted
                    )
                    VALUES (?, ?, ?, ?, ?, 'es', 'created', SYSUTCDATETIME(), SYSUTCDATETIME(), SYSUTCDATETIME(), 0)
                """, (session_uuid, client_uuid, user_db_id, scenario_uuid, rubric_uuid))
                conn.commit()
                logger.info(f"Sesión creada en Azure SQL: {session_uuid}")
        except Exception as e:
            logger.warning(f"Aviso al crear sesión en Azure SQL: {e}")

    return {
        "sessionId": session_id,
        "session_id": session_id,
        "scenarioId": sc_id,
        "scenario_id": sc_id,
        "status": "created",
        "questionCount": 8,
    }

@app.get("/sessions/{session_id}")
@app.get("/v1/sessions/{session_id}")
@app.get("/api/sessions/{session_id}")
def get_session(session_id: str, user: dict = Depends(verify_token)):
    return {
        "sessionId": session_id,
        "scenarioId": "crisis-voceria-01",
        "status": "created",
        "questions": [
            {"id": "q1", "sequenceNo": 1, "text": "¿Cuál es la gravedad real de la falla detectada en el lote de producción?"},
            {"id": "q2", "sequenceNo": 2, "text": "¿Cómo garantizan que otros productos en el mercado no estén afectados por el mismo problema?"},
            {"id": "q3", "sequenceNo": 3, "text": "¿Existe algún riesgo directo para la salud o integridad de los consumidores?"},
            {"id": "q4", "sequenceNo": 4, "text": "¿Qué compensación inmediata recibirán los clientes perjudicados?"},
            {"id": "q5", "sequenceNo": 5, "text": "¿Existen sanciones internas contra los responsables de la supervisión de calidad?"},
            {"id": "q6", "sequenceNo": 6, "text": "¿Cómo afectará este retiro las metas comerciales y financieras del trimestre?"},
            {"id": "q7", "sequenceNo": 7, "text": "¿Qué medidas concretas han implementado para que esto no vuelva a ocurrir jamás?"},
            {"id": "q8", "sequenceNo": 8, "text": "Para concluir, ¿cuál es el mensaje definitivo de la presidencia de la empresa a las familias?"}
        ],
        "retentionPolicy": {
            "version": "1.0",
            "keep": "full_recording",
            "termDays": 30
        }
    }

@app.post("/sessions/{session_id}/consent")
@app.post("/v1/sessions/{session_id}/consent")
@app.post("/api/sessions/{session_id}/consent")
def grant_consent(session_id: str, payload: ConsentRequest, user: dict = Depends(verify_token)):
    return {
        "sessionId": session_id,
        "status": "consented",
        "consentId": f"consent-{session_id}-{int(datetime.now(timezone.utc).timestamp())}",
        "consentedAt": datetime.now(timezone.utc).isoformat()
    }

class DevTokenRequest(BaseModel):
    email: str = "ana.torres@acme-corp.com"

@app.post("/dev/token")
@app.post("/v1/dev/token")
def create_dev_token(payload: DevTokenRequest):
    return {
        "accessToken": "dev-local-jwt-token-voxready",
        "tokenType": "Bearer",
        "expiresIn": 28800
    }

@app.put("/sessions/{session_id}/mock-upload")
@app.put("/v1/sessions/{session_id}/mock-upload")
def mock_upload(session_id: str):
    return {"status": "uploaded"}

@app.post("/sessions/{session_id}/recording-url")
@app.post("/v1/sessions/{session_id}/recording-url")
@app.post("/api/sessions/{session_id}/upload-url")
@app.post("/v1/api/sessions/{session_id}/upload-url")
def get_upload_sas_url(session_id: str, user: dict = Depends(verify_token)):
    """Genera URL prefirmada temporal para subida directa desde el navegador (PUT)"""
    if not STORAGE_CONN_STR:
        mock_url = f"http://localhost:8000/v1/sessions/{session_id}/mock-upload"
        return {
            "upload_url": mock_url,
            "uploadUrl": mock_url,
            "blob_name": f"recordings/{session_id}.webm",
            "blobPath": f"recordings/{session_id}.webm"
        }

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
        return {"upload_url": upload_url, "uploadUrl": upload_url, "blob_name": blob_name, "blobPath": blob_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando SAS token: {str(e)}")

@app.get("/sessions/{session_id}/recording-url")
@app.get("/v1/sessions/{session_id}/recording-url")
@app.get("/api/sessions/{session_id}/recording-url")
@app.get("/v1/api/sessions/{session_id}/recording-url")
def get_playback_sas_url(session_id: str, user: dict = Depends(verify_token)):
    """Genera URL prefirmada temporal de LECTURA para reproducir la grabación desde el navegador"""
    blob_name = f"recordings/{session_id}.webm"

    if not STORAGE_CONN_STR:
        return {
            "playback_url": "",
            "session_id": session_id,
            "message": "Storage no configurado en desarrollo local"
        }

    try:
        blob_service_client = BlobServiceClient.from_connection_string(STORAGE_CONN_STR)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)
        blob_client = container_client.get_blob_client(blob_name)

        if not blob_client.exists():
            raise HTTPException(
                status_code=404,
                detail=f"La grabación '{blob_name}' no existe en Azure Blob Storage."
            )

        account_name = blob_service_client.account_name
        account_key = blob_service_client.credential.account_key

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=CONTAINER_NAME,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(minutes=60)
        )
        playback_url = f"https://{account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}?{sas_token}"
        return {"playback_url": playback_url, "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando URL de reproducción: {str(e)}")


@app.post("/sessions/{session_id}/finish", status_code=202)
@app.post("/v1/sessions/{session_id}/finish", status_code=202)
@app.post("/api/sessions/{session_id}/finish", status_code=202)
@app.post("/v1/api/sessions/{session_id}/finish", status_code=202)
async def finish_session(session_id: str, payload: FinishSessionRequest, user: dict = Depends(verify_token)):
    """
    Finaliza la grabación de la sesión, registra el job de análisis en Azure SQL
    y dispara la inferencia asíncrona en ca-analysis-worker vía HTTP interno (escalado 0 a 1).
    """
    session_uuid = _safe_uuid(session_id) or session_id
    job_id = str(uuid.uuid4())
    rubric_version_id = None
    blob_path = payload.blobPath or payload.video_blob_name or f"recordings/{session_id}.webm"

    # 1. Gestionar estado y job en Azure SQL si está configurado
    if SQL_CONN_STR:
        try:
            conn_str = _normalize_sql_conn_str(SQL_CONN_STR)
            with pyodbc.connect(conn_str, timeout=10) as conn:
                cur = conn.cursor()
                cur.execute("SELECT id, status, rubric_version_id FROM session WHERE id = ?", session_uuid)
                session_row = cur.fetchone()

                if session_row and session_row[2]:
                    rubric_version_id = session_row[2]
                else:
                    cur.execute("SELECT TOP 1 id FROM rubric_version WHERE status = 'published'")
                    rub_row = cur.fetchone()
                    rubric_version_id = rub_row[0] if rub_row else None

                # Crear registro en analysis_job
                cur.execute("""
                    INSERT INTO analysis_job (id, session_id, rubric_version_id, status, started_at, created_at, updated_at)
                    VALUES (?, ?, ?, 'running', SYSUTCDATETIME(), SYSUTCDATETIME(), SYSUTCDATETIME())
                """, (job_id, session_uuid, rubric_version_id))

                # Transicionar sesión a 'analyzing'
                cur.execute("""
                    UPDATE session 
                    SET status = 'analyzing', finished_at = SYSUTCDATETIME(), updated_at = SYSUTCDATETIME()
                    WHERE id = ?
                """, session_uuid)
                conn.commit()
                logger.info(f"Sesión {session_uuid} actualizada a 'analyzing' (Job: {job_id}) en Azure SQL.")
        except Exception as e_sql:
            logger.warning(f"Aviso actualizando estado en Azure SQL ({session_id}): {e_sql}")

    # 2. Despachar llamada HTTP interna al worker (DNS privado de Container Apps)
    trigger_payload = WorkerTriggerPayload(
        sessionId=session_id,
        jobId=job_id,
        rubricVersionId=str(rubric_version_id) if rubric_version_id else "",
        blobPath=blob_path,
        turns=payload.turns or []
    )

    worker_started = await trigger_worker_analysis(trigger_payload)
    if not worker_started:
        logger.warning(f"No se pudo confirmar el inicio del worker HTTP para job {job_id}.")
        # Fallback de seguridad: si Service Bus está configurado, encolar como contingencia
        if SERVICE_BUS_CONN_STR:
            try:
                message_payload = {
                    "event_type": "SESSION_RECORDING_COMPLETED",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "session_id": session_id,
                        "job_id": job_id,
                        "rubric_version_id": str(rubric_version_id) if rubric_version_id else None,
                        "user_id": user.get("sub", "anonymous"),
                        "scenario_id": payload.scenario_id,
                        "tenant_id": payload.tenant_id,
                        "media": {
                            "video_blob_name": blob_path,
                            "storage_container": CONTAINER_NAME
                        },
                        "turns": [t.model_dump() for t in (payload.turns or [])]
                    }
                }
                with ServiceBusClient.from_connection_string(SERVICE_BUS_CONN_STR) as sb_client:
                    with sb_client.get_queue_sender(queue_name=QUEUE_NAME) as sender:
                        msg = ServiceBusMessage(json.dumps(message_payload), content_type="application/json")
                        sender.send_messages(msg)
                logger.info(f"Mensaje de contingencia encolado en Service Bus para sesión {session_id}")
            except Exception as sb_err:
                logger.warning(f"Fallo en encolado de contingencia Service Bus: {sb_err}")

    return {
        "sessionId": session_id,
        "session_id": session_id,
        "status": "analyzing",
        "analysisId": job_id,
        "estimatedSeconds": 45
    }


@app.get("/sessions/{session_id}/report")
@app.get("/v1/sessions/{session_id}/report")
@app.get("/api/sessions/{session_id}/report")
@app.get("/v1/api/sessions/{session_id}/report")
def get_session_report(session_id: str, user: dict = Depends(verify_token)):
    """Obtiene el reporte consolidado normalizado desde Blob Storage y Azure SQL"""
    report_data = None

    # 1. Intentar leer desde Azure Blob Storage
    if STORAGE_CONN_STR:
        try:
            blob_service_client = BlobServiceClient.from_connection_string(STORAGE_CONN_STR)
            container_client = blob_service_client.get_container_client("reports")
            report_blob_name = f"{session_id}_report.json"
            blob_client = container_client.get_blob_client(report_blob_name)

            if blob_client.exists():
                content = blob_client.download_blob().readall()
                report_data = json.loads(content.decode("utf-8"))
        except Exception as e:
            logger.warning(f"Aviso al leer reporte desde Blob Storage ({session_id}): {e}")

    # 2. Si no está en Blob Storage o para complementar, consultar Azure SQL
    sql_report = None
    if SQL_CONN_STR and not report_data:
        try:
            conn_str = _normalize_sql_conn_str(SQL_CONN_STR)
            valid_uuid = _safe_uuid(session_id) or str(uuid.uuid5(uuid.NAMESPACE_DNS, session_id))
            with pyodbc.connect(conn_str, timeout=10) as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT r.id, r.overall_score, r.narrative_strengths, r.narrative_improvements,
                           r.cross_signal_observation, r.generated_at, s.status as session_status
                    FROM report r
                    JOIN session s ON r.session_id = s.id
                    WHERE s.id = ? AND r.is_current = 1
                """, valid_uuid)
                row = cur.fetchone()
                if row:
                    report_id, overall_score, strengths_raw, improvements_raw, cross_signal, gen_at, sess_status = row
                    strengths = json.loads(strengths_raw) if strengths_raw else []
                    improvements = json.loads(improvements_raw) if improvements_raw else []

                    # Leer area_scores
                    cur.execute("""
                        SELECT ra.area_key, a.value
                        FROM area_score a
                        JOIN rubric_area ra ON a.rubric_area_id = ra.id
                        WHERE a.report_id = ?
                    """, report_id)
                    area_scores_list = [{"area": r[0], "value": r[1]} for r in cur.fetchall()]

                    sql_report = {
                        "sessionId": session_id,
                        "session_id": session_id,
                        "overallScore": overall_score,
                        "status": "completed",
                        "narrative": {
                            "strengths": strengths,
                            "improvements": improvements,
                            "crossSignal": cross_signal or "",
                            "visum": {
                                "sintesis_ejecutiva": {
                                    "diagnostico_general": "Evaluación estructurada completada.",
                                    "fortaleza_principal": strengths[0] if strengths else "",
                                    "foco_desarrollo": improvements[0] if improvements else "",
                                    "continuidad_recomendada": "Entrenamiento continuo en vocería de crisis."
                                },
                                "desempeno_observado": {
                                    "evaluacion_general": "Desempeño registrado en sistema de evaluación.",
                                    "fortalezas": strengths,
                                    "oportunidades_desarrollo": improvements,
                                    "formula_practica_recomendada": "Reconocer el impacto -> Explicar certezas -> Acciones en curso."
                                },
                                "observacion_senal_cruzada": cross_signal or ""
                            }
                        },
                        "areaScores": area_scores_list,
                        "generatedAt": gen_at.isoformat() if gen_at else datetime.now(timezone.utc).isoformat()
                    }
        except Exception as sqle:
            logger.warning(f"Aviso al consultar reporte en Azure SQL ({session_id}): {sqle}")

    final_report = report_data or sql_report

    if not final_report:
        return {
            "sessionId": session_id,
            "session_id": session_id,
            "status": "processing",
            "message": "El análisis multimedia está en curso..."
        }

    # Normalizar respuesta unificada asegurando todas las claves requeridas por el frontend
    overall = final_report.get("overallScore") or final_report.get("puntuacion_global", {}).get("score_general", 75)
    visum = (
        final_report.get("informe_ejecutivo_visum")
        or final_report.get("narrative", {}).get("visum")
        or {}
    )
    narrative_obj = final_report.get("narrative") or {}
    if not narrative_obj.get("visum") and visum:
        narrative_obj["visum"] = visum
    if not narrative_obj.get("strengths") and visum.get("desempeno_observado", {}).get("fortalezas"):
        narrative_obj["strengths"] = visum["desempeno_observado"]["fortalezas"]
    if not narrative_obj.get("improvements") and visum.get("desempeno_observado", {}).get("oportunidades_desarrollo"):
        narrative_obj["improvements"] = visum["desempeno_observado"]["oportunidades_desarrollo"]
    if not narrative_obj.get("crossSignal") and visum.get("observacion_senal_cruzada"):
        narrative_obj["crossSignal"] = visum["observacion_senal_cruzada"]

    area_scores = final_report.get("areaScores")
    if not area_scores and "puntuacion_global" in final_report and "areas" in final_report["puntuacion_global"]:
        areas_dict = final_report["puntuacion_global"]["areas"]
        area_scores = [{"area": k, "value": v} for k, v in areas_dict.items()]

    response_payload = {
        "sessionId": session_id,
        "session_id": session_id,
        "status": "completed",
        "overallScore": int(round(overall)),
        "puntuacion_global": final_report.get("puntuacion_global", {}),
        "areaScores": area_scores or [],
        "narrative": narrative_obj,
        "informe_ejecutivo_visum": visum,
        "metrics": final_report.get("metrics", {}),
        "recordingUrl": final_report.get("recordingUrl") or f"https://stavoxreadyst.blob.core.windows.net/recordings/recordings/{session_id}.webm",
        "scenarioTitle": final_report.get("scenarioTitle") or "Simulación de Vocería en Crisis",
        "generatedAt": final_report.get("processed_at") or final_report.get("generatedAt") or datetime.now(timezone.utc).isoformat()
    }
    return response_payload

