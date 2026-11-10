"""Kiểm đầu ra viết lại một phần: giới hạn theo loại phần, tiếng Việt có dấu, văn bản thuần, không thêm số (năm) lạ."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from .. import rules
from ..llm.runner import Outcome
from ..schemas.common import Usage
from ..schemas.lesson import RewriteSectionRequest, RewriteSectionResponse
from ..text import count_words, has_markdown, looks_vietnamese, split_sentences, strip_markdown

# Số có 3 đến 4 chữ số (năm, thế kỷ ghi số...). Dấu phân cách hàng nghìn bị bỏ trước khi tìm để "1.500" và "1500" là một.
_THOUSANDS = re.compile(r"(?<=\d)[.,](?=\d{3}(?!\d))")
_YEAR_LIKE = re.compile(r"(?<!\d)\d{3,4}(?!\d)")
# Lần kiểm đầu không dung sai; lần cuối (và bản dự phòng) nới độ dài câu trung bình của bước câu chuyện như bộ kiểm soạn bài.
_LENIENT_AVG_WORDS = rules.LEVEL1_MAX_AVG_SENTENCE_WORDS


class _RawRewrite(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    title: str | None = None


def year_like_numbers(text: str | None) -> set[str]:
    """Các số 3 đến 4 chữ số trong chữ (đã bỏ dấu phân cách hàng nghìn)."""
    if not text:
        return set()
    return set(_YEAR_LIKE.findall(_THOUSANDS.sub("", text)))


def known_numbers(req: RewriteSectionRequest) -> set[str]:
    """Mọi số 3 đến 4 chữ số được phép xuất hiện: có trong chữ cũ, tiêu đề cũ, nội dung bài hoặc tư liệu di sản."""
    known: set[str] = set()
    known |= year_like_numbers(req.current_text) | year_like_numbers(req.title) | year_like_numbers(req.lesson_content)
    if req.year is not None:
        known |= year_like_numbers(str(abs(req.year)))
    for h in req.heritages:
        for chunk in (h.name, h.short_description, h.content):
            known |= year_like_numbers(chunk)
        for t in h.timeline:
            known |= year_like_numbers(t.name) | year_like_numbers(t.description) | year_like_numbers(t.date_label)
            known |= year_like_numbers(str(abs(t.start_year)))
        for i in h.images:
            known |= year_like_numbers(i.caption)
        for s in h.sources:
            known |= year_like_numbers(s.title)
    return known


def _tidy(text: str, keep_paragraphs: bool) -> str:
    text = strip_markdown(text)
    if keep_paragraphs:
        lines = [" ".join(line.split()) for line in text.splitlines()]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return " ".join(text.split())


def validate_rewrite(data: Any, req: RewriteSectionRequest, *, lenient: bool = False) -> Outcome:
    """lenient=False: giới hạn đúng bảng, Markdown là lỗi. lenient=True: dung sai số từ, Markdown được bỏ lặng lẽ."""
    try:
        raw = _RawRewrite.model_validate(data)
    except ValidationError:
        return Outcome(problems=["Đầu ra sai lược đồ JSON (cần `text` và `title`)."])

    kind = req.kind.value
    limit = rules.section_limit(kind, req.grade_level)
    problems: list[str] = []

    # ---- Chữ mới ----
    if not lenient and (has_markdown(raw.text) or has_markdown(raw.title)):
        problems.append("Chỉ viết văn bản thuần: không dùng ký hiệu Markdown (#, **, gạch đầu dòng, liên kết, dấu huyền).")
    text = _tidy(raw.text, keep_paragraphs=kind == "READING")
    n = count_words(text)
    if n == 0:
        problems.append("`text` rỗng.")
    else:
        tol = rules.WORD_TOLERANCE if lenient else 0.0
        low = int(limit.min_words * (1 - tol))
        high = int(limit.max_words * (1 + tol)) + (1 if tol else 0)
        if n > high:
            problems.append(f"`text` có {n} từ, tối đa {limit.max_words} từ cho {limit.name}: rút bớt khoảng {n - limit.max_words} từ.")
        elif n < low:
            problems.append(f"`text` có {n} từ, tối thiểu {limit.min_words} từ cho {limit.name}: viết thêm ý có trong tư liệu.")
        if not looks_vietnamese(text, min_words=5):
            problems.append("`text` phải viết bằng tiếng Việt có dấu, không lẫn ngôn ngữ khác.")
        sentences = split_sentences(text)
        count = len(sentences)
        if count < limit.min_sentences or (limit.max_sentences is not None and count > limit.max_sentences):
            if limit.max_sentences is None:
                wanted = f"ít nhất {limit.min_sentences}"
            elif limit.min_sentences == limit.max_sentences:
                wanted = f"đúng {limit.max_sentences}"
            else:
                wanted = f"{limit.min_sentences} đến {limit.max_sentences}"
            problems.append(f"`text` có {count} câu, {limit.name} cần {wanted} câu.")
        if limit.avg_sentence_words is not None and count:
            cap = _LENIENT_AVG_WORDS if lenient else limit.avg_sentence_words
            avg = n / count
            if avg > cap:
                problems.append(f"Câu quá dài cho cấp 1: trung bình {avg:.0f} từ mỗi câu, cần không quá {limit.avg_sentence_words} từ.")
        if limit.is_question and not text.rstrip().endswith("?"):
            problems.append("`text` phải là một câu hỏi kết thúc bằng dấu hỏi (?).")

    # ---- Tiêu đề (chỉ khi bản cũ có tiêu đề) ----
    old_title = (req.title or "").strip()
    title: str | None = None
    if old_title:
        new_title = _tidy(raw.title or "", keep_paragraphs=False)
        title = new_title or old_title
        if len(title) > rules.REWRITE_TITLE_MAX:
            problems.append(f"`title` dài {len(title)} ký tự, tối đa {rules.REWRITE_TITLE_MAX}.")

    # ---- Số (năm) lạ ----
    new_numbers = year_like_numbers(text) | year_like_numbers(title)
    strange = sorted(new_numbers - known_numbers(req))
    if strange:
        problems.append(
            f"Có số không có trong bản cũ, nội dung bài hoặc tư liệu di sản: {', '.join(strange)}. "
            "Không thêm năm hay số liệu mới; chỉ dùng số đã có trong tư liệu."
        )
    if kind == "MILESTONE" and req.year is not None:
        # Mốc không đổi năm: chữ mới chỉ được nhắc năm của chính mốc (hoặc số đã nằm sẵn trong chữ cũ).
        allowed = year_like_numbers(str(abs(req.year))) | year_like_numbers(req.current_text) | year_like_numbers(req.title)
        other = sorted(new_numbers - allowed - set(strange))
        if other:
            problems.append(
                f"Mốc thời gian này ở năm {abs(req.year)}{' TCN' if req.year < 0 else ''}: không đổi năm, "
                f"không nêu năm khác ({', '.join(other)})."
            )

    if problems:
        return Outcome(problems=problems)
    response = RewriteSectionResponse(text=text, title=title, model="", usage=Usage())
    return Outcome(value=response, done=True)

