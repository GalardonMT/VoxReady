"""VoxReady API - FastAPI application entrypoint."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.config import get_settings
from app.core.correlation import CorrelationMiddleware
from app.core.errors import register_exception_handlers
from app.core.storage import init_storage
from app.services.analysis_worker import AnalysisWorker
from app.services.retention_job import RetentionJob

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_storage(settings)
    worker = AnalysisWorker(settings)
    retention = RetentionJob(settings)
    app.state.analysis_worker = worker
    app.state.retention_job = retention
    if settings.enable_analysis_worker:
        await worker.start()
    if settings.enable_retention_job:
        await retention.start()
    yield
    await worker.stop()
    await retention.stop()


app = FastAPI(
    title="VoxReady API",
    version="1.0.0",
    description="Plataforma SaaS multi-tenant de entrenamiento de vocería de crisis.",
    lifespan=lifespan,
)

# CORS — allow the frontend to call the API cross-origin
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(CorrelationMiddleware)
register_exception_handlers(app)
app.include_router(v1_router, prefix="/v1")


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}
