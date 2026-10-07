# backend/schemas/session.py
from typing import List, Optional
from pydantic import BaseModel, Field


class TurnInterval(BaseModel):
    questionId: str
    sequenceNo: int
    startMs: int
    endMs: int


class FinishSessionRequest(BaseModel):
    blobPath: Optional[str] = Field(default=None, description="Ruta relativa del archivo WebM en el storage")
    video_blob_name: Optional[str] = Field(default=None, description="Ruta para retrocompatibilidad")
    turns: Optional[List[TurnInterval]] = Field(default=[], description="Segmentación temporal por pregunta")
    scenario_id: Optional[str] = "crisis-voceria-01"
    tenant_id: Optional[str] = "tenant-voxready-dev"


class WorkerTriggerPayload(BaseModel):
    sessionId: str
    jobId: str
    rubricVersionId: Optional[str] = None
    blobPath: str
    turns: List[TurnInterval] = []
