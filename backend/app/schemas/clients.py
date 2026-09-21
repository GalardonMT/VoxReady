"""Request schemas for client admin (retention) endpoints."""
from typing import Literal

from pydantic import BaseModel


class RetentionPolicyIn(BaseModel):
    keep: Literal["full_recording", "metrics_only"]
    termDays: int | None = None
