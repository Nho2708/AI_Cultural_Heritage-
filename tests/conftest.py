from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.llm.client import LlmResult, TokenUsage
from app.main import create_app

INTERNAL_KEY = "khoa-noi-bo-thu-nghiem"
HEADERS = {"X-Internal-Key": INTERNAL_KEY, "X-Correlation-Id": "test-corr-1"}


class FakeLlm:
    """Mô hình giả: trả lần lượt các phần tử đã cho (LlmResult hoặc ngoại lệ); hết thì lặp phần tử cuối."""

    model = "claude-haiku-5-5"

    def __init__(self, *items):
        self.items = list(items)
        self.calls: list[dict] = []

    async def complete_json(self, **kwargs):
        self.calls.append(kwargs)
        item = self.items.pop(0) if len(self.items) > 1 else self.items[0]
        if isinstance(item, Exception):
            raise item
        return item


def ok(data, input_tokens: int = 100, output_tokens: int = 50, **kw) -> LlmResult:
    return LlmResult(data, TokenUsage(input_tokens, output_tokens), "claude-haiku-5-5", **kw)


def truncated(input_tokens: int = 100, output_tokens: int = 999) -> LlmResult:
    return LlmResult(None, TokenUsage(input_tokens, output_tokens), "claude-haiku-5-5", truncated=True, stop_reason="max_tokens")


@pytest.fixture
def make_client():
    clients: list[httpx.AsyncClient] = []

    def factory(llm, **settings) -> httpx.AsyncClient:
        cfg = Settings(ai_internal_key=INTERNAL_KEY, anthropic_api_key="khong-dung", **settings)
        app = create_app(cfg, llm, configure_logging=False)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=HEADERS)
        clients.append(client)
        return client

    yield factory
