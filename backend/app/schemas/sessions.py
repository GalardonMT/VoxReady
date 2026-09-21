"""Request schemas for the session flow."""
from pydantic import BaseModel


class SessionCreateIn(BaseModel):
    scenarioId: str
    language: str | None = None


class ConsentIn(BaseModel):
    acceptRecording: bool
    acknowledgeDeletion: bool
    policyVersion: str


class RecordingUrlIn(BaseModel):
    contentType: str
    durationSeconds: int | None = None


class FinishIn(BaseModel):
    blobPath: str
