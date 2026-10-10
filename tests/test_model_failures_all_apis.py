"""Cùng một bộ tình huống lỗi của mô hình chạy trên cả bốn API dùng mô hình: đầu ra sai lược đồ, cắt cụt, từ chối, lỗi nhà cung cấp."""
from __future__ import annotations

import anthropic
import pytest

from app.llm.client import AnthropicLlm

from .conftest import FakeLlm, ok, truncated
from .factories import compose_request, questions_request, translate_request
from .test_anthropic_client import REQ, fake_client, message, response_of
from .test_heritage import summarize_request

CASES = {
    "compose-lesson": compose_request(2),
    "generate-questions": questions_request(2, ["SINGLE_CHOICE"], count=2),
    "summarize-heritage": summarize_request(),
    "translate-heritage": translate_request("ko"),
}


@pytest.mark.parametrize("endpoint", CASES)
async def test_wrong_schema_twice_is_502_after_exactly_two_calls(make_client, endpoint):
    llm = FakeLlm(ok({"khong": "dung"}))
    r = await make_client(llm).post(f"/v1/{endpoint}", json=CASES[endpoint])
    assert r.status_code == 502 and r.json()["errorCode"] == "invalid_model_output"
    assert len(llm.calls) == 2
    assert "LƯU Ý" in llm.calls[1]["user"]


@pytest.mark.parametrize("endpoint", CASES)
async def test_truncated_twice_is_502_with_more_room_on_the_second_call(make_client, endpoint):
    llm = FakeLlm(truncated())
    r = await make_client(llm).post(f"/v1/{endpoint}", json=CASES[endpoint])
    assert r.status_code == 502 and len(llm.calls) == 2
    assert llm.calls[1]["max_tokens"] > llm.calls[0]["max_tokens"]


@pytest.mark.parametrize("endpoint", CASES)
async def test_refusal_is_422_after_one_call(make_client, endpoint):
    client, messages = fake_client(message([], stop_reason="refusal"))
    r = await make_client(AnthropicLlm(client, "claude-haiku-5-5")).post(f"/v1/{endpoint}", json=CASES[endpoint])
    assert r.status_code == 422 and r.json()["errorCode"] == "model_refused"
    assert len(messages.calls) == 1


@pytest.mark.parametrize("endpoint", CASES)
@pytest.mark.parametrize(
    "exc,status",
    [
        (anthropic.RateLimitError("429", response=response_of(429), body=None), 503),
        (anthropic.InternalServerError("500", response=response_of(500), body=None), 502),
        (anthropic.APIStatusError("529", response=response_of(529), body=None), 503),
        (anthropic.APIConnectionError(request=REQ), 503),
        (anthropic.APITimeoutError(request=REQ), 504),
        (anthropic.AuthenticationError("401", response=response_of(401), body=None), 503),
    ],
)
async def test_provider_errors_map_to_retryable_codes_without_retrying_inside(make_client, endpoint, exc, status):
    client, messages = fake_client(exc)
    r = await make_client(AnthropicLlm(client, "claude-haiku-5-5")).post(f"/v1/{endpoint}", json=CASES[endpoint])
    assert r.status_code == status
    assert r.status_code >= 500  # backend thử lại 5xx
    assert len(messages.calls) == 1


@pytest.mark.parametrize("endpoint", CASES)
async def test_invalid_json_text_is_retried_once(make_client, endpoint):
    from types import SimpleNamespace

    bad = message([SimpleNamespace(type="text", text="không phải json")])
    client, messages = fake_client(bad)
    r = await make_client(AnthropicLlm(client, "claude-haiku-5-5")).post(f"/v1/{endpoint}", json=CASES[endpoint])
    assert r.status_code == 502 and len(messages.calls) == 2
