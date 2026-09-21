"""Request schemas for topics (client admin)."""
from typing import Literal

from pydantic import BaseModel, Field


class TopicIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    context: str = Field(min_length=1)
    optics: Literal["empathetic", "formal", "technical"]
    audience: str = Field(min_length=1, max_length=50)
    languages: list[Literal["es", "en", "pt"]] = Field(min_length=1)
    keyMessages: list[str] = Field(min_length=1)
    redLines: list[str] = Field(default_factory=list)
