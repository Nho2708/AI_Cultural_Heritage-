"""Bộ gọi Claude (SDK anthropic, async) cho Haiku 5.5.

Quy tắc của mô hình này: không gửi temperature, top_p, top_k; không prefill; không budget_tokens.
Suy nghĩ thích ứng bật sẵn nên đọc khối nội dung theo type và chừa chỗ trong max_tokens; độ sâu chỉnh bằng output_config.effort.
Đầu ra có cấu trúc dùng output_config.format (lược đồ JSON). Không ghi khóa hay nội dung prompt vào log.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from ..errors import ModelUnavailable, ServiceError

log = logging.getLogger("ai.llm")


@dataclass
class TokenUsage:
    """Số token đã dùng. input_tokens là phần không đọc từ bộ nhớ đệm; cache_* là phần đệm."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, other: "TokenUsage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens

    @property
    def total_input(self) -> int:
        """Tổng token vào theo hợp đồng (usage.inputTokens): cả phần đệm."""
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass
class LlmResult:
    data: Any | None
    usage: TokenUsage
    model: str
    truncated: bool = False
    parse_error: str | None = None
    stop_reason: str | None = None


class Llm(Protocol):
    model: str

    async def complete_json(
        self,
        *,
        api: str,
        system: str,
        user: str,
        schema: dict,
        effort: str,
        max_tokens: int,
        timeout: float,
    ) -> LlmResult: ...


def _extract_json(text: str) -> Any:
    """Lấy đối tượng JSON ngoài cùng khỏi đoạn chữ (bỏ khối mã Markdown nếu mô hình lỡ thêm)."""
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1] if start >= 0 and end > start else text)


def _usage_of(response: Any) -> TokenUsage:
    u = getattr(response, "usage", None)
    if u is None:
        return TokenUsage()
    return TokenUsage(
        input_tokens=int(getattr(u, "input_tokens", 0) or 0),
        output_tokens=int(getattr(u, "output_tokens", 0) or 0),
        cache_read_tokens=int(getattr(u, "cache_read_input_tokens", 0) or 0),
        cache_write_tokens=int(getattr(u, "cache_creation_input_tokens", 0) or 0),
    )


