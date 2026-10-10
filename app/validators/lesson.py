"""Kiểm đầu ra soạn bài học theo khung nội dung của từng cấp (sao quy tắc của backend để backend không phải bỏ phần nào)."""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from .. import rules
from ..llm.runner import Outcome
from ..schemas.common import SectionKind, Usage
from ..schemas.lesson import ComposedStep, ComposeRequest, ComposeResponse, SourceQuote
from ..text import count_words, find_verbatim, looks_vietnamese, split_sentences, strip_markdown


class _RawStep(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: str
    title: str | None = None
    text: str | None = None
    mediaId: int | None = None
    year: int | None = None
    eventId: int | None = None


class _RawQuote(BaseModel):
    model_config = ConfigDict(extra="ignore")
    heritageId: int
    quote: str
    source: str


class _RawLesson(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str
    keyPoints: list[str]
    steps: list[_RawStep] = []
    sourceQuotes: list[_RawQuote] = []


def word_window(frame: rules.LevelFrame) -> tuple[int, int]:
    return int(frame.min_words * (1 - rules.WORD_TOLERANCE)), int(frame.max_words * (1 + rules.WORD_TOLERANCE)) + 1


def validate_compose(data: Any, req: ComposeRequest) -> Outcome:
    try:
        raw = _RawLesson.model_validate(data)
    except ValidationError:
        return Outcome(problems=["Đầu ra sai lược đồ JSON (thiếu hoặc sai kiểu trường)."])

    level = req.grade_level
    frame = rules.LEVEL_FRAMES[level]
    problems: list[str] = []

    # ---- Nội dung chính ----
    content = strip_markdown(raw.content)
    n = count_words(content)
    low, high = word_window(frame)
    if n == 0:
        problems.append("`content` rỗng.")
    elif not low <= n <= high:
        problems.append(
            f"`content` hiện có {n} từ, phải nằm trong {frame.min_words} đến {frame.max_words} từ "
            f"(mục tiêu {frame.targets[req.length.value]} từ)."
        )
    if n and not looks_vietnamese(content):
        problems.append("`content` phải viết bằng tiếng Việt có dấu, không lẫn ngôn ngữ khác.")
    if level == 1 and n:
        sentences = split_sentences(content)
        avg = n / max(1, len(sentences))
        if avg > rules.LEVEL1_MAX_AVG_SENTENCE_WORDS:
            problems.append(f"Câu quá dài cho cấp 1: trung bình {avg:.0f} từ mỗi câu, cần khoảng 15 từ trở xuống.")

    # ---- Ý chính ----
    key_points: list[str] = []
    seen: set[str] = set()
    for k in raw.keyPoints:
        k = strip_markdown(k).strip()
        if not k or k.lower() in seen:
            continue
        seen.add(k.lower())
        key_points.append(k)
    if len(key_points) > rules.MAX_KEY_POINTS:
        key_points = key_points[: rules.MAX_KEY_POINTS]
    if len(key_points) < rules.MIN_KEY_POINTS:
        problems.append(f"`keyPoints` cần {rules.MIN_KEY_POINTS} đến {rules.MAX_KEY_POINTS} ý khác nhau, hiện có {len(key_points)}.")
    for i, k in enumerate(key_points):
        if len(k) > rules.KEY_POINT_MAX_CHARS:
            problems.append(f"Ý chính thứ {i + 1} dài {len(k)} ký tự, tối đa {rules.KEY_POINT_MAX_CHARS}.")

    # ---- Các phần có cấu trúc ----
    offered_media = {i.media_id for h in req.heritages for i in h.images}
    events = {t.event_id: t.start_year for h in req.heritages for t in h.timeline}
    steps: list[ComposedStep] = []
    max_year = date.today().year
    kind_counts: dict[str, int] = {}
    for idx, s in enumerate(raw.steps):
        if s.kind not in frame.kinds:
            problems.append(f"Phần thứ {idx + 1} có kind={s.kind} không thuộc khung của {frame.name}; chỉ dùng {', '.join(frame.kinds)}.")
            continue
        kind_counts[s.kind] = kind_counts.get(s.kind, 0) + 1
        text = strip_markdown(s.text).strip() if s.text else None
        title = strip_markdown(s.title).strip() if s.title else None
        label = f"Phần {s.kind} thứ {kind_counts[s.kind]}"
        if s.kind == "STORY":
            if not text:
                problems.append(f"{label} thiếu `text`.")
            elif count_words(text) > int(rules.LEVEL1_STEP_MAX_WORDS * (1 + rules.WORD_TOLERANCE)):
                problems.append(f"{label} dài {count_words(text)} từ, tối đa {rules.LEVEL1_STEP_MAX_WORDS} từ.")
            media = s.mediaId
            if offered_media and media not in offered_media:
                problems.append(f"{label} phải có `mediaId` lấy từ danh sách ảnh của di sản.")
            if not offered_media:
                media = None
            steps.append(ComposedStep(kind=SectionKind.STORY, text=text, media_id=media, title=title or None))
        elif s.kind == "IMAGE":
            if s.mediaId not in offered_media:
                problems.append(f"{label} phải có `mediaId` lấy từ danh sách ảnh của di sản.")
            if not text:
                problems.append(f"{label} thiếu chú thích `text`.")
            steps.append(ComposedStep(kind=SectionKind.IMAGE, text=text, media_id=s.mediaId, title=title or None))
        elif s.kind == "MILESTONE":
            if s.year is None or not rules.MIN_YEAR <= s.year <= max_year:
                problems.append(f"{label} cần `year` là số nguyên hợp lệ (năm TCN là số âm).")
            if not text:
                problems.append(f"{label} thiếu `text`.")
            event_id = s.eventId if s.eventId in events else None
            if event_id is not None and s.year is not None and events[event_id] != s.year:
                event_id = None
            steps.append(
                ComposedStep(kind=SectionKind.MILESTONE, text=text, year=s.year, event_id=event_id, title=title or None)
            )
        else:  # REFLECTION
            if not text or count_words(text) < 5:
                problems.append(f"{label} cần một câu hỏi đầy đủ trong `text`.")
            steps.append(ComposedStep(kind=SectionKind.REFLECTION, text=text, title=title or None))

    rank = {SectionKind.STORY: 0, SectionKind.IMAGE: 1, SectionKind.MILESTONE: 2, SectionKind.REFLECTION: 3}
    steps.sort(key=lambda st: (rank[st.kind], st.year if st.kind == SectionKind.MILESTONE and st.year is not None else 0))
    _check_counts(level, kind_counts, bool(offered_media), problems)

    if level == 1 and kind_counts.get("STORY") and n:
        story_words = sum(count_words(s.text) for s in steps if s.kind == SectionKind.STORY)
        if not 0.6 <= story_words / n <= 1.4:
            problems.append(
                f"Các bước câu chuyện gộp lại có {story_words} từ nhưng `content` có {n} từ; các bước phải là chính câu chuyện trong `content` chia nhỏ."
            )

    quotes = _check_quotes(level, raw.sourceQuotes, req, problems)

    if problems:
        return Outcome(problems=problems)
    response = ComposeResponse(
        content=content,
        steps=steps,
        source_quotes=quotes,
        key_points=key_points,
        grade_level=level,
        length=req.length,
        model="",  # dịch vụ điền sau
        usage=Usage(),
    )
    return Outcome(value=response, done=True)


def _check_counts(level: int, counts: dict[str, int], has_images: bool, problems: list[str]) -> None:
    if level == 1:
        stories = counts.get("STORY", 0)
        if not rules.LEVEL1_MIN_STEPS <= stories <= rules.LEVEL1_MAX_STEPS:
            problems.append(f"Cần {rules.LEVEL1_MIN_STEPS} đến {rules.LEVEL1_MAX_STEPS} bước kind=STORY, hiện có {stories}.")
        if counts.get("IMAGE", 0) > rules.LEVEL1_MAX_IMAGES:
            problems.append(f"Tối đa {rules.LEVEL1_MAX_IMAGES} phần kind=IMAGE.")
    elif level == 2:
        m = counts.get("MILESTONE", 0)
        if not rules.LEVEL2_MIN_MILESTONES <= m <= rules.LEVEL2_MAX_MILESTONES:
            problems.append(f"Cần {rules.LEVEL2_MIN_MILESTONES} đến {rules.LEVEL2_MAX_MILESTONES} mốc kind=MILESTONE, hiện có {m}.")
        images = counts.get("IMAGE", 0)
        if images > rules.LEVEL2_MAX_IMAGES:
            problems.append(f"Tối đa {rules.LEVEL2_MAX_IMAGES} phần kind=IMAGE.")
        if has_images and images == 0:
            problems.append("Di sản có ảnh nên cần ít nhất một phần kind=IMAGE kèm chú thích.")
    else:
        r = counts.get("REFLECTION", 0)
        if not rules.LEVEL3_MIN_REFLECTIONS <= r <= rules.LEVEL3_MAX_REFLECTIONS:
            problems.append(f"Cần {rules.LEVEL3_MIN_REFLECTIONS} đến {rules.LEVEL3_MAX_REFLECTIONS} câu hỏi kind=REFLECTION, hiện có {r}.")
        if counts.get("MILESTONE", 0) > rules.LEVEL3_MAX_MILESTONES:
            problems.append(f"Tối đa {rules.LEVEL3_MAX_MILESTONES} mốc kind=MILESTONE.")


def _check_quotes(level: int, raw_quotes: list[_RawQuote], req: ComposeRequest, problems: list[str]) -> list[SourceQuote]:
    if level != 3:
        return []
    contents = {h.heritage_id: (h.content or "") for h in req.heritages}
    quotable = any(count_words(c) >= rules.LEVEL3_QUOTE_MIN_WORDS for c in contents.values())
    quotes: list[SourceQuote] = []
    for i, q in enumerate(raw_quotes, start=1):
        source_text = contents.get(q.heritageId)
        if source_text is None:
            problems.append(f"Đoạn trích {i} có `heritageId` không có trong danh sách di sản.")
            continue
        verbatim = find_verbatim(q.quote, source_text)
        if verbatim is None:
            problems.append(f"Đoạn trích {i} không phải chuỗi con nguyên văn của nội dung di sản {q.heritageId}; hãy sao chép từng chữ.")
            continue
        n = count_words(verbatim)
        if not rules.LEVEL3_QUOTE_MIN_WORDS <= n <= rules.LEVEL3_QUOTE_MAX_WORDS:
            problems.append(f"Đoạn trích {i} dài {n} từ, cần {rules.LEVEL3_QUOTE_MIN_WORDS} đến {rules.LEVEL3_QUOTE_MAX_WORDS} từ.")
            continue
        source = q.source.strip()
        if not source or len(source) > rules.SOURCE_MAX_CHARS:
            problems.append(f"Đoạn trích {i} thiếu nguồn hoặc nguồn quá {rules.SOURCE_MAX_CHARS} ký tự.")
            continue
        quotes.append(SourceQuote(heritage_id=q.heritageId, quote=verbatim, source=source))
    if len(quotes) > rules.LEVEL3_MAX_QUOTES:
        quotes = quotes[: rules.LEVEL3_MAX_QUOTES]
    if quotable and not quotes:
        problems.append("Cấp 3 cần ít nhất một đoạn trích tư liệu gốc nguyên văn kèm nguồn trong `sourceQuotes`.")
    return quotes
