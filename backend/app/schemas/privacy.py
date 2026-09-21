"""Request schemas for privacy (deletion requests)."""
from pydantic import BaseModel


class DeletionRequestIn(BaseModel):
    sessionId: str | None = None
    reason: str | None = None
