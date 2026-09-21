"""Aggregate /v1 router."""
from fastapi import APIRouter

from app.api.v1 import (
    clients,
    dev_auth,
    identity,
    master,
    microlessons,
    privacy,
    progress,
    scenarios,
    schedule,
    sessions,
    topics,
    uploads,
)

router = APIRouter()
for module in (
    identity,
    scenarios,
    sessions,
    progress,
    microlessons,
    schedule,
    privacy,
    topics,
    clients,
    master,
    uploads,
    dev_auth,
):
    router.include_router(module.router)
