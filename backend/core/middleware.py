import time
import uuid
import logging
import json
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.responses import JSONResponse

logger = logging.getLogger("mdt.access")


class RequestSizeLimitMiddleware:
    """Bound buffered request bytes, including chunked bodies without Content-Length."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        from core.config import settings
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > settings.MAX_REQUEST_BYTES:
                return await JSONResponse({"detail": "Request body exceeds configured size limit"}, status_code=413)(scope, receive, send)
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        sent = False
        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)


class JSONLogFormatter(logging.Formatter):
    """Format log records as structured JSON for production observability."""
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_obj["request_id"] = record.request_id
        if hasattr(record, "latency_ms"):
            log_obj["latency_ms"] = record.latency_ms
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """
    Assigns unique X-Request-ID and tracks latency in milliseconds for every HTTP request.
    """
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"{request.method} {request.url.path} 500 Internal Error [{duration_ms:.2f}ms] (id={request_id}): {exc}",
                extra={"request_id": request_id, "latency_ms": round(duration_ms, 2)},
                exc_info=True
            )
            raise exc

        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-MS"] = f"{duration_ms:.2f}"

        # Skip spamming logs on healthcheck polls unless in error
        if request.url.path.rstrip("/") != "/health" or response.status_code >= 400:
            logger.info(
                f"{request.method} {request.url.path} {response.status_code} [{duration_ms:.2f}ms] (id={request_id})",
                extra={"request_id": request_id, "latency_ms": round(duration_ms, 2)}
            )

        return response
