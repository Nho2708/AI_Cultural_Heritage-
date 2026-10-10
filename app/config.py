"""Cấu hình dịch vụ AI, đọc từ biến môi trường và hai tệp .env (không bao giờ in giá trị khóa)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_DIR = Path(__file__).resolve().parent.parent


def env_files() -> tuple[str, ...]:
    r"""Tệp .env theo thứ tự ưu tiên tăng dần: %APPDATA%\DSVHVN\ai-service.env rồi .env trong thư mục dịch vụ.

    Biến môi trường của tiến trình luôn thắng cả hai tệp. Tệp nào không có thì bỏ qua.
    """
    files: list[str] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        files.append(str(Path(appdata) / "DSVHVN" / "ai-service.env"))
    files.append(str(SERVICE_DIR / ".env"))
    return tuple(files)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    anthropic_api_key: SecretStr | None = None
    ai_internal_key: SecretStr | None = None
    ai_model: str = "claude-haiku-5-5"

    # Thời gian (giây). Ngân sách tổng cho một yêu cầu phải nhỏ hơn thời gian chờ của backend
    # (45 giây soạn bài và sinh câu, 90 giây dịch và tóm tắt) để gọi lại một lần vẫn kịp.
    ai_llm_timeout_seconds: float = Field(default=40.0, gt=0)
    ai_budget_seconds: float = Field(default=43.0, gt=0)
    ai_heritage_llm_timeout_seconds: float = Field(default=80.0, gt=0)
    ai_heritage_budget_seconds: float = Field(default=88.0, gt=0)
    ai_log_level: str = "INFO"

    def llm_configured(self) -> bool:
        return self.anthropic_api_key is not None and bool(self.anthropic_api_key.get_secret_value().strip())

    def internal_key_value(self) -> str:
        return self.ai_internal_key.get_secret_value() if self.ai_internal_key else ""


def load_settings() -> Settings:
    return Settings(_env_file=env_files())  # type: ignore[call-arg]


@lru_cache
def get_settings() -> Settings:
    return load_settings()
