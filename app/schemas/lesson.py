from __future__ import annotations

from pydantic import Field, field_validator, model_validator

from .. import rules
from .common import CamelModel, HeritageInput, LessonLength, SectionKind, Usage


class ComposeRequest(CamelModel):
    generation_id: int = 0
    lesson_id: int = 0
    grade_level: int = Field(ge=1, le=3)
    length: LessonLength = LessonLength.MEDIUM
    heritages: list[HeritageInput] = Field(min_length=1, max_length=10)
    current_content: str = ""
    # Yêu cầu thêm của giáo viên về trọng tâm, cách viết (không bắt buộc). Cắt khoảng trắng hai đầu; rỗng thì prompt không có khối này.
    teacher_note: str = Field(default="", max_length=rules.TEACHER_NOTE_MAX)

    @field_validator("teacher_note", mode="before")
    @classmethod
    def _strip_note(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


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


# Loại phần được viết lại và cấp học dùng được (đoạn trích tư liệu phải nguyên văn nên không viết lại).
_REWRITE_KIND_LEVELS: dict[SectionKind, tuple[int, int]] = {
    SectionKind.STORY: (1, 1),
    SectionKind.IMAGE: (1, 3),
    SectionKind.READING: (2, 3),
    SectionKind.MILESTONE: (1, 3),
    SectionKind.REFLECTION: (3, 3),
}


class RewriteSectionRequest(CamelModel):
    generation_id: int = 0
    lesson_id: int = 0
    grade_level: int = Field(ge=1, le=3)
    kind: SectionKind
    current_text: str = Field(min_length=1, max_length=rules.REWRITE_TEXT_MAX)
    title: str | None = Field(default=None, max_length=rules.REWRITE_TITLE_MAX)
    year: int | None = Field(default=None, ge=rules.MIN_YEAR, le=2100)
    teacher_note: str = Field(default="", max_length=rules.TEACHER_NOTE_MAX)
    lesson_content: str = Field(default="", max_length=rules.REWRITE_LESSON_CONTENT_MAX)
    heritages: list[HeritageInput] = Field(min_length=1, max_length=10)

    @field_validator("teacher_note", mode="before")
    @classmethod
    def _strip_note(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _check_kind(self) -> RewriteSectionRequest:
        levels = _REWRITE_KIND_LEVELS.get(self.kind)
        if levels is None:
            raise ValueError("Loại phần này không viết lại được (đoạn trích tư liệu phải nguyên văn).")
        if not levels[0] <= self.grade_level <= levels[1]:
            raise ValueError("Loại phần không thuộc khung của cấp học này.")
        if not self.current_text.strip():
            raise ValueError("Chữ cần viết lại đang rỗng.")
        return self


class RewriteSectionResponse(CamelModel):
    text: str
    title: str | None = None
    model: str
    usage: Usage
