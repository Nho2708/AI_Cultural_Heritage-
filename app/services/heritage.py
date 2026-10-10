"""Tóm tắt tiếng Việt và dịch di sản sang en, ko, zh-Hans, ja."""
from __future__ import annotations

from ..config import Settings
from ..errors import InvalidInput
from ..llm.client import Llm
from ..llm.runner import run_validated
from ..prompts import heritage as prompts
from ..schemas.common import Usage
from ..schemas.heritage import SummarizeRequest, SummarizeResponse, TranslateRequest, TranslateResponse
from ..validators.heritage import validate_summary, validate_translation

API_SUMMARIZE = "summarize-heritage"
API_TRANSLATE = "translate-heritage"


async def summarize_heritage(req: SummarizeRequest, llm: Llm, settings: Settings) -> SummarizeResponse:
    src = req.source
    if not src.name.strip() or not ((src.short_description or "").strip() or (src.content or "").strip()):
        raise InvalidInput("missing_source", "Di sản chưa có tên hoặc nội dung tiếng Việt để tóm tắt.")
    result = await run_validated(
        llm,
        api=API_SUMMARIZE,
        system=prompts.SUMMARIZE_SYSTEM,
        user=prompts.summarize_user(req),
        schema=prompts.summarize_schema(),
        effort="low",
        max_tokens=6000,
        llm_timeout=settings.ai_heritage_llm_timeout_seconds,
        budget_seconds=settings.ai_heritage_budget_seconds,
        validate=lambda data: validate_summary(data, req),
    )
    response: SummarizeResponse = result.value
    return response.model_copy(
        update={"model": result.model, "usage": Usage(input_tokens=result.usage.total_input, output_tokens=result.usage.output_tokens)}
    )


def _estimate_output_tokens(req: TranslateRequest) -> int:
    c = req.content
    chars = len(c.name) + len(c.short_description or "") + len(c.content or "")
    chars += sum(len(t.name) + len(t.description or "") for t in c.timelines)
    chars += sum(len(e.name) + len(e.description or "") for e in c.events)
    chars += sum(len(m.caption) for m in c.media)
    if req.summary:
        chars += len(req.summary.short_text) + len(req.summary.detailed_text)
    # Tiếng Việt khoảng 2 ký tự mỗi token; chữ Hàn, Trung, Nhật tốn token hơn; chừa chỗ cho suy nghĩ và khung JSON.
    return max(6000, min(20000, int(chars / 1.6) + 3000))


async def translate_heritage(req: TranslateRequest, llm: Llm, settings: Settings) -> TranslateResponse:
    if req.target_language.value == req.content_language.value:
        raise InvalidInput("same_language", "Ngôn ngữ đích trùng ngôn ngữ của nội dung nguồn.")
    if req.summary_language is not None and req.summary_language.value == req.target_language.value:
        raise InvalidInput("same_language", "Ngôn ngữ đích trùng ngôn ngữ của bản tóm tắt nguồn.")
    if not req.content.name.strip():
        raise InvalidInput("missing_source", "Di sản chưa có tên để dịch.")
    result = await run_validated(
        llm,
        api=API_TRANSLATE,
        system=prompts.TRANSLATE_SYSTEM,
        user=prompts.translate_user(req),
        schema=prompts.translate_schema(req.summary is not None),
        effort="low",
        max_tokens=_estimate_output_tokens(req),
        llm_timeout=settings.ai_heritage_llm_timeout_seconds,
        budget_seconds=settings.ai_heritage_budget_seconds,
        validate=lambda data: validate_translation(data, req),
    )
    response: TranslateResponse = result.value
    return response.model_copy(
        update={"model": result.model, "usage": Usage(input_tokens=result.usage.total_input, output_tokens=result.usage.output_tokens)}
    )
