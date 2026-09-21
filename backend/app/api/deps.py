"""Shared API dependencies: pagination and UUID parsing."""
import uuid
from typing import NamedTuple

from app.core.errors import AppError


class Pagination(NamedTuple):
    page: int
    page_size: int
    offset: int


def pagination_params(page: int = 1, pageSize: int = 20) -> Pagination:
    """Validate page/pageSize per spec (pageSize 1-100, default 20)."""
    if page < 1 or pageSize < 1 or pageSize > 100:
        raise AppError(
            400, "invalid_query", "Parámetros de filtro o paginación inválidos."
        )
    return Pagination(page=page, page_size=pageSize, offset=(page - 1) * pageSize)


def to_uuid(value: str, error_code: str) -> uuid.UUID:
    """Parse a UUID path/body value or raise the endpoint's 404 code."""
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise AppError(404, error_code, "El recurso indicado no existe.")
