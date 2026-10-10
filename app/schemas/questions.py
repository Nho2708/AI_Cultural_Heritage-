from __future__ import annotations

from pydantic import Field

from .common import CamelModel, Difficulty, HeritageInput, QuestionType, Usage


class QuestionsRequest(CamelModel):
    generation_id: int = 0
    lesson_id: int = 0
    grade_level: int = Field(ge=1, le=3)
    count: int = Field(ge=1, le=20)
    difficulty: Difficulty
    types: list[QuestionType] = Field(min_length=1)
    heritages: list[HeritageInput] = Field(min_length=1, max_length=10)


class Option(CamelModel):
    content: str | None = None
    image_url: str | None = None
    is_correct: bool = False


class Pair(CamelModel):
    left: str | None = None
    left_image_url: str | None = None
    right: str | None = None


class Blank(CamelModel):
    accepted: list[str] | None = None


class Statement(CamelModel):
    text: str | None = None
    is_true: bool = False


class GeneratedQuestion(CamelModel):
    heritage_id: int
    question_type: QuestionType
    content: str | None = None
    explanation: str | None = None
    image_url: str | None = None
    passage: str | None = None
    passage_source: str | None = None
    answer_is_true: bool | None = None
    options: list[Option] | None = None
    pairs: list[Pair] | None = None
    steps: list[str] | None = None
    blanks: list[Blank] | None = None
    distractors: list[str] | None = None
    statements: list[Statement] | None = None


class QuestionsResponse(CamelModel):
    questions: list[GeneratedQuestion]
    model: str
    usage: Usage
