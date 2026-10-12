"""Log JSON một dòng, luôn kèm mã tương quan. Không ghi khóa, không ghi nội dung prompt hay đầu ra."""
from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")

_EXTRA_FIELDS = (
    "api", "model", "inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens",
    "ms", "result", "status", "method", "path", "attempt", "problems", "stopReason", "errorCode",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlationId": correlation_id_var.get(),
        }
        for field in _EXTRA_FIELDS:
            if hasattr(record, field):
                data[field] = getattr(record, field)
        if record.exc_info and record.exc_info[0] is not None:
            # Chỉ ghi kiểu lỗi, không ghi chuỗi lỗi (có thể chứa nội dung yêu cầu).
            data["exception"] = record.exc_info[0].__name__
        return json.dumps(data, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    try:  # Cửa sổ Windows mặc định cp1252 không in được tiếng Việt
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpx2", "httpcore", "anthropic", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
