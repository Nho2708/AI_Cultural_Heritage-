"""Bộ gọi Claude với SDK giả (không mạng): tham số gửi đi đúng quy tắc Haiku 5.5, đọc khối nội dung, stop_reason, ánh xạ lỗi sang mã backend chờ."""
from __future__ import annotations

import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.errors import ModelUnavailable, ServiceError
from app.llm.client import AnthropicLlm

from .conftest import FakeLlm, ok
from .factories import compose_request, lesson_output

REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def response_of(status: int) -> httpx2.Response:
    return httpx2.Response(status, request=REQ)


class FakeMessages:
    def __init__(self, result):
        self.result = result
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def fake_client(result) -> tuple[SimpleNamespace, FakeMessages]:
    messages = FakeMessages(result)
    return SimpleNamespace(messages=messages), messages


def message(blocks, stop_reason="end_turn", usage=None, model="claude-haiku-5-5"):
    return SimpleNamespace(
        content=blocks, stop_reason=stop_reason, model=model,
        usage=usage or SimpleNamespace(input_tokens=100, output_tokens=40, cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


def text(value) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))


async def call(llm: AnthropicLlm, **kw):
    params = dict(api="compose-lesson", system="hệ thống", user="người dùng", schema={"type": "object"}, effort="medium", max_tokens=1000, timeout=30.0)
    params.update(kw)
    return await llm.complete_json(**params)


async def test_request_follows_haiku_5_5_rules():
    client, messages = fake_client(message([text({"a": 1})]))
    result = await call(AnthropicLlm(client, "claude-haiku-5-5"), effort="low", max_tokens=777, timeout=12.5)

    assert result.data == {"a": 1}
    sent = messages.calls[0]
    assert sent["model"] == "claude-haiku-5-5"
    for forbidden in ("temperature", "top_p", "top_k", "thinking"):
        assert forbidden not in sent
    assert sent["max_tokens"] == 777 and sent["timeout"] == 12.5
    assert sent["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": {"type": "object"}}}
    # không prefill: tin nhắn cuối là của người dùng, và chỉ có một tin nhắn
    assert [m["role"] for m in sent["messages"]] == ["user"]
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "budget_tokens" not in json.dumps(sent, default=str)


async def test_thinking_blocks_before_text_are_skipped_and_usage_includes_cache():
    usage = SimpleNamespace(input_tokens=100, output_tokens=300, cache_read_input_tokens=2000, cache_creation_input_tokens=50)
    msg = message([SimpleNamespace(type="thinking", thinking="", signature="x"), text({"ok": True})], usage=usage, model="claude-haiku-5-5-x")
    result = await call(AnthropicLlm(fake_client(msg)[0], "claude-haiku-5-5"))
    assert result.data == {"ok": True} and result.model == "claude-haiku-5-5-x"
    assert result.usage.total_input == 2150 and result.usage.output_tokens == 300
    assert result.usage.cache_read_tokens == 2000 and result.usage.cache_write_tokens == 50


async def test_max_tokens_is_reported_as_truncated():
    msg = message([SimpleNamespace(type="thinking", thinking="", signature="x")], stop_reason="max_tokens")
    result = await call(AnthropicLlm(fake_client(msg)[0], "m"))
    assert result.truncated and result.data is None and result.usage.output_tokens == 40


async def test_refusal_is_422_not_retryable():
    msg = message([], stop_reason="refusal")
    with pytest.raises(ServiceError) as info:
        await call(AnthropicLlm(fake_client(msg)[0], "m"))
    assert info.value.status == 422 and info.value.code == "model_refused" and not info.value.retryable


async def test_no_text_block_and_bad_json_become_parse_errors():
    result = await call(AnthropicLlm(fake_client(message([SimpleNamespace(type="thinking", thinking="", signature="x")]))[0], "m"))
    assert result.data is None and result.parse_error
    result = await call(AnthropicLlm(fake_client(message([text("{không phải json")]))[0], "m"))
    assert result.data is None and result.parse_error


