import os
import json
import logging
import uuid
import re
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from pydantic import Field, StringConstraints, field_validator
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from azure.servicebus import ServiceBusClient, ServiceBusMessage
import jwt
from jwt import PyJWKClient
import pyodbc
import master_topics as master_store
import spokesperson_store
import microlessons as microlesson_store

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
MICROLESSON_VIDEO_MAX_BYTES = int(os.getenv("MICROLESSON_VIDEO_MAX_BYTES", str(250 * 1024 * 1024)))
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

    if not token:
        raise HTTPException(status_code=401, detail="Token no provisto o inválido")

    # El token local solo identifica una fila existente. Rol, cliente, nombre
    # y correo se resuelven siempre desde dbo.app_user.
    if DEV_AUTH and token.startswith("dev-user-"):
        user_id = _safe_uuid(token.removeprefix("dev-user-"))
        if not user_id:
            raise HTTPException(status_code=401, detail="Token de desarrollo inválido")
        return {"sub": user_id, "oid": user_id}
    if DEV_AUTH and token.startswith("dev-"):
        raise HTTPException(status_code=401, detail="Token de desarrollo inválido")

    # 2. Los tokens reales de Microsoft Entra siempre requieren firma válida,
    # incluso cuando el acceso local de desarrollo está habilitado.
    try:
        client = _get_jwks_client()
        if not client:
            raise HTTPException(status_code=401, detail="La validación de Microsoft Entra no está configurada.")
        signing_key = client.get_signing_key_from_jwt(token)
        allowed_audiences = [a for a in [
            JWT_AUDIENCE,
            "e219fd4b-3686-45dd-9656-b582d1fb0698",
            "5dd1bf8d-c0de-4f67-8131-df42e93dcf29",
            "api://5dd1bf8d-c0de-4f67-8131-df42e93dcf29"
        ] if a]
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=allowed_audiences if allowed_audiences else None,
            options={
                "verify_aud": bool(allowed_audiences),
                "verify_iss": False,
            },
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.warning("Falló la validación firmada del token de Microsoft Entra: %s", type(error).__name__)
        raise HTTPException(status_code=401, detail="Token de Microsoft Entra inválido.") from None


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
    """Resuelve un usuario existente; nunca aprovisiona durante una petición."""
    if not SQL_CONN_STR:
        return {}

    user_uuid = _safe_uuid(user_id)
    clean_email = email.strip() if email else ""

    try:
        conn_str = _normalize_sql_conn_str(SQL_CONN_STR)
        with pyodbc.connect(conn_str, timeout=10) as conn:
            cursor = conn.cursor()
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
                    "SELECT id, client_id, email, display_name, role, preferred_language FROM app_user "
                    "WHERE LOWER(LTRIM(RTRIM(email))) = LOWER(?) AND (is_deleted IS NULL OR is_deleted = 0)",
                    (clean_email,)
                )
                matches = cursor.fetchall()
                if len(matches) == 1:
                    row = matches[0]
                    cols = [c[0].lower() for c in cursor.description]

            if row:
                user_data = dict(zip(cols, row))
                logger.info("Usuario autenticado resuelto desde Azure SQL.")
                return user_data
            return {}

    except Exception as e:
        logger.warning("No se pudo resolver el usuario en Azure SQL: %s", type(e).__name__)
        return {}

# 6. Endpoints
@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "backend-api"}

@app.get("/me")
@app.get("/v1/me")
def get_current_user_profile(user: dict = Depends(verify_token)):
    """Obtiene desde Azure SQL el perfil existente del usuario autenticado."""
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

    # La base de datos es la única fuente de rol, cliente e identidad visible.
    db_user = sync_or_get_user(
        user_id=str(user_id),
        email=email or "",
        display_name=display_name,
        client_id=str(client_id) if client_id else None,
        token_role=token_role,
    )

    if not db_user:
        raise HTTPException(status_code=403, detail="Usuario no registrado en VoxReady.")

    return {
        "userId": str(db_user["id"]),
        "email": str(db_user.get("email") or "").strip(),
        "displayName": db_user.get("display_name") or str(db_user.get("email") or "Usuario"),
        "role": db_user["role"],
        "clientId": str(db_user["client_id"]) if db_user.get("client_id") else None,
        "preferredLanguage": db_user.get("preferred_language") or "es",
    }

