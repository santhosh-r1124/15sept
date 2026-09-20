"""Application error hierarchy and FastAPI exception handlers.

Every non-2xx response uses one JSON envelope (mirrored in
``@legal-platform/shared`` as ``ApiError``)::

    {
      "error": {
        "code": "not_found",
        "message": "Advocate not found",
        "details": [{"field": "body.email", "message": "value is not a valid email address"}],
        "request_id": "0f9c…"
      }
    }
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger("app.errors")


class AppError(Exception):
    """Base class for expected, domain-level failures.

    Raise these from routers/services; the handler turns them into the standard
    envelope. Unexpected exceptions become a generic 500.
    """

    code: str = "internal_error"
    message: str = "An unexpected error occurred."
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: list[dict[str, str]] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "not_found"
    message = "Resource not found."
    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(AppError):
    code = "conflict"
    message = "The request conflicts with the current state."
    status_code = status.HTTP_409_CONFLICT


class UnauthorizedError(AppError):
    code = "unauthorized"
    message = "Authentication is required."
    status_code = status.HTTP_401_UNAUTHORIZED


class ForbiddenError(AppError):
    code = "forbidden"
    message = "You do not have permission to perform this action."
    status_code = status.HTTP_403_FORBIDDEN


class ValidationAppError(AppError):
    code = "validation_error"
    message = "The request payload is invalid."
    status_code = 422


class ServiceUnavailableError(AppError):
    code = "service_unavailable"
    message = "A downstream dependency is unavailable."
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class RateLimitedError(AppError):
    code = "rate_limited"
    message = "Too many requests. Please slow down and try again shortly."
    status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(self, *, retry_after: int, message: str | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else "-"


def build_error_body(
    *,
    code: str,
    message: str,
    request_id: str,
    details: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if details:
        error["details"] = details
    return {"error": error}


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    retry_after = getattr(exc, "retry_after", None)
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_body(
            code=exc.code,
            message=exc.message,
            request_id=_request_id(request),
            details=exc.details,
        ),
        headers={"Retry-After": str(retry_after)} if retry_after is not None else None,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=build_error_body(
            code="validation_error",
            message="The request payload is invalid.",
            request_id=_request_id(request),
            details=details,
        ),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    code = {
        status.HTTP_401_UNAUTHORIZED: "unauthorized",
        status.HTTP_403_FORBIDDEN: "forbidden",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
        status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
    }.get(exc.status_code, "http_error")
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_body(code=code, message=message, request_id=_request_id(request)),
        headers=getattr(exc, "headers", None),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        request_id=_request_id(request),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=build_error_body(
            code="internal_error",
            message="An unexpected error occurred.",
            request_id=_request_id(request),
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
