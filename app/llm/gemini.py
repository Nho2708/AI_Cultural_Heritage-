"""Bộ gọi Gemini (REST generateContent của Google AI Studio, httpx async) theo cùng giao diện Llm với bộ gọi Claude.

Đầu ra có cấu trúc dùng generationConfig.responseJsonSchema (lược đồ JSON, nhận anyOf, enum, additionalProperties, null);
nhà cung cấp từ chối lược đồ thì chuyển sang JSON thuần trong prompt như bộ gọi Claude. Độ sâu suy nghĩ đặt bằng
thinkingConfig.thinkingLevel; token suy nghĩ tính vào maxOutputTokens. Khóa gửi ở tiêu đề x-goog-api-key, không bao giờ nằm trong URL hay log.

Bản miễn phí giới hạn số lượt theo TỪNG mô hình (vd 20 lượt mỗi ngày cho gemini-3.8-flash) và hay báo quá tải. Vì vậy bộ gọi giữ một
danh sách mô hình: mô hình nào báo 429 (hết hạn mức) hoặc 503 (quá tải) hoặc 404 (không còn dùng được) thì cho nghỉ một thời gian và
gọi ngay mô hình kế tiếp trong cùng yêu cầu. Hết mô hình dùng được thì trả 503 để backend tự gọi lại.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from ..errors import ModelUnavailable, ServiceError
from .client import LlmResult, TokenUsage, _extract_json

log = logging.getLogger("ai.llm")

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Gemini dừng vì lý do an toàn hoặc chính sách: coi như mô hình từ chối nội dung (422, backend không gọi lại).
_REFUSED_FINISH = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "LANGUAGE"}

# Thời gian cho một mô hình nghỉ (giây) khi nhà cung cấp không nói rõ.
REST_RATE_LIMITED = 60.0
REST_OVERLOADED = 30.0
REST_NOT_FOUND = 3600.0
REST_TIMEOUT = 60.0


def _usage_of(body: dict) -> TokenUsage:
    """promptTokenCount gồm cả phần đệm; token ra gồm cả token suy nghĩ (đều được tính như đầu ra)."""
    u = body.get("usageMetadata") or {}
    cached = int(u.get("cachedContentTokenCount") or 0)
    return TokenUsage(
        input_tokens=max(0, int(u.get("promptTokenCount") or 0) - cached),
        output_tokens=int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0),
        cache_read_tokens=cached,
    )


class GeminiLlm:
    # Đổi sang False khi nhà cung cấp từ chối lược đồ (giống bộ gọi Claude).
    structured = True

    def __init__(
        self,
        api_key: str | None,
        model: str,
        *,
        fallback_models: Sequence[str] = (),
        thinking_level: str | None = None,
        http: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._key = api_key
        self.model = model
        self._models = [model, *(m for m in dict.fromkeys(fallback_models) if m and m != model)]
        self._resting: dict[str, float] = {}  # mô hình -> thời điểm (đồng hồ đơn điệu) được dùng lại
        self._clock = clock
        self._thinking_override = thinking_level
        self._thinking = True  # tắt khi mô hình không nhận mức suy nghĩ đã gửi
        self._http = http or httpx.AsyncClient()

    @property
    def models(self) -> list[str]:
        return list(self._models)

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
        if not self._key:
            raise ModelUnavailable(503, "llm_not_configured", "Dịch vụ AI chưa được cấu hình khóa mô hình.")
        started = time.perf_counter()
        queue = self._available()
        if not queue:
            raise ModelUnavailable(503, "llm_rate_limited", "Mọi mô hình Gemini đang hết hạn mức hoặc quá tải; thử lại sau.")
        body: dict | None = None
        last_status = 0
        reconfigured = 0  # số lần đổi cách gửi (bỏ lược đồ, bỏ mức suy nghĩ) cho cùng mô hình
        deadline = time.monotonic() + timeout
        while queue and body is None:
            model = queue[0]
            try:
                response = await self._http.post(
                    f"{BASE_URL}/models/{model}:generateContent",
                    headers={"x-goog-api-key": self._key, "Content-Type": "application/json"},
                    json=self._payload(system, user, schema, effort, max_tokens),
                    timeout=min(timeout, deadline - time.monotonic()),
                )
            except httpx.TimeoutException:
                self._log_failure(api, started, "timeout", model)

                self._resting[model] = self._clock() + REST_TIMEOUT
                queue.pop(0)

                if queue:
                    log.warning(
                        "Model Gemini timeout, chuyển sang model tiếp theo",
                        extra={
                            "api": api,
                            "model": queue[0],
                            "result": "timeout",
                        },
                    )
                    reconfigured = 0
                    continue

                raise ModelUnavailable(
                    504,
                    "llm_timeout",
                    "Tất cả model Gemini đều không phản hồi kịp thời gian chờ.",
                )
            except httpx.TransportError as exc:
                self._log_failure(api, started, "connection", model)
                raise ModelUnavailable(
                    503,
                    "llm_unreachable",
                    "Không kết nối được nhà cung cấp mô hình.",
                ) from exc
            status = last_status = response.status_code
            if status == 200:
                body = response.json()
                break
            detail = _error_message(response)
            if status == 400:
                lowered = detail.lower()
                self._log_failure(api, started, "bad_request", model, detail=detail[:300])
                if reconfigured < 2 and self.structured and any(k in lowered for k in ("schema", "response_json_schema", "responsejsonschema", "response_mime_type")):
                    log.warning("Nhà cung cấp từ chối lược đồ JSON: chuyển sang chế độ JSON thuần trong prompt", extra={"api": api})
                    self.structured = False
                    reconfigured += 1
                    continue
                if reconfigured < 2 and self._thinking and "thinking" in lowered:
                    log.warning("Mô hình không nhận mức suy nghĩ đã gửi: bỏ cấu hình suy nghĩ", extra={"api": api})
                    self._thinking = False
                    reconfigured += 1
                    continue
                if "api key" in lowered or "api_key" in lowered:
                    raise ModelUnavailable(503, "llm_not_ready", "Dịch vụ AI chưa sẵn sàng (khóa hoặc mô hình chưa dùng được).")
                raise ModelUnavailable(502, "llm_bad_request", "Yêu cầu gửi mô hình bị từ chối.")
            self._log_failure(api, started, f"status_{status}", model)
            if status in (401, 403):
                raise ModelUnavailable(503, "llm_not_ready", "Dịch vụ AI chưa sẵn sàng (khóa hoặc mô hình chưa dùng được).")
            if status in (429, 503, 404):
                rest = _retry_delay(response) or {429: REST_RATE_LIMITED, 503: REST_OVERLOADED, 404: REST_NOT_FOUND}[status]
                self._resting[model] = self._clock() + rest
                queue.pop(0)
                if queue:
                    log.warning("Chuyển sang mô hình Gemini kế tiếp", extra={"api": api, "model": queue[0], "result": f"status_{status}"})
                reconfigured = 0
                continue
            raise ModelUnavailable(502, "llm_unavailable", "Nhà cung cấp mô hình đang lỗi hoặc quá tải.")

        if body is None:
            if last_status == 429:
                raise ModelUnavailable(503, "llm_rate_limited", "Mọi mô hình Gemini đang hết hạn mức; thử lại sau.")
            if last_status == 404:
                raise ModelUnavailable(503, "llm_not_ready", "Dịch vụ AI chưa sẵn sàng (khóa hoặc mô hình chưa dùng được).")
            raise ModelUnavailable(503, "llm_unavailable", "Nhà cung cấp mô hình đang lỗi hoặc quá tải.")

        usage = _usage_of(body)
        model = body.get("modelVersion") or model
        block = (body.get("promptFeedback") or {}).get("blockReason")
        candidates = body.get("candidates") or []
        finish = candidates[0].get("finishReason") if candidates else None
        if block or finish in _REFUSED_FINISH:
            log.warning(
                "Mô hình từ chối",
                extra={"api": api, "model": model, "stopReason": block or finish, "inputTokens": usage.total_input, "outputTokens": usage.output_tokens},
            )
            raise ServiceError(422, "model_refused", "Mô hình từ chối xử lý nội dung này.")
        if finish == "MAX_TOKENS":
            return LlmResult(None, usage, model, truncated=True, stop_reason="max_tokens")
        parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought") and isinstance(p.get("text"), str))
        if not text.strip():
            return LlmResult(None, usage, model, parse_error="Mô hình không trả khối chữ nào.", stop_reason=finish)
        try:
            return LlmResult(json.loads(text) if self.structured else _extract_json(text), usage, model, stop_reason=finish)
        except json.JSONDecodeError:
            return LlmResult(None, usage, model, parse_error="Đầu ra không phải JSON hợp lệ.", stop_reason=finish)

    def _available(self) -> list[str]:
        now = self._clock()
        return [m for m in self._models if self._resting.get(m, 0.0) <= now]

    def _payload(self, system: str, user: str, schema: dict, effort: str, max_tokens: int) -> dict[str, Any]:
        config: dict[str, Any] = {"responseMimeType": "application/json", "maxOutputTokens": max_tokens}
        if self.structured:
            config["responseJsonSchema"] = schema
        else:
            system = (
                f"{system}\n\nTrả về DUY NHẤT một đối tượng JSON hợp lệ đúng lược đồ JSON sau, không kèm chữ nào khác, không dùng khối mã:\n"
                f"{json.dumps(schema, ensure_ascii=False, separators=(',', ':'))}"
            )
        if self._thinking:
            config["thinkingConfig"] = {"thinkingLevel": self._thinking_override or effort}
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": config,
        }

    @staticmethod
    def _log_failure(api: str, started: float, result: str, model: str, detail: str | None = None) -> None:
        extra: dict[str, Any] = {"api": api, "model": model, "result": result, "ms": int((time.perf_counter() - started) * 1000)}
        if detail:
            extra["problems"] = detail
        log.warning("Gọi mô hình lỗi", extra=extra)


def _error_body(response: httpx.Response) -> dict:
    try:
        return response.json().get("error") or {}
    except ValueError:
        return {}


def _error_message(response: httpx.Response) -> str:
    return str(_error_body(response).get("message") or "") or response.text[:300]


def _retry_delay(response: httpx.Response) -> float | None:
    """Thời gian chờ Google gợi ý (RetryInfo.retryDelay, vd "31625s"), nếu có."""
    for detail in _error_body(response).get("details") or []:
        delay = detail.get("retryDelay") if isinstance(detail, dict) else None
        match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(delay or ""))
        if match:
            return float(match.group(1))
    return None
