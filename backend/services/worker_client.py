import os
import logging
import httpx
try:
    from schemas.session import WorkerTriggerPayload
except (ImportError, ValueError):
    from backend.schemas.session import WorkerTriggerPayload

logger = logging.getLogger(__name__)

WORKER_INTERNAL_URL = os.getenv("WORKER_INTERNAL_URL", "").strip()
INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "").strip()


async def trigger_worker_analysis(payload: WorkerTriggerPayload) -> bool:
    """
    Envía la señal de inicio de análisis al worker mediante HTTP interno.
    La llamada despertará el contenedor de 0 a 1 réplica.
    """
    if not WORKER_INTERNAL_URL:
        logger.error("WORKER_INTERNAL_URL no está configurada.")
        return False
    if len(INTERNAL_SERVICE_TOKEN) < 32:
        logger.error("INTERNAL_SERVICE_TOKEN no está configurado o es demasiado corto.")
        return False

    try:
        # Timeout de 45s total y 30s de conexión para absorber el arranque en frío (cold-start) de ACA
        timeout = httpx.Timeout(45.0, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.post(
                WORKER_INTERNAL_URL,
                json=payload.model_dump(),
                headers={
                    "Content-Type": "application/json",
                    "X-VoxReady-Service-Token": INTERNAL_SERVICE_TOKEN,
                },
            )
            if response.status_code == 202:
                logger.info(f"Worker activado exitosamente para la sesión {payload.sessionId} (Job: {payload.jobId})")
                return True
            else:
                logger.error("Worker respondió con estado inesperado %s.", response.status_code)
                return False
    except httpx.RequestError as exc:
        logger.error("Error de red contactando al worker interno: %s", type(exc).__name__)
        return False
