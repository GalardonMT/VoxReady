"""Request schema for the dev-only token endpoint."""
from pydantic import BaseModel


class DevTokenIn(BaseModel):
    email: str
