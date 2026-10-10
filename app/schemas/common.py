"""Kiểu chung: JSON camelCase, UTF-8, đúng hợp đồng backend."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class Usage(CamelModel):
    input_tokens: int = 0
    output_tokens: int = 0


class LessonLength(str, Enum):
    SHORT = "SHORT"
    MEDIUM = "MEDIUM"
    DETAILED = "DETAILED"


class Difficulty(str, Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class QuestionType(str, Enum):
    SINGLE_CHOICE = "SINGLE_CHOICE"
    TRUE_FALSE = "TRUE_FALSE"
    IMAGE_CHOICE = "IMAGE_CHOICE"
    MATCHING = "MATCHING"
    ORDERING = "ORDERING"
    FILL_BLANK = "FILL_BLANK"
    MULTI_TRUE_FALSE = "MULTI_TRUE_FALSE"
    SOURCE_READING = "SOURCE_READING"


class SectionKind(str, Enum):
    STORY = "STORY"
    IMAGE = "IMAGE"
    READING = "READING"
    MILESTONE = "MILESTONE"
    SOURCE_EXCERPT = "SOURCE_EXCERPT"
    REFLECTION = "REFLECTION"


# ---- Dữ liệu di sản gửi kèm khi soạn bài và sinh câu (AiHeritageInput của backend) ----

class TimelineInput(CamelModel):
    event_id: int
    phase: str = ""
    name: str = ""
    description: str | None = None
    start_year: int = 0
    date_label: str = ""


class SourceInput(CamelModel):
    title: str = ""
    url: str | None = None


class ImageInput(CamelModel):
    media_id: int
    url: str
    caption: str | None = None


class HeritageInput(CamelModel):
    heritage_id: int
    name: str
    short_description: str | None = None
    content: str | None = None
    timeline: list[TimelineInput] = Field(default_factory=list)
    sources: list[SourceInput] = Field(default_factory=list)
    images: list[ImageInput] = Field(default_factory=list)
