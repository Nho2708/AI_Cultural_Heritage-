"""Dựng bộ gọi mô hình theo nhà cung cấp đã chọn (AI_PROVIDER)."""
from __future__ import annotations

from ..config import Settings
from .client import AnthropicLlm, Llm
from .gemini import GeminiLlm


def build_llm(settings: Settings) -> Llm:
    """Chưa có khóa thì vẫn dựng bộ gọi: các API dùng mô hình trả 503, rank-related vẫn chạy."""
    key = settings.provider_key()
    if settings.ai_provider == "gemini":
        fallback = [m.strip() for m in settings.gemini_fallback_models.split(",") if m.strip()]
        return GeminiLlm(key, settings.gemini_model, fallback_models=fallback, thinking_level=settings.gemini_thinking_level or None)
    return AnthropicLlm.from_key(key, settings.ai_model) if key else AnthropicLlm(None, settings.ai_model)
