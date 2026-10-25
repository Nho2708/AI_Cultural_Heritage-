"""Lược đồ yêu cầu của POST /v1/tts (phản hồi là tệp audio/mpeg, không có thân JSON)."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from .common import CamelModel

CHU_TOI_DA = 1000


class TtsRequest(CamelModel):
    text: str = Field(min_length=1, max_length=CHU_TOI_DA)
    voice: Literal["vieneu-mai-anh"] = "vieneu-mai-anh"

    @field_validator("text")
    @classmethod
    def _co_chu(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Chữ cần đọc không được để trống.")
        return v
