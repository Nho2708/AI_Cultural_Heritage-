"""Cấu hình dịch vụ AI, đọc từ biến môi trường và hai tệp .env (không bao giờ in giá trị khóa)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_DIR = Path(__file__).resolve().parent.parent


def env_files() -> tuple[str, ...]:
    r"""Tệp .env theo thứ tự ưu tiên tăng dần: %APPDATA%\DSVHVN\ai-service.env, .env trong thư mục dịch vụ, rồi tệp ở AI_ENV_FILE.

    AI_ENV_FILE dùng khi dịch vụ chạy dưới IIS trên máy demo (tài khoản app pool không có %APPDATA% của người dùng):
    web.config trỏ tới C:\dsvhvn\cau-hinh\ai.env. Biến môi trường của tiến trình luôn thắng mọi tệp. Tệp nào không có thì bỏ qua.
    """
    files: list[str] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        files.append(str(Path(appdata) / "DSVHVN" / "ai-service.env"))
    files.append(str(SERVICE_DIR / ".env"))
    explicit = os.environ.get("AI_ENV_FILE", "").strip()
    if explicit:
        files.append(explicit)
    return tuple(files)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    # Nhà cung cấp mô hình: "anthropic" (Claude, trả phí theo lượt) hoặc "gemini" (Google AI Studio, có hạn mức miễn phí).
    ai_provider: Literal["anthropic", "gemini"] = "anthropic"
    anthropic_api_key: SecretStr | None = None
    ai_internal_key: SecretStr | None = None
    ai_model: str = "claude-haiku-5-5"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    # Mô hình dự phòng (phân cách bằng dấu phẩy): bản miễn phí giới hạn số lượt mỗi ngày theo từng mô hình, mô hình chính hết hạn mức
    # hoặc quá tải thì gọi mô hình kế tiếp. Để rỗng nếu chỉ muốn dùng một mô hình.
    gemini_fallback_models: str = "gemini-3.5-flash,gemini-3.5-flash-lite"
    # Mức suy nghĩ cho mọi lời gọi Gemini. Mặc định "low": ở hạn mức miễn phí, mức "medium" làm một lần soạn bài mất hơn 40 giây,
    # quá thời gian chờ của backend; "low" khoảng 15 giây và vẫn qua bộ kiểm. Đặt rỗng để theo effort của từng API.
    gemini_thinking_level: str | None = "low"

    # Thời gian (giây). Ngân sách tổng cho một yêu cầu phải nhỏ hơn thời gian chờ của backend
    # (45 giây soạn bài và sinh câu, 90 giây dịch và tóm tắt) để gọi lại một lần vẫn kịp.
    ai_llm_timeout_seconds: float = Field(default=40.0, gt=0)
    ai_budget_seconds: float = Field(default=43.0, gt=0)
    ai_heritage_llm_timeout_seconds: float = Field(default=80.0, gt=0)
    ai_heritage_budget_seconds: float = Field(default=88.0, gt=0)
    ai_log_level: str = "INFO"

    # Giọng đọc tiếng Việt tự host (POST /v1/tts, VieNeu-TTS v3 Turbo). Mặc định tắt: máy chỉ cài requirements.txt (CI, máy demo
    # IIS) không có gói giọng đọc. Ảnh Docker đặt GIONG_DOC_BAT=1.
    giong_doc_bat: bool = False
    # Số luồng tính của ONNX Runtime / OMP; máy chủ 2 vCPU thì để 2.
    giong_doc_luong: int = Field(default=2, ge=1, le=32)
    # "auto": int8 khi CPU có VNNI (Linux đọc /proc/cpuinfo), không thì fp32; "int8" hoặc "fp32" để ép.
    giong_doc_do_chinh_xac: Literal["auto", "int8", "fp32"] = "auto"

    def provider_key(self) -> str | None:
        """Khóa của nhà cung cấp đang chọn (None nếu chưa đặt)."""
        secret = self.gemini_api_key if self.ai_provider == "gemini" else self.anthropic_api_key
        value = secret.get_secret_value().strip() if secret else ""
        return value or None

    def llm_configured(self) -> bool:
        return self.provider_key() is not None

    def model_name(self) -> str:
        return self.gemini_model if self.ai_provider == "gemini" else self.ai_model

    def internal_key_value(self) -> str:
        return self.ai_internal_key.get_secret_value() if self.ai_internal_key else ""


def load_settings() -> Settings:
    return Settings(_env_file=env_files())  # type: ignore[call-arg]


@lru_cache
def get_settings() -> Settings:
    return load_settings()
