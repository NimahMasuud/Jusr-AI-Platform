import logging
import uuid
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}

def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)

def error_response(request: Request, status_code: int, code: str, message: str,
                   details: dict | None = None, headers: dict | None = None) -> JSONResponse:
    body = {
        "success": False,
        "error": {"code": code, "message": message, "details": details or {}},
        "meta": {"requestId": _request_id(request)},
    }
    return JSONResponse(status_code=status_code, content=body, headers=headers)

def register_error_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            code = str(detail["code"])
            message = str(detail.get("message", ""))
            details = {k: v for k, v in detail.items() if k not in ("code", "message")}
        else:
            code = STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
            message = detail if isinstance(detail, str) else str(detail)
            details = {}
        return error_response(request, exc.status_code, code, message, details, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        issues = [
            {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return error_response(request, 422, "VALIDATION_ERROR", "Request validation failed", {"errors": issues})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error (requestId=%s)", _request_id(request))
        return error_response(request, 500, "INTERNAL_ERROR", "Internal server error")
