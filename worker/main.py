import os
import sys
import logging

_worker_dir = os.path.dirname(os.path.abspath(__file__))
if _worker_dir not in sys.path:
    sys.path.insert(0, _worker_dir)

from fastapi import FastAPI, BackgroundTasks, status
from pydantic import BaseModel
from typing import List, Optional
try:
    from core.pipeline_orchestrator import process_session_pipeline
except (ImportError, ValueError):
    from worker.core.pipeline_orchestrator import process_session_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("ca-analysis-worker")

app = FastAPI(
    title="ca-analysis-worker",
    version="2.2.0",
    description="Servicio interno de inferencia multimodal y evaluación VISUM para VoxReady"
)


class TurnInterval(BaseModel):
    questionId: str
    sequenceNo: int
    startMs: int
    endMs: int


class JobRequest(BaseModel):
    sessionId: str
    jobId: str
    rubricVersionId: Optional[str] = None
    blobPath: str
    turns: Optional[List[TurnInterval]] = []


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "ca-analysis-worker",
        "version": "2.2.0"
    }


@app.post("/analyze", status_code=status.HTTP_202_ACCEPTED)
async def trigger_analysis(job: JobRequest, background_tasks: BackgroundTasks):
    """
    Recibe la orden de trabajo, responde 202 de inmediato para liberar al backend
    y procesa la inferencia multimodal en segundo plano (BackgroundTasks).
    Permite el autoescalado de 0 a 1 réplica en Azure Container Apps Express.
    """
    logger.info(f"Trabajo de análisis recibido para sesión: {job.sessionId} (Job ID: {job.jobId})")
    
    # Delegar la ejecución pesada en segundo plano
    background_tasks.add_task(
        process_session_pipeline,
        session_id=job.sessionId,
        job_id=job.jobId,
        rubric_version_id=job.rubricVersionId,
        blob_path=job.blobPath,
        turns=[t.model_dump() for t in (job.turns or [])]
    )
    
    return {
        "status": "accepted",
        "sessionId": job.sessionId,
        "jobId": job.jobId
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