@app.get("/scenarios")
@app.get("/v1/scenarios")
def list_scenarios(category: str = "", q: str = "", page: int = 1, pageSize: int = 20, user: dict = Depends(verify_token)):
    if page < 1 or pageSize < 1 or pageSize > 100:
        raise HTTPException(422, "Invalid pagination")
    return spokesperson_store.list_catalog(SQL_CONN_STR, user, category, q, page, pageSize)

@app.get("/scenarios/{scenario_id}")
@app.get("/v1/scenarios/{scenario_id}")
def get_scenario(scenario_id: str, user: dict = Depends(verify_token)):
    return spokesperson_store.scenario_detail(SQL_CONN_STR, user, scenario_id)

@app.post("/sessions", status_code=201)
@app.post("/v1/sessions", status_code=201)
@app.post("/api/sessions")
@app.post("/v1/api/sessions")
def create_session(payload: CreateSessionRequest, user: dict = Depends(verify_token), idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
    scenario_id = payload.scenarioId or payload.scenario_id
    if not scenario_id:
        raise HTTPException(422, "scenarioId is required")
    return spokesperson_store.create_session(SQL_CONN_STR, user, scenario_id, payload.language, idempotency_key)

@app.get("/sessions/{session_id}")
@app.get("/v1/sessions/{session_id}")
@app.get("/api/sessions/{session_id}")
def get_session(session_id: str, user: dict = Depends(verify_token)):
    return spokesperson_store.get_session(SQL_CONN_STR, user, session_id)

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
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=256)]

