from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import CamelModel, Usage


class TimelineText(CamelModel):
    id: int
    name: str = ""
    description: str | None = None


class EventText(CamelModel):
    id: int
    timeline_id: int
    name: str = ""
    description: str | None = None


class MediaText(CamelModel):
    id: int
    caption: str = ""


class HeritageText(CamelModel):
    name: str = ""
    short_description: str | None = None
    content: str | None = None
    timelines: list[TimelineText] = Field(default_factory=list)
    events: list[EventText] = Field(default_factory=list)
    media: list[MediaText] = Field(default_factory=list)


class SummaryText(CamelModel):
    short_text: str
    detailed_text: str


class SummarizeRequest(CamelModel):
    generation_id: int = 0
    heritage_id: int = 0
    source: HeritageText


class SummarizeResponse(CamelModel):
    short_text: str
    detailed_text: str
    model: str
    usage: Usage


class TargetLanguage(str, Enum):
    en = "en"
    ko = "ko"
    zh_hans = "zh-Hans"
    ja = "ja"


class ContentLanguage(str, Enum):
    vi = "vi"
    en = "en"


class TranslateRequest(CamelModel):
    generation_id: int = 0
    heritage_id: int = 0
    target_language: TargetLanguage
    content_language: ContentLanguage
    content: HeritageText
    summary_language: ContentLanguage | None = None
    summary: SummaryText | None = None


class TranslateResponse(CamelModel):
    content: HeritageText
    summary: SummaryText | None = None
    model: str
    usage: Usage
