"""Request schemas for master configuration endpoints."""
from pydantic import BaseModel, Field


class RubricAreaIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    channel: str = Field(min_length=1, max_length=60)
    criteria: str = Field(min_length=1, max_length=500)
    weight: int
    descriptors: dict[str, str]


class RubricDraftIn(BaseModel):
    areas: list[RubricAreaIn] = Field(min_length=1)
    languages: list[str] = Field(default_factory=list)


class RubricPublishIn(BaseModel):
    version: str
    reevaluate: bool = False


class AreaScoreIn(BaseModel):
    area: str
    value: int


class ResolveCaseIn(BaseModel):
    scores: list[AreaScoreIn] = Field(min_length=1)
    comment: str | None = None
