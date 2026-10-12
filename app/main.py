"""Dịch vụ AI nội bộ của DSVHVN (FastAPI). Backend gọi một chiều, dịch vụ không truy cập CSDL."""
from __future__ import annotations

import hmac
import logging
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api.routes import router
from .config import Settings, get_settings
from .errors import ServiceError
from .llm.client import Llm
from .llm.factory import build_llm
from .logging_setup import correlation_id_var, setup_logging

log = logging.getLogger("ai.http")
_CID = re.compile(r"[^A-Za-z0-9._\-]")
KEY_HEADER = "x-internal-key"
CORRELATION_HEADER = "X-Correlation-Id"


def _error(status: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    body: dict = {"errorCode": code, "message": message, "correlationId": correlation_id_var.get()}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content=body)


def _key_ok(provided: str | None, expected: str) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def create_app(settings: Settings | None = None, llm: Llm | None = None, *, configure_logging: bool = True) -> FastAPI:
    settings = settings or get_settings()
    if configure_logging:
        setup_logging(settings.ai_log_level)
    if not settings.internal_key_value():
        raise RuntimeError(
            "Thiếu AI_INTERNAL_KEY (khóa nội bộ giữa backend và dịch vụ AI). Đặt trong .env hoặc %APPDATA%\\DSVHVN\\ai-service.env."
        )
    if llm is None:
        llm = build_llm(settings)
        if not settings.llm_configured():
            missing = "GEMINI_API_KEY" if settings.ai_provider == "gemini" else "ANTHROPIC_API_KEY"
            log.warning(f"Chưa có {missing}: các API dùng mô hình sẽ trả 503, rank-related vẫn chạy.")

    app = FastAPI(title="DSVHVN AI Service", version="1.0.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.llm = llm
    expected_key = settings.internal_key_value()

    @app.middleware("http")
    async def gate(request: Request, call_next):
        raw = request.headers.get(CORRELATION_HEADER, "")
        cid = _CID.sub("", raw)[:64] or uuid.uuid4().hex
        token = correlation_id_var.set(cid)
        started = time.perf_counter()
        try:
            if request.url.path.startswith("/v1/") and not _key_ok(request.headers.get(KEY_HEADER), expected_key):
                response = _error(401, "invalid_internal_key", "Thiếu hoặc sai khóa nội bộ.")
            else:
                try:
                    response = await call_next(request)
                except Exception as exc:  # noqa: BLE001 - lỗi ngoài dự kiến: chỉ ghi kiểu lỗi, không ghi nội dung
                    log.error("Lỗi không xử lý được", extra={"errorCode": type(exc).__name__})
                    response = _error(500, "internal_error", "Lỗi nội bộ của dịch vụ AI.")
            response.headers[CORRELATION_HEADER] = cid
            log.info(
                "Yêu cầu",
                extra={"method": request.method, "path": request.url.path, "status": response.status_code,
                       "ms": int((time.perf_counter() - started) * 1000)},
            )
            return response
        finally:
            correlation_id_var.reset(token)

    @app.exception_handler(ServiceError)
    async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
        log.warning("Trả lỗi", extra={"status": exc.status, "errorCode": exc.code})
        return _error(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Chỉ trả đường dẫn trường và lý do chung, không lặp lại giá trị người gọi gửi.
        details = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]} for e in exc.errors()][:20]
        return _error(422, "invalid_request", "Yêu cầu không đúng lược đồ.", details)

    app.include_router(router)
    return app
