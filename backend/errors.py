"""Consistent error responses: {"error": {"code", "message", "details"?}}.

Messages are written by our code and never include stack traces, file paths, credentials or
data values. Unexpected exceptions are logged by type only and answered with a generic 500.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.database.component_3_artifacts import StorageError
from backend.services.component_3.service import ArtifactUnavailable, IdentifierLeak, InvalidParameter, NotFound

log = logging.getLogger("backend.api")


def error(status: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    body = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body})


def install(app: FastAPI) -> None:
    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound):
        return error(404, "not_found", str(exc))

    @app.exception_handler(ArtifactUnavailable)
    async def _unavailable(_: Request, exc: ArtifactUnavailable):
        return error(404, "artifact_unavailable", str(exc))

    @app.exception_handler(InvalidParameter)
    async def _invalid(_: Request, exc: InvalidParameter):
        return error(422, "invalid_parameter", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [{"location": ".".join(str(p) for p in e.get("loc", ())), "message": e.get("msg", "invalid")}
                   for e in exc.errors()]
        return error(422, "invalid_parameter", "request parameters are invalid", details)

    @app.exception_handler(StorageError)
    async def _storage(_: Request, exc: StorageError):
        log.warning("storage error: %s", exc)
        return error(503, "storage_unavailable", "research artifacts could not be read; try again later")

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = "not_found" if exc.status_code == 404 else "invalid_parameter" if exc.status_code < 500 \
            else "internal_error"
        return error(exc.status_code, code, "resource not found" if exc.status_code == 404 else str(exc.detail))

    @app.exception_handler(IdentifierLeak)
    async def _leak(_: Request, exc: IdentifierLeak):
        log.error("response blocked: it would have contained commenter identifiers")
        return error(500, "internal_error", "an internal error occurred")

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        log.error("unexpected error: %s", type(exc).__name__)
        return error(500, "internal_error", "an internal error occurred")
