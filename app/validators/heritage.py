"""Kiểm đầu ra tóm tắt và dịch di sản: độ dài, chữ viết theo ngôn ngữ đích, đủ mã phần con, thuật ngữ tên riêng."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from .. import rules
from ..llm.runner import Outcome
from ..prompts.glossary import missing_terms
from ..prompts.heritage import glossary_terms
from ..schemas.common import Usage
from ..schemas.heritage import (
    EventText,
    HeritageText,
    MediaText,
    SummarizeRequest,
    SummarizeResponse,
    SummaryText,
    TimelineText,
    TranslateRequest,
    TranslateResponse,
)
from ..text import accented_ratio, count_words, looks_vietnamese, script_profile, strip_markdown

# Chữ Hán phồn thể thường gặp, không dùng trong tiếng Trung giản thể.
_TRADITIONAL = set("國學與後為傳說這個們來時會點無開長東車門問間見認話語讀還進過達連選順領風飛馬魚鳥麼體興歷區變實對將從條樣師員畫書義亞據導愛慶產單廣歲歸營張戰輝總邊輪興")


def _single_paragraph(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ---------------- Tóm tắt ----------------

class _RawSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shortText: str
    detailedText: str


def validate_summary(data: Any, req: SummarizeRequest) -> Outcome:
    try:
        raw = _RawSummary.model_validate(data)
    except ValidationError:
        return Outcome(problems=["Đầu ra sai lược đồ JSON."])
    short = _single_paragraph(strip_markdown(raw.shortText))
    detailed = strip_markdown(raw.detailedText)
    detailed = re.sub(r"[ \t]+\n", "\n", detailed)
    src = req.source
    source_words = count_words(" ".join([src.name, src.short_description or "", src.content or ""]))
    problems: list[str] = []

    tol = rules.SUMMARY_TOLERANCE
    n_short = count_words(short)
    low_short = max(15, min(int(rules.SHORT_SUMMARY_MIN * (1 - tol)), int(source_words * 0.5)))
    high_short = int(rules.SHORT_SUMMARY_MAX * (1 + tol)) + 1
    if not low_short <= n_short <= high_short:
        problems.append(f"`shortText` có {n_short} từ, cần khoảng {rules.SHORT_SUMMARY_MIN} đến {rules.SHORT_SUMMARY_MAX} từ.")
    n_det = count_words(detailed)
    low_det = max(40, min(int(rules.DETAILED_SUMMARY_MIN * (1 - tol)), int(source_words * 0.7)))
    high_det = int(rules.DETAILED_SUMMARY_MAX * (1 + tol)) + 1
    if not low_det <= n_det <= high_det:
        problems.append(f"`detailedText` có {n_det} từ, cần khoảng {rules.DETAILED_SUMMARY_MIN} đến {rules.DETAILED_SUMMARY_MAX} từ.")
    if short and not looks_vietnamese(short):
        problems.append("`shortText` phải viết bằng tiếng Việt có dấu.")
    if detailed and not looks_vietnamese(detailed):
        problems.append("`detailedText` phải viết bằng tiếng Việt có dấu.")
    if len(short) > rules.SUMMARY_SHORT_MAX_CHARS:
        problems.append(f"`shortText` dài {len(short)} ký tự, tối đa {rules.SUMMARY_SHORT_MAX_CHARS}.")
    if problems:
        return Outcome(problems=problems)
    return Outcome(
        value=SummarizeResponse(short_text=short, detailed_text=detailed, model="", usage=Usage()),
        done=True,
    )


# ---------------- Dịch ----------------

class _RawTimeline(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    name: str = ""
    description: str | None = None


class _RawEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    timelineId: int | None = None
    name: str = ""
    description: str | None = None


class _RawMedia(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    caption: str = ""


class _RawText(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = ""
    shortDescription: str | None = None
    content: str | None = None
    timelines: list[_RawTimeline] = []
    events: list[_RawEvent] = []
    media: list[_RawMedia] = []


class _RawTranslation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: _RawText
    summary: _RawSummary | None = None


def check_script(text: str, target: str, *, where: str) -> str | None:
    """Kiểm một đoạn chữ có đúng chữ viết của ngôn ngữ đích không. Trả mô tả lỗi hoặc None."""
    p = script_profile(text)
    letters = p["letters"]
    if letters < 3:
        return None
    long = letters >= 40
    if target == "ko":
        if p["hangul"] < (0.4 if long else 0.3):
            return f"{where} phải viết bằng tiếng Hàn (chữ Hangul)."
    elif target == "zh-Hans":
        if p["han"] < 0.5 or p["hangul"] + p["kana"] > 0.02:
            return f"{where} phải viết bằng tiếng Trung giản thể (chữ Hán), không lẫn tiếng Hàn hay tiếng Nhật."
        if sum(1 for c in text if c in _TRADITIONAL) / max(1.0, letters) > 0.01:
            return f"{where} dùng chữ Hán phồn thể; phải dùng chữ giản thể."
    elif target == "ja":
        if p["kana"] + p["han"] < 0.6 or p["hangul"] > 0.02:
            return f"{where} phải viết bằng tiếng Nhật."
        if long and p["kana"] < 0.1:
            return f"{where} có vẻ không phải tiếng Nhật (thiếu chữ kana)."
    else:  # en
        if p["latin"] < 0.9:
            return f"{where} phải viết bằng tiếng Anh."
        if count_words(text) >= 8 and accented_ratio(text) > 0.25:
            return f"{where} còn nhiều chữ tiếng Việt chưa dịch; phải dịch sang tiếng Anh."
    return None


def _need_text(src: str | None, out: str | None) -> bool:
    """Nguồn có chữ mà bản dịch trống."""
    return bool(src and src.strip()) and not (out and out.strip())


def _fit_ratio(src: str, out: str) -> bool:
    if len(src) < 200:
        return True
    ratio = len(out) / len(src)
    return 0.12 <= ratio <= 4.0


def validate_translation(data: Any, req: TranslateRequest) -> Outcome:
    try:
        raw = _RawTranslation.model_validate(data)
    except ValidationError:
        return Outcome(problems=["Đầu ra sai lược đồ JSON."])
    target = req.target_language.value
    src = req.content
    problems: list[str] = []
    out = raw.content

    def clean(text: str | None) -> str | None:
        return text.strip() if text and text.strip() else None

    name = clean(out.name)
    if not name:
        problems.append("Thiếu tên di sản đã dịch (`content.name`).")
    elif len(name) > rules.NAME_MAX:
        problems.append(f"Tên di sản đã dịch dài {len(name)} ký tự, tối đa {rules.NAME_MAX}.")
    elif (m := check_script(name, target, where="`name`")):
        problems.append(m)

    short_description = clean(out.shortDescription)
    if clean(src.short_description):
        if not short_description:
            problems.append("Thiếu `shortDescription` đã dịch.")
        else:
            if len(short_description) > rules.SHORT_DESCRIPTION_MAX:
                problems.append(f"`shortDescription` đã dịch dài {len(short_description)} ký tự, tối đa {rules.SHORT_DESCRIPTION_MAX}.")
            if (m := check_script(short_description, target, where="`shortDescription`")):
                problems.append(m)
    else:
        short_description = None

    content = out.content.strip() if out.content and out.content.strip() else None
    if clean(src.content):
        if not content:
            problems.append("Thiếu `content` đã dịch.")
        else:
            if not _fit_ratio(src.content or "", content):
                problems.append("`content` đã dịch có độ dài lệch quá nhiều so với bản gốc (thiếu hoặc thừa phần).")
            heads_src = len(re.findall(r"^\s{0,3}#{1,6}\s", src.content or "", re.MULTILINE))
            heads_out = len(re.findall(r"^\s{0,3}#{1,6}\s", content, re.MULTILINE))
            if heads_src != heads_out:
                problems.append(f"`content` gốc có {heads_src} tiêu đề Markdown, bản dịch có {heads_out}; phải giữ nguyên cấu trúc.")
            if (m := check_script(content, target, where="`content`")):
                problems.append(m)
    else:
        content = None

    # ---- Phần con: giữ đủ mã ----
    src_timelines = {t.id: t for t in src.timelines}
    out_timelines = {t.id: t for t in out.timelines}
    if set(out_timelines) != set(src_timelines):
        problems.append(f"`timelines` phải có đúng các id {sorted(src_timelines)} (nhận {sorted(out_timelines)}).")
    src_events = {e.id: e for e in src.events}
    out_events = {e.id: e for e in out.events}
    if set(out_events) != set(src_events):
        problems.append(f"`events` phải có đúng các id {sorted(src_events)} (nhận {sorted(out_events)}).")
    src_media = {m.id: m for m in src.media}
    out_media = {m.id: m for m in out.media}
    if set(out_media) != set(src_media):
        problems.append(f"`media` phải có đúng các id {sorted(src_media)} (nhận {sorted(out_media)}).")

    timelines: list[TimelineText] = []
    for t in src.timelines:
        o = out_timelines.get(t.id)
        if o is None:
            continue
        n, d = clean(o.name), clean(o.description)
        if not n:
            problems.append(f"Giai đoạn {t.id} thiếu tên đã dịch.")
        elif (m := check_script(n, target, where=f"Tên giai đoạn {t.id}")):
            problems.append(m)
        if _need_text(t.description, d):
            problems.append(f"Giai đoạn {t.id} thiếu mô tả đã dịch.")
        elif d and (m := check_script(d, target, where=f"Mô tả giai đoạn {t.id}")):
            problems.append(m)
        timelines.append(TimelineText(id=t.id, name=(n or "")[: rules.NAME_MAX], description=d if clean(t.description) else None))
    events: list[EventText] = []
    for e in src.events:
        o = out_events.get(e.id)
        if o is None:
            continue
        n, d = clean(o.name), clean(o.description)
        if not n:
            problems.append(f"Sự kiện {e.id} thiếu tên đã dịch.")
        elif (m := check_script(n, target, where=f"Tên sự kiện {e.id}")):
            problems.append(m)
        if _need_text(e.description, d):
            problems.append(f"Sự kiện {e.id} thiếu mô tả đã dịch.")
        elif d and (m := check_script(d, target, where=f"Mô tả sự kiện {e.id}")):
            problems.append(m)
        events.append(EventText(id=e.id, timeline_id=e.timeline_id, name=(n or "")[: rules.NAME_MAX], description=d if clean(e.description) else None))
    media: list[MediaText] = []
    for md in src.media:
        o = out_media.get(md.id)
        if o is None:
            continue
        c = clean(o.caption)
        if not c and clean(md.caption):
            problems.append(f"Ảnh {md.id} thiếu chú thích đã dịch.")
        elif c and (m := check_script(c, target, where=f"Chú thích ảnh {md.id}")):
            problems.append(m)
        media.append(MediaText(id=md.id, caption=(c or "")[: rules.CAPTION_MAX]))

    # ---- Tóm tắt đã dịch ----
    summary: SummaryText | None = None
    if req.summary is not None:
        if raw.summary is None:
            problems.append("Thiếu `summary` đã dịch.")
        else:
            s_short = _single_paragraph(strip_markdown(raw.summary.shortText))
            s_det = strip_markdown(raw.summary.detailedText)
            if not s_short or not s_det:
                problems.append("`summary` đã dịch thiếu bản ngắn hoặc bản chi tiết.")
            else:
                if len(s_short) > rules.SUMMARY_SHORT_MAX_CHARS:
                    problems.append(f"`summary.shortText` dài {len(s_short)} ký tự, tối đa {rules.SUMMARY_SHORT_MAX_CHARS}.")
                for label, original, translated in (
                    ("summary.shortText", req.summary.short_text, s_short),
                    ("summary.detailedText", req.summary.detailed_text, s_det),
                ):
                    if not _fit_ratio(original, translated):
                        problems.append(f"`{label}` đã dịch có độ dài lệch quá nhiều so với bản gốc.")
                    if (m := check_script(translated, target, where=f"`{label}`")):
                        problems.append(m)
                summary = SummaryText(short_text=s_short, detailed_text=s_det)

    # ---- Thuật ngữ tên riêng ----
    all_out = "\n".join(
        [name or "", short_description or "", content or ""]
        + [f"{t.name} {t.description or ''}" for t in timelines]
        + [f"{e.name} {e.description or ''}" for e in events]
        + [m.caption for m in media]
        + ([summary.short_text, summary.detailed_text] if summary else [])
    )
    missing = missing_terms(glossary_terms(req), target, all_out)
    if missing:
        problems.append("Chưa dùng đúng bảng thuật ngữ cho: " + ", ".join(missing) + ".")

    if problems:
        return Outcome(problems=problems)
    text = HeritageText(
        name=(name or "")[: rules.NAME_MAX],
        short_description=short_description[: rules.SHORT_DESCRIPTION_MAX] if short_description else None,
        content=content,
        timelines=timelines,
        events=events,
        media=media,
    )
    return Outcome(value=TranslateResponse(content=text, summary=summary, model="", usage=Usage()), done=True)
