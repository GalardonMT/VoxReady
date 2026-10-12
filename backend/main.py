import os
import json
import logging
import uuid
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
if DEV_AUTH and os.getenv("ENVIRONMENT", "production").lower() != "development":
    raise RuntimeError("DEV_AUTH solo se permite con ENVIRONMENT=development.")

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
        dev_email = os.getenv("DEV_AUTH_TEST_EMAIL", "").strip()
        if not dev_email:
            raise HTTPException(status_code=503, detail="DEV_AUTH_TEST_EMAIL no está configurado")
        return {
            "sub": "dev-user-001",
            "oid": "dev-user-001",
            "name": "Dev User",
            "email": dev_email,
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
                logger.warning("Validación con firma JWKS falló: %s", type(e_jwks).__name__)
                raise HTTPException(status_code=401, detail="Token inválido") from None

        raise HTTPException(status_code=401, detail="Error validando token con Microsoft")
    except HTTPException:
        raise
    except Exception as error:
        logger.warning("JWT verification failed: %s", type(error).__name__)
        raise HTTPException(status_code=401, detail="Token inválido") from None


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
    """Resuelve únicamente usuarios activos y preasignados en app_user."""
    if not SQL_CONN_STR:
        raise HTTPException(status_code=503, detail="Azure SQL no está configurado")

    user_uuid = _safe_uuid(user_id)
    clean_email = email.strip() if email else ""
    if not user_uuid and not clean_email:
        raise HTTPException(status_code=403, detail="Usuario no registrado en VoxReady")

    try:
        conn_str = _normalize_sql_conn_str(SQL_CONN_STR)
        with pyodbc.connect(conn_str, timeout=10) as conn:
            cursor = conn.cursor()
            row = None
            if user_uuid:
                cursor.execute(
                    "SELECT id, client_id, email, display_name, role, preferred_language FROM dbo.app_user WHERE id = ? AND (is_deleted IS NULL OR is_deleted = 0)",
                    (user_uuid,)
                )
                row = cursor.fetchone()
            if not row and clean_email:
                cursor.execute(
                    "SELECT TOP 2 id, client_id, email, display_name, role, preferred_language FROM dbo.app_user WHERE LOWER(email) = LOWER(?) AND (is_deleted IS NULL OR is_deleted = 0)",
                    (clean_email,)
                )
                matches = cursor.fetchall()
                if len(matches) == 1:
                    row = matches[0]
            if row is None:
                raise HTTPException(status_code=403, detail="Usuario no registrado en VoxReady")
            user_data = dict(zip((c[0].lower() for c in cursor.description), row))
            if clean_email and user_data.get("email") and user_data["email"].lower() != clean_email.lower():
                raise HTTPException(status_code=403, detail="La identidad no coincide con el usuario preasignado")
            if user_data.get("role") not in ("spokesperson", "client_admin", "master_config"):
                raise HTTPException(status_code=403, detail="El usuario no tiene un rol válido")
            if user_data["role"] != "master_config" and not user_data.get("client_id"):
                raise HTTPException(status_code=403, detail="El usuario no tiene una empresa asignada")
            return user_data
    except HTTPException:
        raise
    except pyodbc.Error:
        logger.exception("Azure SQL no disponible al resolver app_user")
        raise HTTPException(status_code=503, detail="No se pudo consultar el usuario en Azure SQL") from None

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
    """Obtiene el perfil preasignado; rol y empresa provienen de Azure SQL."""
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
    db_user = sync_or_get_user(
        user_id=str(user_id),
        email=email or "",
        display_name=display_name,
        client_id=None,
        token_role=None,
    )

    return {
        "userId": str(db_user["id"]),
        "email": db_user.get("email") or email,
        "displayName": db_user.get("display_name") or display_name,
        "role": db_user["role"],
        "clientId": str(db_user["client_id"]) if db_user.get("client_id") else None,
        "preferredLanguage": db_user.get("preferred_language") or user.get("preferredLanguage", "es"),
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
    spokesperson_store.require_session_access(SQL_CONN_STR, user, session_id)
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
    spokesperson_store.require_session_access(SQL_CONN_STR, user, session_id)
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
    spokesperson_store.require_session_access(SQL_CONN_STR, user, session_id, read_only=True)
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
    access = spokesperson_store.require_session_access(SQL_CONN_STR, user, session_id)
    session_uuid = access['id']
    job_id = str(uuid.uuid4())
    rubric_version_id = None
    blob_path = f"recordings/{session_id}.webm"
    if any(path and path != blob_path for path in (payload.blobPath, payload.video_blob_name)):
        raise HTTPException(422, "La ruta de grabación no corresponde a la sesión.")

    # 1. Gestionar estado y job en Azure SQL si está configurado
    if SQL_CONN_STR:
        try:
            conn_str = _normalize_sql_conn_str(SQL_CONN_STR)
            with pyodbc.connect(conn_str, timeout=10) as conn:
                cur = conn.cursor()
                cur.execute("""SELECT id, status, rubric_version_id FROM session
                               WHERE id=? AND user_id=? AND client_id=? AND is_deleted=0""",
                            session_uuid, access['profile']['id'], access['profile']['client_id'])
                session_row = cur.fetchone()
                if session_row is None:
                    raise HTTPException(404, "Sesión no encontrada.")
                rubric_version_id = session_row[2]

                # Crear registro en analysis_job
                cur.execute("""
                    INSERT INTO analysis_job (id, session_id, rubric_version_id, status, started_at, created_at, updated_at)
                    VALUES (?, ?, ?, 'running', SYSUTCDATETIME(), SYSUTCDATETIME(), SYSUTCDATETIME())
                """, (job_id, session_uuid, rubric_version_id))

                # Transicionar sesión a 'analyzing'
                cur.execute("""
                    UPDATE session 
                    SET status = 'analyzing', finished_at = SYSUTCDATETIME(), updated_at = SYSUTCDATETIME()
                    WHERE id = ? AND user_id = ? AND client_id = ? AND is_deleted = 0
                """, session_uuid, access['profile']['id'], access['profile']['client_id'])
                conn.commit()
                logger.info(f"Sesión {session_uuid} actualizada a 'analyzing' (Job: {job_id}) en Azure SQL.")
        except HTTPException:
            raise
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
                        "user_id": access['profile']['id'],
                        "scenario_id": access['scenario_id'],
                        "tenant_id": access['profile']['client_id'],
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
    access = spokesperson_store.require_session_access(SQL_CONN_STR, user, session_id, read_only=True)
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
            with pyodbc.connect(conn_str, timeout=10) as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT r.id, r.overall_score, r.narrative_strengths, r.narrative_improvements,
                           r.cross_signal_observation, r.generated_at, s.status as session_status
                    FROM report r
                    JOIN session s ON r.session_id = s.id
                    WHERE s.id = ? AND r.is_current = 1
                """, access['id'])
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

