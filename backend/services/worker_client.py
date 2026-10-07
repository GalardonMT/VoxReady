import os
import logging
import httpx
try:
    from schemas.session import WorkerTriggerPayload
except (ImportError, ValueError):
    from backend.schemas.session import WorkerTriggerPayload

logger = logging.getLogger(__name__)

WORKER_INTERNAL_URL = os.getenv(
    "WORKER_INTERNAL_URL",
    "https://ca-analysis-worker.wittywater-6601cc91.westus.azurecontainerapps.io/analyze"
)


async def trigger_worker_analysis(payload: WorkerTriggerPayload) -> bool:
    """
    Envía la señal de inicio de análisis al worker mediante HTTP interno.
    La llamada despertará el contenedor de 0 a 1 réplica.
    """
    try:
        # Se establece un timeout de 30 segundos y verify=False para absorber el cold-start y certs internos de ACA
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            response = await client.post(
                WORKER_INTERNAL_URL,
                json=payload.model_dump(),
                headers={"Content-Type": "application/json"}
            )
            if response.status_code == 202:
                logger.info(f"Worker activado exitosamente para la sesión {payload.sessionId} (Job: {payload.jobId})")
                return True
            else:
                logger.error(f"Worker respondió con estado inesperado {response.status_code}: {response.text}")
                return False
    except httpx.RequestError as exc:
        logger.error(f"Error de red contactando al worker interno ({WORKER_INTERNAL_URL}): {str(exc)}")
        return False