@pytest.mark.parametrize(
    "exc,status,code",
    [
        (anthropic.APITimeoutError(request=REQ), 504, "llm_timeout"),
        (anthropic.APIConnectionError(request=REQ), 503, "llm_unreachable"),
        (anthropic.RateLimitError("429", response=response_of(429), body=None), 503, "llm_rate_limited"),
        (anthropic.InternalServerError("500", response=response_of(500), body=None), 502, "llm_unavailable"),
        (anthropic.APIStatusError("529", response=response_of(529), body=None), 503, "llm_unavailable"),
        (anthropic.APIStatusError("502", response=response_of(502), body=None), 502, "llm_unavailable"),
        (anthropic.AuthenticationError("401", response=response_of(401), body=None), 503, "llm_not_ready"),
        (anthropic.PermissionDeniedError("403", response=response_of(403), body=None), 503, "llm_not_ready"),
        (anthropic.NotFoundError("404", response=response_of(404), body=None), 503, "llm_not_ready"),
        (anthropic.BadRequestError("400", response=response_of(400), body=None), 502, "llm_bad_request"),
    ],
)
async def test_anthropic_errors_map_to_backend_status_codes(exc, status, code):
    llm = AnthropicLlm(fake_client(exc)[0], "m")
    with pytest.raises(ModelUnavailable) as info:
        await call(llm)
    assert info.value.status == status and info.value.code == code
    assert info.value.retryable is True  # backend thử lại 5xx; 503/502/504 đều thuộc nhóm này


async def test_exhausted_credit_balance_is_503_billing_not_a_bad_request():
    exc = anthropic.BadRequestError(
        "Your credit balance is too low to access the Anthropic API.", response=response_of(400), body=None
    )
    with pytest.raises(ModelUnavailable) as info:
        await call(AnthropicLlm(fake_client(exc)[0], "m"))
    assert info.value.status == 503 and info.value.code == "llm_billing"


async def test_missing_api_key_is_503_without_network():
    with pytest.raises(ModelUnavailable) as info:
        await call(AnthropicLlm(None, "m"))
    assert info.value.status == 503 and info.value.code == "llm_not_configured"


async def test_end_to_end_through_the_api_with_anthropic_errors(make_client):
    """Lỗi 429/5xx/mạng của Anthropic ra tới backend đúng mã thử lại được; từ chối là 422."""
    req = compose_request(2)
    cases = [
        (anthropic.RateLimitError("429", response=response_of(429), body=None), 503),
        (anthropic.InternalServerError("500", response=response_of(500), body=None), 502),
        (anthropic.APIConnectionError(request=REQ), 503),
        (anthropic.APITimeoutError(request=REQ), 504),
    ]
    for exc, status in cases:
        client, messages = fake_client(exc)
        r = await make_client(AnthropicLlm(client, "claude-haiku-5-5")).post("/v1/compose-lesson", json=req)
        assert r.status_code == status
        assert len(messages.calls) == 1  # việc thử lại do backend quyết định

    client, _ = fake_client(message([], stop_reason="refusal"))
    r = await make_client(AnthropicLlm(client, "claude-haiku-5-5")).post("/v1/compose-lesson", json=req)
    assert r.status_code == 422 and r.json()["errorCode"] == "model_refused"


async def test_full_pipeline_with_fake_sdk_returns_valid_lesson(make_client):
    req = compose_request(2)
    client, messages = fake_client(message([text(lesson_output(2, req))]))
    r = await make_client(AnthropicLlm(client, "claude-haiku-5-5")).post("/v1/compose-lesson", json=req)
    assert r.status_code == 200 and r.json()["usage"] == {"inputTokens": 100, "outputTokens": 40}
    assert messages.calls[0]["output_config"]["effort"] == "medium"
