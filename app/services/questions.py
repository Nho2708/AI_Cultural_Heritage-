"""Sinh câu hỏi 8 dạng theo cấp, kiểm từng câu rồi mới trả."""
from __future__ import annotations

from ..config import Settings
from ..errors import InvalidInput
from ..llm.client import Llm
from ..llm.runner import Outcome, run_validated
from ..prompts import questions as prompts
from ..rules import QUESTION_NAMES, question_allowed_at
from ..schemas.common import HeritageInput, Usage
from ..schemas.questions import GeneratedQuestion, QuestionsRequest, QuestionsResponse
from ..text import count_words
from ..validators.questions import parse_items, signature, validate_question

API = "generate-questions"
MIN_TEXT_WORDS = 25
MIN_PASSAGE_WORDS = 40


def feasible_types(req: QuestionsRequest, types: list[str]) -> dict[str, list[int]]:
    """Dạng nào dùng được với di sản nào, theo dữ liệu đang có (đủ chữ, đủ ảnh)."""
    result: dict[str, list[int]] = {}
    for t in types:
        ids: list[int] = []
        for h in req.heritages:
            if _supports(t, h, req.grade_level):
                ids.append(h.heritage_id)
        if ids:
            result[t] = ids
    return result


def _supports(question_type: str, h: HeritageInput, level: int) -> bool:
    text_words = count_words(h.content) + count_words(h.short_description)
    content_words = count_words(h.content)
    images = len({i.url for i in h.images})
    if question_type == "IMAGE_CHOICE":
        return images >= 3
    if question_type == "TRUE_FALSE":
        return text_words >= MIN_TEXT_WORDS and (level != 1 or images >= 1)
    if question_type in ("SOURCE_READING", "FILL_BLANK"):
        return content_words >= MIN_PASSAGE_WORDS
    if question_type == "ORDERING":
        return content_words >= MIN_PASSAGE_WORDS or len(h.timeline) >= 3
    if question_type == "MATCHING":
        return images >= 3 or content_words >= MIN_PASSAGE_WORDS
    return text_words >= MIN_TEXT_WORDS  # SINGLE_CHOICE, MULTI_TRUE_FALSE


async def generate_questions(req: QuestionsRequest, llm: Llm, settings: Settings) -> QuestionsResponse:
    types: list[str] = []
    for t in req.types:
        if t.value not in types:
            types.append(t.value)
    bad = [t for t in types if not question_allowed_at(t, req.grade_level)]
    if bad:
        raise InvalidInput(
            "type_not_allowed_at_level",
            f"Dạng câu không dùng được ở cấp {req.grade_level}: " + ", ".join(QUESTION_NAMES[t] for t in bad) + ".",
            details=[{"field": "types", "message": t} for t in bad],
        )
    feasible = feasible_types(req, types)
    if not feasible:
        raise InvalidInput(
            "insufficient_material",
            "Tư liệu của các di sản chưa đủ (chữ hoặc ảnh) để sinh bất kỳ dạng câu nào được chọn.",
        )
    usable = list(feasible)
    libraries = {h.heritage_id: {i.url for i in h.images} for h in req.heritages}
    if len(libraries) != len(req.heritages):
        raise InvalidInput("duplicate_heritage", "Danh sách di sản có heritageId trùng nhau.")

    accepted: list[GeneratedQuestion] = []
    seen: set[str] = set()

    def need() -> int:
        return max(1, req.count - len(accepted))

    def build_user(problems: list[str]) -> str:
        base = prompts.user_prompt(req, req.heritages, feasible, need(), [q.content or "" for q in accepted])
        if not problems:
            return base
        listed = "\n".join(f"- {p}" for p in problems[:12])
        return f"{base}\n\nLƯU Ý: lần trả lời trước có câu chưa đạt. Hãy sinh {need()} câu mới, sửa đủ các điểm sau:\n{listed}"

    def validate(data: object) -> Outcome:
        items = parse_items(data)
        if items is None:
            return Outcome(problems=["Đầu ra thiếu mảng `questions`."])
        problems: list[str] = []
        for i, raw in enumerate(items):
            if len(accepted) >= req.count:
                break
            question, errors = validate_question(
                raw, i, grade_level=req.grade_level, allowed_types=set(usable), libraries=libraries
            )
            if question is None:
                problems.extend(errors)
                continue
            sig = signature(question)
            if sig in seen:
                problems.append(f"Câu {i + 1}: trùng một câu đã nhận.")
                continue
            seen.add(sig)
            accepted.append(question)
        if len(accepted) >= req.count:
            return Outcome(value=list(accepted[: req.count]), done=True)
        if not problems:
            problems.append(f"Mới có {len(accepted)} câu hợp lệ trên {req.count} câu yêu cầu.")
        return Outcome(problems=problems)

    result = await run_validated(
        llm,
        api=API,
        system=prompts.system_prompt(),
        user=build_user,
        schema=prompts.schema(usable, req.grade_level),
        effort="medium",
        max_tokens=min(16000, 5000 + 700 * req.count),
        llm_timeout=settings.ai_llm_timeout_seconds,
        budget_seconds=settings.ai_budget_seconds,
        validate=validate,
        # Sau khi gọi lại vẫn thiếu câu: trả số câu đã đạt (backend nhận ít câu hơn yêu cầu); không có câu nào thì lỗi.
        finalize=lambda: list(accepted[: req.count]) if accepted else None,
    )
    return QuestionsResponse(
        questions=result.value,
        model=result.model,
        usage=Usage(input_tokens=result.usage.total_input, output_tokens=result.usage.output_tokens),
    )