@app.post("/dev/token")
@app.post("/v1/dev/token")
def create_dev_token(payload: DevTokenRequest):
    if not DEV_AUTH:
        raise HTTPException(status_code=404, detail="Acceso de desarrollo no disponible.")
    with master_store.database(SQL_CONN_STR) as cursor:
        cursor.execute("""SELECT id FROM dbo.app_user
                          WHERE LOWER(LTRIM(RTRIM(email)))=LOWER(?)
                          AND (is_deleted IS NULL OR is_deleted=0)""", payload.email)
        matches = cursor.fetchall()
        if len(matches) != 1:
            raise HTTPException(status_code=404, detail="Usuario no registrado en VoxReady.")
        user_id = str(matches[0][0])
    return {
        "accessToken": f"dev-user-{user_id}",
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
    if not blob_path.startswith("recordings/"):
        blob_path = f"recordings/{blob_path.lstrip('/')}"

    # 1. Gestionar estado y job en Azure SQL si está configurado
    if SQL_CONN_STR:
        try:
            conn_str = _normalize_sql_conn_str(SQL_CONN_STR)
            with pyodbc.connect(conn_str, timeout=10) as conn:
                cur = conn.cursor()
                # Resolver sesión por external_session_id o id
                session_row = None
                try:
                    cur.execute("SELECT id, status, rubric_version_id FROM session WHERE external_session_id = ?", session_id)
                    session_row = cur.fetchone()
                except Exception:
                    pass

                if not session_row:
                    valid_uuid = _safe_uuid(session_id)
                    if valid_uuid:
                        try:
                            cur.execute("SELECT id, status, rubric_version_id FROM session WHERE id = ?", valid_uuid)
                            session_row = cur.fetchone()
                        except Exception:
                            pass

                if session_row:
                    session_uuid = str(session_row[0])
                    if session_row[2]:
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

    # Normalizar turnos (turns o question_marks)
    turns = list(payload.turns or [])
    if not turns and payload.question_marks:
        for idx, qm in enumerate(payload.question_marks):
            q_idx = qm.get("questionIndex", idx)
            start_ms = qm.get("startMs", 0)
            end_ms = qm.get("endMs")
            if end_ms is None:
                end_ms = start_ms + 5000
            turns.append(TurnInterval(
                questionId=f"q-{q_idx + 1}",
                sequenceNo=idx + 1,
                startMs=int(start_ms),
                endMs=int(end_ms)
            ))

    # 2. Despachar llamada HTTP interna al worker (DNS privado de Container Apps)
    trigger_payload = WorkerTriggerPayload(
        sessionId=session_id,
        jobId=job_id,
        rubricVersionId=str(rubric_version_id) if rubric_version_id else "",
        blobPath=blob_path,
        turns=turns
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
                        "turns": [t.model_dump() for t in turns]
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
            valid_uuid = _safe_uuid(session_id)
            with pyodbc.connect(conn_str, timeout=10) as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT r.id, r.overall_score, r.narrative_strengths, r.narrative_improvements,
                           r.cross_signal_observation, r.generated_at, s.status as session_status
                    FROM report r
                    JOIN session s ON r.session_id = s.id
                    WHERE (s.external_session_id = ? OR s.id = ?) AND r.is_current = 1
                """, (session_id, valid_uuid))
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


# Configuración maestra. Los tipos técnicos se mantienen separados de etiquetas UI.
MasterText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
MasterTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class MasterQuestionInput(BaseModel):
    id: uuid.UUID | None = None
    text: MasterText


class MasterTopicRequest(BaseModel):
    name: MasterTitle
    context: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    optics: Literal['empathetic', 'formal', 'technical']
    audience: Literal['leadership', 'frontline', 'technical']
    keyMessages: list[MasterText] = Field(default_factory=list)
    redLines: list[MasterText] = Field(default_factory=list)
    questions: list[MasterQuestionInput] = Field(default_factory=list)

    @field_validator('questions', mode='before')
    @classmethod
    def question_strings(cls, questions):
        return [{"text": q} if isinstance(q, str) else q for q in questions] if isinstance(questions, list) else questions


class MasterScenarioRequest(BaseModel):
    title: MasterTitle
    category: Literal['health', 'operational', 'reputational']
    difficulty: Literal['basic', 'intermediate', 'hard']
    estimatedMinutes: Annotated[int, Field(strict=True, gt=0)]
    clientId: uuid.UUID
    questionIds: Annotated[list[uuid.UUID], Field(min_length=1)]

    @field_validator('questionIds')
    @classmethod
    def distinct_questions(cls, questions):
        if len(set(questions)) != len(questions):
            raise ValueError('No se puede seleccionar una pregunta dos veces.')
        return questions


class MasterStatusRequest(BaseModel):
    status: Literal['active', 'archived']


class MicrolessonRequest(BaseModel):
    clientId: uuid.UUID
    scenarioId: uuid.UUID
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    topicTag: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    durationMinutes: Annotated[int, Field(strict=True, gt=0, le=1440)] | None = None
    learningObjective: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    theoryContent: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    exampleContent: str | None = None
    status: Literal['active', 'archived']

    @field_validator('topicTag', 'exampleContent', mode='before')
    @classmethod
    def optional_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class MicrolessonVideoUploadRequest(BaseModel):
    fileName: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    contentType: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    sizeBytes: Annotated[int, Field(strict=True, gt=0)]


class MicrolessonVideoFinalizeRequest(MicrolessonVideoUploadRequest):
    blobPath: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]


@app.get('/api/master/clients')
@app.get('/v1/api/master/clients')
def master_clients(user: dict = Depends(verify_token)):
    with master_store.database(SQL_CONN_STR) as cursor:
        master_store.resolve_user(cursor, user, master=True)
        cursor.execute("SELECT id,name,status FROM dbo.client WHERE status='active' AND is_deleted=0 ORDER BY name,id")
        items = master_store.rows(cursor)
        for item in items:
            item['id'] = str(item['id'])
        return {"items": items}


@app.get('/api/master/topics')
@app.get('/v1/api/master/topics')
def master_topics(status: Literal['active', 'archived', 'all'] = 'active', user: dict = Depends(verify_token)):
    with master_store.database(SQL_CONN_STR) as cursor:
        master_store.resolve_user(cursor, user, master=True)
        cursor.execute("""SELECT t.id,t.name,t.context,t.optics,t.audience,t.status,
            (SELECT COUNT(*) FROM dbo.question q WHERE q.topic_id=t.id AND q.status='active' AND q.in_bank=1 AND q.is_deleted=0) AS questionCount
            FROM dbo.topic t WHERE t.client_id IS NULL AND t.is_deleted=0 AND (?='all' OR t.status=?)
            ORDER BY t.created_at DESC,t.id""", status, status)
        topics = master_store.rows(cursor)
        for topic in topics:
            topic['id'] = str(topic['id'])
            scenarios = master_store.scenarios_for_topic(cursor, topic['id'])
            topic['scenarioCount'] = sum(s['status'] == 'active' for s in scenarios) if topic['status'] == 'active' else 0
            topic['clients'] = list({s['clientId']: {'id': s['clientId'], 'name': s['clientName']} for s in scenarios if s['status'] == 'active' and topic['status'] == 'active'}.values())
        return {'items': topics, 'total': len(topics)}


@app.get('/api/master/topics/{topic_id}')
@app.get('/v1/api/master/topics/{topic_id}')
def master_topic_detail(topic_id: uuid.UUID, user: dict = Depends(verify_token)):
    with master_store.database(SQL_CONN_STR) as cursor:
        master_store.resolve_user(cursor, user, master=True)
        return master_store.topic_detail(cursor, str(topic_id))


@app.post('/api/master/topics', status_code=201)
@app.post('/v1/api/master/topics', status_code=201)
def master_create_topic(payload: MasterTopicRequest, user: dict = Depends(verify_token)):
    if any(q.id for q in payload.questions):
        raise HTTPException(422, 'Las preguntas de un tema nuevo deben crearse sin id.')
    with master_store.database(SQL_CONN_STR) as cursor:
        master_store.resolve_user(cursor, user, master=True)
        topic_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO dbo.topic(id,client_id,name,context,optics,audience,status) VALUES(?,NULL,?,?,?,?,'active')", topic_id, payload.name, payload.context, payload.optics, payload.audience)
        master_store.save_messages(cursor, topic_id, 'topic_key_message', payload.keyMessages)
        master_store.save_messages(cursor, topic_id, 'topic_red_line', payload.redLines)
        master_store.save_questions(cursor, topic_id, payload.questions)
        return master_store.topic_detail(cursor, topic_id)


@app.put('/api/master/topics/{topic_id}')
@app.put('/v1/api/master/topics/{topic_id}')
def master_update_topic(topic_id: uuid.UUID, payload: MasterTopicRequest, user: dict = Depends(verify_token)):
    with master_store.database(SQL_CONN_STR) as cursor:
        master_store.resolve_user(cursor, user, master=True)
        topic_id = str(topic_id)
        master_store.require_topic(cursor, topic_id, lock=True)
        cursor.execute("UPDATE dbo.topic SET name=?,context=?,optics=?,audience=?,updated_at=SYSUTCDATETIME() WHERE id=?", payload.name, payload.context, payload.optics, payload.audience, topic_id)
        master_store.save_messages(cursor, topic_id, 'topic_key_message', payload.keyMessages)
        master_store.save_messages(cursor, topic_id, 'topic_red_line', payload.redLines)
        master_store.save_questions(cursor, topic_id, payload.questions)
        return master_store.topic_detail(cursor, topic_id)


@app.patch('/api/master/topics/{topic_id}/status')
@app.patch('/v1/api/master/topics/{topic_id}/status')
def master_topic_status(topic_id: uuid.UUID, payload: MasterStatusRequest, user: dict = Depends(verify_token)):
    with master_store.database(SQL_CONN_STR) as cursor:
        master_store.resolve_user(cursor, user, master=True)
        topic_id = str(topic_id)
        master_store.require_topic(cursor, topic_id, lock=True)
        cursor.execute("UPDATE dbo.topic SET status=?,updated_at=SYSUTCDATETIME() WHERE id=?", payload.status, topic_id)
        cursor.execute("UPDATE dbo.scenario SET status=?,updated_at=SYSUTCDATETIME() WHERE topic_id=? AND is_deleted=0", payload.status, topic_id)
        return master_store.topic_detail(cursor, topic_id)


@app.post('/api/master/topics/{topic_id}/scenarios', status_code=201)
@app.post('/v1/api/master/topics/{topic_id}/scenarios', status_code=201)
def master_create_scenario(topic_id: uuid.UUID, payload: MasterScenarioRequest, user: dict = Depends(verify_token)):
    with master_store.database(SQL_CONN_STR) as cursor:
        master_store.resolve_user(cursor, user, master=True)
        return master_store.save_scenario(cursor, str(topic_id), payload)


@app.put('/api/master/scenarios/{scenario_id}')
@app.put('/v1/api/master/scenarios/{scenario_id}')
def master_update_scenario(scenario_id: uuid.UUID, payload: MasterScenarioRequest, user: dict = Depends(verify_token)):
    with master_store.database(SQL_CONN_STR) as cursor:
        master_store.resolve_user(cursor, user, master=True)
        scenario_id = str(scenario_id)
        topic_id = master_store.scenario_topic(cursor, scenario_id)
        return master_store.save_scenario(cursor, topic_id, payload, scenario_id)


@app.patch('/api/master/scenarios/{scenario_id}/status')
@app.patch('/v1/api/master/scenarios/{scenario_id}/status')
def master_scenario_status(scenario_id: uuid.UUID, payload: MasterStatusRequest, user: dict = Depends(verify_token)):
    with master_store.database(SQL_CONN_STR) as cursor:
        master_store.resolve_user(cursor, user, master=True)
        scenario_id = str(scenario_id)
        topic_id = master_store.scenario_topic(cursor, scenario_id)
        topic_status = master_store.require_topic(cursor, topic_id, lock=True)
        if payload.status == 'active' and topic_status != 'active':
            raise HTTPException(409, 'Reactiva el tema antes de reactivar el escenario.')
        cursor.execute("UPDATE dbo.scenario SET status=?,updated_at=SYSUTCDATETIME() WHERE id=?", payload.status, scenario_id)
        return next(s for s in master_store.scenarios_for_topic(cursor, topic_id) if s['id'].lower() == scenario_id)


# Microlecciones. El maestro administra; el vocero solo lee contenido visible
# de su empresa y la misma regla de escenarios usada por el catalogo.
@app.get('/api/master/microlessons/clients')
@app.get('/v1/api/master/microlessons/clients')
def master_microlesson_clients(
    status: Literal['active', 'archived', 'all'] = 'all',
    user: dict = Depends(verify_token),
):
    return microlesson_store.clients(SQL_CONN_STR, user, status)


@app.get('/api/master/microlessons/clients/{client_id}/scenarios')
@app.get('/v1/api/master/microlessons/clients/{client_id}/scenarios')
def master_microlesson_scenarios(
    client_id: uuid.UUID,
    status: Literal['active', 'archived', 'all'] = 'active',
    user: dict = Depends(verify_token),
):
    return microlesson_store.scenarios_for_client(SQL_CONN_STR, user, str(client_id), status)


@app.get('/api/master/microlessons')
@app.get('/v1/api/master/microlessons')
def master_microlessons(
    clientId: uuid.UUID | None = None,
    status: Literal['active', 'archived', 'all'] = 'all',
    user: dict = Depends(verify_token),
):
    return microlesson_store.list_master(SQL_CONN_STR, user, str(clientId) if clientId else None, status)


@app.get('/api/master/microlessons/{microlesson_id}')
@app.get('/v1/api/master/microlessons/{microlesson_id}')
def master_microlesson_detail(microlesson_id: uuid.UUID, user: dict = Depends(verify_token)):
    return microlesson_store.get_master(SQL_CONN_STR, user, str(microlesson_id))


@app.post('/api/master/microlessons', status_code=201)
@app.post('/v1/api/master/microlessons', status_code=201)
def master_create_microlesson(payload: MicrolessonRequest, user: dict = Depends(verify_token)):
    return microlesson_store.save(SQL_CONN_STR, user, payload)


@app.put('/api/master/microlessons/{microlesson_id}')
@app.put('/v1/api/master/microlessons/{microlesson_id}')
def master_update_microlesson(
    microlesson_id: uuid.UUID,
    payload: MicrolessonRequest,
    user: dict = Depends(verify_token),
):
    return microlesson_store.save(SQL_CONN_STR, user, payload, str(microlesson_id))


@app.patch('/api/master/microlessons/{microlesson_id}/status')
@app.patch('/v1/api/master/microlessons/{microlesson_id}/status')
def master_microlesson_status(
    microlesson_id: uuid.UUID,
    payload: MasterStatusRequest,
    user: dict = Depends(verify_token),
):
    return microlesson_store.set_status(SQL_CONN_STR, user, str(microlesson_id), payload.status)


_VIDEO_MIME_BY_EXTENSION = {
    '.mp4': {'video/mp4'},
    '.webm': {'video/webm'},
    '.mov': {'video/quicktime'},
}


def _validated_video(file_name: str, content_type: str, size_bytes: int):
    safe_source = re.split(r'[\\/]', file_name)[-1].strip()
    extension = os.path.splitext(safe_source)[1].lower()
    normalized_type = content_type.split(';', 1)[0].strip().lower()
    if extension not in _VIDEO_MIME_BY_EXTENSION or normalized_type not in _VIDEO_MIME_BY_EXTENSION[extension]:
        raise HTTPException(422, 'El video debe ser MP4, WebM o MOV y su MIME debe coincidir con la extension.')
    if size_bytes > MICROLESSON_VIDEO_MAX_BYTES:
        raise HTTPException(413, f'El video supera el limite de {MICROLESSON_VIDEO_MAX_BYTES // (1024 * 1024)} MB.')
    stem = os.path.splitext(safe_source)[0]
    stem = re.sub(r'[^A-Za-z0-9._-]+', '-', stem).strip('._-')[:120] or 'video'
    return f'{stem}{extension}', normalized_type


def _blob_service():
    if not STORAGE_CONN_STR:
        raise HTTPException(503, 'Azure Blob Storage no esta configurado.')
    try:
        return BlobServiceClient.from_connection_string(STORAGE_CONN_STR)
    except Exception:
        raise HTTPException(503, 'No se pudo conectar con Azure Blob Storage.') from None


def _delete_blob(blob_path: str | None):
    if not blob_path or not STORAGE_CONN_STR:
        return
    try:
        _blob_service().get_container_client(CONTAINER_NAME).delete_blob(blob_path, delete_snapshots='include')
    except Exception as error:
        logger.warning('No se pudo limpiar un video de microleccion en Blob Storage: %s', type(error).__name__)


def _playback_url(blob_path: str):
    service = _blob_service()
    try:
        blob = service.get_container_client(CONTAINER_NAME).get_blob_client(blob_path)
        if not blob.exists():
            raise HTTPException(404, 'El video no existe en Azure Blob Storage.')
        sas = generate_blob_sas(
            account_name=service.account_name,
            container_name=CONTAINER_NAME,
            blob_name=blob_path,
            account_key=service.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        return f'https://{service.account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_path}?{sas}'
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'No se pudo generar el acceso temporal al video.') from None


@app.post('/api/master/microlessons/{microlesson_id}/video-upload-url')
@app.post('/v1/api/master/microlessons/{microlesson_id}/video-upload-url')
def master_microlesson_video_upload_url(
    microlesson_id: uuid.UUID,
    payload: MicrolessonVideoUploadRequest,
    user: dict = Depends(verify_token),
):
    owner = microlesson_store.video_owner(SQL_CONN_STR, user, str(microlesson_id))
    safe_name, content_type = _validated_video(payload.fileName, payload.contentType, payload.sizeBytes)
    blob_path = f"microlessons/{owner['clientId']}/{owner['id']}/{uuid.uuid4()}-{safe_name}"
    service = _blob_service()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=30)
    try:
        sas = generate_blob_sas(
            account_name=service.account_name,
            container_name=CONTAINER_NAME,
            blob_name=blob_path,
            account_key=service.credential.account_key,
            permission=BlobSasPermissions(create=True, write=True),
            expiry=expiry,
        )
    except Exception:
        raise HTTPException(503, 'No se pudo preparar la subida del video.') from None
    return {
        'uploadUrl': f'https://{service.account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_path}?{sas}',
        'blobPath': blob_path,
        'fileName': safe_name,
        'contentType': content_type,
        'expiresAt': expiry.isoformat(),
        'maxSizeBytes': MICROLESSON_VIDEO_MAX_BYTES,
    }


@app.put('/api/master/microlessons/{microlesson_id}/video')
@app.put('/v1/api/master/microlessons/{microlesson_id}/video')
def master_finalize_microlesson_video(
    microlesson_id: uuid.UUID,
    payload: MicrolessonVideoFinalizeRequest,
    user: dict = Depends(verify_token),
):
    owner = microlesson_store.video_owner(SQL_CONN_STR, user, str(microlesson_id))
    safe_name, content_type = _validated_video(payload.fileName, payload.contentType, payload.sizeBytes)
    expected_prefix = f"microlessons/{owner['clientId']}/{owner['id']}/"
    if not payload.blobPath.startswith(expected_prefix) or '..' in payload.blobPath:
        raise HTTPException(422, 'La ruta del video no corresponde a esta microleccion.')
    service = _blob_service()
    try:
        properties = service.get_container_client(CONTAINER_NAME).get_blob_client(payload.blobPath).get_blob_properties()
        actual_size = int(properties.size)
        actual_type = (properties.content_settings.content_type or '').split(';', 1)[0].lower()
        if actual_size != payload.sizeBytes or actual_size > MICROLESSON_VIDEO_MAX_BYTES:
            raise HTTPException(422, 'El tamano del blob no coincide con el archivo declarado.')
        if actual_type != content_type:
            raise HTTPException(422, 'El tipo MIME almacenado no coincide con el video declarado.')
    except HTTPException:
        _delete_blob(payload.blobPath)
        raise
    except Exception:
        _delete_blob(payload.blobPath)
        raise HTTPException(422, 'No se encontro un video valido para confirmar.') from None
    try:
        old_path = microlesson_store.set_video(
            SQL_CONN_STR, user, str(microlesson_id), payload.blobPath,
            safe_name, content_type, payload.sizeBytes,
        )
    except Exception:
        _delete_blob(payload.blobPath)
        raise
    if old_path and old_path != payload.blobPath:
        _delete_blob(old_path)
    return microlesson_store.get_master(SQL_CONN_STR, user, str(microlesson_id))


@app.delete('/api/master/microlessons/{microlesson_id}/video')
@app.delete('/v1/api/master/microlessons/{microlesson_id}/video')
def master_remove_microlesson_video(microlesson_id: uuid.UUID, user: dict = Depends(verify_token)):
    old_path = microlesson_store.clear_video(SQL_CONN_STR, user, str(microlesson_id))
    _delete_blob(old_path)
    return microlesson_store.get_master(SQL_CONN_STR, user, str(microlesson_id))


@app.get('/api/master/microlessons/{microlesson_id}/video-url')
@app.get('/v1/api/master/microlessons/{microlesson_id}/video-url')
def master_microlesson_video_url(microlesson_id: uuid.UUID, user: dict = Depends(verify_token)):
    path = microlesson_store.playback_path(SQL_CONN_STR, user, str(microlesson_id), master=True)
    return {'playbackUrl': _playback_url(path), 'expiresIn': 3600}


@app.get('/microlessons')
@app.get('/v1/microlessons')
def spokesperson_microlessons(user: dict = Depends(verify_token)):
    return microlesson_store.list_spokesperson(SQL_CONN_STR, user)


@app.get('/microlessons/{microlesson_id}')
@app.get('/v1/microlessons/{microlesson_id}')
def spokesperson_microlesson_detail(microlesson_id: uuid.UUID, user: dict = Depends(verify_token)):
    return microlesson_store.get_spokesperson(SQL_CONN_STR, user, str(microlesson_id))


@app.get('/microlessons/{microlesson_id}/video-url')
@app.get('/v1/microlessons/{microlesson_id}/video-url')
def spokesperson_microlesson_video_url(microlesson_id: uuid.UUID, user: dict = Depends(verify_token)):
    path = microlesson_store.playback_path(SQL_CONN_STR, user, str(microlesson_id))
    return {'playbackUrl': _playback_url(path), 'expiresIn': 3600}

