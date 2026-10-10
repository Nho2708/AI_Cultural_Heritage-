"""Soạn nội dung bài học theo cấp."""
from __future__ import annotations

from ..config import Settings
from ..llm.client import Llm
from ..llm.runner import run_validated
from ..prompts import lesson as prompts
from ..schemas.common import Usage
from ..schemas.lesson import ComposeRequest, ComposeResponse
from ..validators.lesson import validate_compose

API = "compose-lesson"


async def compose_lesson(req: ComposeRequest, llm: Llm, settings: Settings) -> ComposeResponse:
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
        validate=lambda data: validate_compose(data, req),
    )
    response: ComposeResponse = result.value
    return response.model_copy(
        update={"model": result.model, "usage": Usage(input_tokens=result.usage.total_input, output_tokens=result.usage.output_tokens)}
    )
