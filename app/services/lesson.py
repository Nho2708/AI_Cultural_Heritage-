"""Soạn nội dung bài học theo cấp."""
from __future__ import annotations

from ..config import Settings
from ..llm.client import Llm
from ..llm.runner import Outcome, run_validated
from ..prompts import lesson as prompts
from ..schemas.common import Usage
from ..schemas.lesson import ComposeRequest, ComposeResponse
from ..validators.lesson import validate_compose

API = "compose-lesson"


async def compose_lesson(req: ComposeRequest, llm: Llm, settings: Settings) -> ComposeResponse:
    # Lần đầu kiểm số từ đúng khung của cấp (không dung sai) để bài hơi ngắn hoặc hơi dài được gọi lại kèm góp ý;
    # bản đó vẫn đạt khi có dung sai nên được giữ làm bản dự phòng nếu lần gọi lại hỏng hoặc quá giờ.
    # Lần cuối kiểm có dung sai như trước.
    state: dict = {"attempt": 0, "fallback": None}

    def validate(data: object) -> Outcome:
        state["attempt"] += 1
        if state["attempt"] > 1:
            return validate_compose(data, req)
        strict = validate_compose(data, req, word_tolerance=0.0)
        if not strict.done:
            lenient = validate_compose(data, req)
            if lenient.done:
                state["fallback"] = lenient.value
        return strict

    result = await run_validated(
        llm,
        api=API,
        system=prompts.system_prompt(req.grade_level),
        user=prompts.user_prompt(req),
        schema=prompts.schema(req.grade_level),
        effort="medium",
        max_tokens=10000,
        llm_timeout=settings.ai_llm_timeout_seconds,
        budget_seconds=settings.ai_budget_seconds,
        validate=validate,
        finalize=lambda: state["fallback"],
    )
    response: ComposeResponse = result.value
    return response.model_copy(
        update={"model": result.model, "usage": Usage(input_tokens=result.usage.total_input, output_tokens=result.usage.output_tokens)}
    )
