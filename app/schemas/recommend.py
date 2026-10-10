from __future__ import annotations

from pydantic import Field

from .common import CamelModel


class HeritageFeatures(CamelModel):
    id: int
    name: str | None = None
    type: str | None = None
    province_id: int | None = None
    region: str | None = None
    level: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    text: str | None = None


class WeightedHeritage(CamelModel):
    heritage: HeritageFeatures
    weight: float = 1.0


class RankRequest(CamelModel):
    student_id: int | None = None
    level: int | None = None
    target_difficulty: str | None = None
    references: list[WeightedHeritage] = Field(default_factory=list, max_length=200)
    candidates: list[HeritageFeatures] = Field(default_factory=list, max_length=5000)


class Related(CamelModel):
    heritage_id: int
    score: float
    reason: str


class RankResponse(CamelModel):
    related: list[Related]
