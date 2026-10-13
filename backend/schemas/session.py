# backend/schemas/session.py
from typing import List, Optional
from pydantic import BaseModel, Field, AliasChoices, field_validator


class TurnInterval(BaseModel):
    questionId: str = Field(default="q", validation_alias=AliasChoices('questionId', 'question_id'))
    sequenceNo: int = Field(default=1, validation_alias=AliasChoices('sequenceNo', 'sequence_no'))
    startMs: int = Field(default=0, validation_alias=AliasChoices('startMs', 'startOffsetMs', 'start_ms', 'start_offset_ms'))
    endMs: int = Field(default=0, validation_alias=AliasChoices('endMs', 'endOffsetMs', 'end_ms', 'end_offset_ms'))
    questionText: Optional[str] = Field(default=None, validation_alias=AliasChoices('questionText', 'question_text', 'text'))

    @field_validator("startMs", mode="before")
    @classmethod
    def parse_start_ms(cls, v):
        if v is None:
            return 0
        try:
            return int(round(float(v)))
        except (ValueError, TypeError):
            return 0

    @field_validator("endMs", mode="before")
    @classmethod
    def parse_end_ms(cls, v):
        if v is None:
            return 0
        try:
            return int(round(float(v)))
        except (ValueError, TypeError):
            return 0


class FinishSessionRequest(BaseModel):
    blobPath: Optional[str] = Field(default=None, description="Ruta relativa del archivo WebM en el storage")
    video_blob_name: Optional[str] = Field(default=None, description="Ruta para retrocompatibilidad")
    turns: Optional[List[TurnInterval]] = Field(default=[], description="Segmentación temporal por pregunta")
    question_marks: Optional[List[dict]] = Field(default=None, description="Marcas de tiempo por pregunta")
    scenario_id: Optional[str] = "crisis-voceria-01"
    tenant_id: Optional[str] = "tenant-voxready-dev"


class WorkerTriggerPayload(BaseModel):
    sessionId: str
    jobId: str
    rubricVersionId: Optional[str] = None
    blobPath: str
    turns: List[TurnInterval] = []
