"""One error shape for every failure: {"error": {"code": "...", "message": "...", "details": ...}}."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

log = get_logger(__name__)


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None,
                 details: Any = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.headers, self.details = status, code, message, headers, details


def unauthorized(message: str = "Not authenticated", code: str = "unauthorized") -> AppError:
    return AppError(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status, headers=exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]
        return JSONResponse(_body("validation_error", "Invalid request", details), status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        """Any bug: the same error shape and a request id to quote; the stack trace goes to the logs only."""
        request_id = getattr(request.state, "request_id", None)
        log.error("unhandled_error", path=request.url.path, method=request.method, request_id=request_id,
                  error=type(exc).__name__, exc_info=exc)
        return JSONResponse(_body("internal_error", "Something went wrong on our side. Please try again.",
                                  {"request_id": request_id}), status_code=500,
                            headers={"X-Request-ID": request_id} if request_id else None)