class AnthropicLlm:
    def __init__(self, client: Any | None, model: str):
        self._client = client
        self.model = model

    @classmethod
    def from_key(cls, api_key: str, model: str) -> "AnthropicLlm":
        # SDK tự đọc ANTHROPIC_AUTH_TOKEN nếu có và gửi cùng khóa API thì nhà cung cấp từ chối: bỏ khỏi môi trường của tiến trình này.
        os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
        # max_retries=0: việc thử lại do backend quyết định (tối đa 2 lần), tránh nhân đôi thời gian chờ.
        return cls(anthropic.AsyncAnthropic(api_key=api_key, max_retries=0), model)

    # Đầu ra có cấu trúc (output_config.format) là đường chính. Nếu nhà cung cấp từ chối lược đồ (400 nói về schema/format) thì chuyển
    # sang chế độ JSON thuần trong prompt cho các lời gọi sau; bộ kiểm đầu ra ở phía trên vẫn bảo đảm kết quả đúng lược đồ riêng.
    structured = True

    async def complete_json(
        self,
        *,
        api: str,
        system: str,
        user: str,
        schema: dict,
        effort: str,
        max_tokens: int,
        timeout: float,
    ) -> LlmResult:
        if self._client is None:
            raise ModelUnavailable(503, "llm_not_configured", "Dịch vụ AI chưa được cấu hình khóa mô hình.")
        started = time.perf_counter()
        response = None
        for _ in range(2):
            try:
                response = await self._client.messages.create(**self._params(system, user, schema, effort, max_tokens, timeout))
                break
            except anthropic.APITimeoutError as exc:
                self._log_failure(api, started, "timeout")
                raise ModelUnavailable(504, "llm_timeout", "Mô hình không trả lời kịp thời gian chờ.") from exc
            except anthropic.APIConnectionError as exc:
                self._log_failure(api, started, "connection")
                raise ModelUnavailable(503, "llm_unreachable", "Không kết nối được nhà cung cấp mô hình.") from exc
            except anthropic.RateLimitError as exc:
                self._log_failure(api, started, "rate_limited")
                raise ModelUnavailable(503, "llm_rate_limited", "Nhà cung cấp mô hình đang giới hạn tần suất.") from exc
            except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError) as exc:
                self._log_failure(api, started, f"not_ready_{exc.status_code}")
                raise ModelUnavailable(503, "llm_not_ready", "Dịch vụ AI chưa sẵn sàng (khóa hoặc mô hình chưa dùng được).") from exc
            except anthropic.BadRequestError as exc:
                detail = str(getattr(exc, "message", ""))
                self._log_failure(api, started, "bad_request", detail=detail[:300])
                lowered = detail.lower()
                if "credit balance" in lowered:  # hết số dư tài khoản nhà cung cấp: lỗi cấu hình, không phải lỗi yêu cầu
                    raise ModelUnavailable(503, "llm_billing", "Tài khoản nhà cung cấp mô hình hết số dư.") from exc
                if self.structured and any(k in lowered for k in ("schema", "output_config", "json_schema", "structured")):
                    log.warning("Nhà cung cấp từ chối lược đồ JSON: chuyển sang chế độ JSON thuần trong prompt", extra={"api": api})
                    self.structured = False
                    continue
                raise ModelUnavailable(502, "llm_bad_request", "Yêu cầu gửi mô hình bị từ chối.") from exc
            except anthropic.APIStatusError as exc:
                self._log_failure(api, started, f"status_{exc.status_code}")
                status = 503 if exc.status_code == 529 else 502
                raise ModelUnavailable(status, "llm_unavailable", "Nhà cung cấp mô hình đang lỗi hoặc quá tải.") from exc
        if response is None:  # hai lần đều bị từ chối lược đồ
            raise ModelUnavailable(502, "llm_bad_request", "Yêu cầu gửi mô hình bị từ chối.")

        usage = _usage_of(response)
        stop = getattr(response, "stop_reason", None)
        model = getattr(response, "model", None) or self.model
        if stop == "refusal":
            log.warning(
                "Mô hình từ chối",
                extra={"api": api, "model": model, "stopReason": stop, "inputTokens": usage.total_input, "outputTokens": usage.output_tokens},
            )
            raise ServiceError(422, "model_refused", "Mô hình từ chối xử lý nội dung này.")
        if stop == "max_tokens":
            return LlmResult(None, usage, model, truncated=True, stop_reason=stop)

        text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
        if text is None:
            return LlmResult(None, usage, model, parse_error="Mô hình không trả khối chữ nào.", stop_reason=stop)
        try:
            return LlmResult(json.loads(text) if self.structured else _extract_json(text), usage, model, stop_reason=stop)
        except json.JSONDecodeError:
            return LlmResult(None, usage, model, parse_error="Đầu ra không phải JSON hợp lệ.", stop_reason=stop)

    def _params(self, system: str, user: str, schema: dict, effort: str, max_tokens: int, timeout: float) -> dict[str, Any]:
        output_config: dict[str, Any] = {"effort": effort}
        if self.structured:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        else:
            system = (
                f"{system}\n\nTrả về DUY NHẤT một đối tượng JSON hợp lệ đúng lược đồ JSON sau, không kèm chữ nào khác, không dùng khối mã:\n"
                f"{json.dumps(schema, ensure_ascii=False, separators=(',', ':'))}"
            )
        return {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}],
            "output_config": output_config,
            "timeout": timeout,
        }

    @staticmethod
    def _log_failure(api: str, started: float, result: str, detail: str | None = None) -> None:
        extra: dict[str, Any] = {"api": api, "result": result, "ms": int((time.perf_counter() - started) * 1000)}
        if detail:
            extra["problems"] = detail
        log.warning("Gọi mô hình lỗi", extra=extra)
