"""RFC 7807 Problem Details error model and exception handlers."""
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

ERROR_BASE_URL = "https://api.voxready.io/errors/"


class AppError(Exception):
    """Domain error carrying HTTP status and a spec-defined error code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.errors = errors or []


def problem_payload(
    request: Request,
    status_code: int,
    code: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "type": f"{ERROR_BASE_URL}{code}",
        "title": code,
        "status": status_code,
        "detail": detail,
        "correlationId": getattr(request.state, "correlation_id", None),
        "errors": errors or [],
    }


def problem_response(
    request: Request,
    status_code: int,
    code: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=problem_payload(request, status_code, code, detail, errors),
        media_type="application/problem+json",
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return problem_response(request, exc.status_code, exc.code, exc.detail, exc.errors)


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Topic endpoints use "validation_error" per spec; the rest "invalid_request".
    code = (
        "validation_error"
        if request.url.path.startswith("/v1/topics")
        else "invalid_request"
    )
    errors = [
        {
            "field": ".".join(str(p) for p in e.get("loc", []) if p != "body") or "body",
            "message": e.get("msg", "inválido"),
        }
        for e in exc.errors()
    ]
    return problem_response(
        request, 400, code, "La solicitud contiene campos inválidos.", errors
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return problem_response(
        request, 500, "internal_error", "Error no controlado del servidor."
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
