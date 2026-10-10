from __future__ import annotations

from pydantic import Field

from .common import CamelModel, HeritageInput, LessonLength, SectionKind, Usage


class ComposeRequest(CamelModel):
    generation_id: int = 0
    lesson_id: int = 0
    grade_level: int = Field(ge=1, le=3)
    length: LessonLength = LessonLength.MEDIUM
    heritages: list[HeritageInput] = Field(min_length=1, max_length=10)
    current_content: str = ""


class ComposedStep(CamelModel):
    kind: SectionKind
    text: str | None = None
    media_id: int | None = None
    year: int | None = None
    event_id: int | None = None
    title: str | None = None


class SourceQuote(CamelModel):
    heritage_id: int
    quote: str
    source: str


class ComposeResponse(CamelModel):
    content: str
    steps: list[ComposedStep]
    source_quotes: list[SourceQuote]
    key_points: list[str]
    grade_level: int
    length: LessonLength
    model: str
    usage: Usage
