"""Vòng gọi mô hình có kiểm đầu ra: gọi, kiểm theo lược đồ riêng, sai thì gọi lại đúng một lần kèm danh sách lỗi."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..errors import ModelUnavailable
from .client import Llm, TokenUsage

log = logging.getLogger("ai.runner")

MAX_ATTEMPTS = 2
MIN_RETRY_SECONDS = 6.0
MAX_TOKENS_CEILING = 20000


@dataclass
class Outcome:
    """Kết quả kiểm một lần trả lời của mô hình. done=True: dùng value, không gọi lại."""

    value: Any = None
    problems: list[str] = field(default_factory=list)
    done: bool = False


@dataclass
class RunResult:
    value: Any
    usage: TokenUsage
    model: str


def with_feedback(base_user: str, problems: list[str]) -> str:
    if not problems:
        return base_user
    listed = "\n".join(f"- {p}" for p in problems[:12])
    return (
        f"{base_user}\n\n"
        "LƯU Ý: lần trả lời trước chưa đạt các điểm sau. Hãy viết lại TOÀN BỘ kết quả và sửa đủ từng điểm:\n"
        f"{listed}"
    )


async def run_validated(
    llm: Llm,
    *,
    api: str,
    system: str,
    user: str | Callable[[list[str]], str],
    schema: dict,
    effort: str,
    max_tokens: int,
    llm_timeout: float,
    budget_seconds: float,
    validate: Callable[[Any], Outcome],
    finalize: Callable[[], Any | None] | None = None,
) -> RunResult:
    deadline = time.monotonic() + budget_seconds
    usage = TokenUsage()
    problems: list[str] = []
    model = llm.model
    tokens = max_tokens
    for attempt in range(1, MAX_ATTEMPTS + 1):
        remaining = deadline - time.monotonic()
        if attempt > 1 and remaining < MIN_RETRY_SECONDS:
            log.warning("Hết ngân sách thời gian, không gọi lại", extra={"api": api, "attempt": attempt})
            break
        timeout = max(1.0, min(llm_timeout, remaining))
        started = time.perf_counter()
        try:
            result = await llm.complete_json(
                api=api,
                system=system,
                user=user(problems) if callable(user) else with_feedback(user, problems),
                schema=schema,
                effort=effort,
                max_tokens=tokens,
                timeout=timeout,
            )
        except ModelUnavailable:
            # Lần gọi lại hỏng (quá giờ, quá tải) mà lần trước đã có phần dùng được thì trả phần đó thay vì báo lỗi.
            fallback = finalize() if attempt > 1 and finalize is not None else None
            if fallback is None:
                raise
            log.warning("Lần gọi lại hỏng, dùng kết quả của lần trước", extra={"api": api, "attempt": attempt})
            return RunResult(fallback, usage, model)
        usage.add(result.usage)
        model = result.model or model
        if result.truncated:
            problems = ["Đầu ra bị cắt vì hết giới hạn token; hãy viết gọn hơn nhưng vẫn đủ các phần bắt buộc."]
            tokens = min(int(tokens * 1.5), MAX_TOKENS_CEILING)
            label = "truncated"
        elif result.parse_error:
            problems = [result.parse_error]
            label = "unparsable"
        else:
            outcome = validate(result.data)
            if outcome.done:
                _log(api, attempt, model, result.usage, started, "ok")
                return RunResult(outcome.value, usage, model)
            problems = outcome.problems or ["Đầu ra không đạt kiểm tra."]
            label = "invalid"
        _log(api, attempt, model, result.usage, started, label, problems)

    if finalize is not None:
        value = finalize()
        if value is not None:
            return RunResult(value, usage, model)
    raise ModelUnavailable(
        502,
        "invalid_model_output",
        "Mô hình trả kết quả không đạt kiểm tra sau khi gọi lại một lần.",
        details=[{"problem": p} for p in problems[:8]],
    )


def _log(api: str, attempt: int, model: str, usage: TokenUsage, started: float, result: str, problems: list[str] | None = None) -> None:
    extra: dict[str, Any] = {
        "api": api,
        "attempt": attempt,
        "model": model,
        "result": result,
        "inputTokens": usage.total_input,
        "outputTokens": usage.output_tokens,
        "cacheReadTokens": usage.cache_read_tokens,
        "cacheWriteTokens": usage.cache_write_tokens,
        "ms": int((time.perf_counter() - started) * 1000),
    }
    if problems:
        extra["problems"] = problems[:8]
    log.info("Gọi mô hình", extra=extra)
