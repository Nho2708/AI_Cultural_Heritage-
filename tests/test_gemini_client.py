"""Bộ gọi Gemini với máy chủ giả (httpx.MockTransport, không mạng): thân yêu cầu, đọc phần chữ, finishReason, ánh xạ lỗi sang mã backend chờ."""
from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.errors import ModelUnavailable, ServiceError
from app.llm.client import AnthropicLlm
from app.llm.factory import build_llm
from app.llm.gemini import GeminiLlm

from .conftest import INTERNAL_KEY
from .factories import compose_request, lesson_output

KEY = "khoa-gemini-gia"


class FakeGemini:
    """Máy chủ giả: trả lần lượt các phản hồi đã cho (dict JSON 200, httpx.Response, hoặc ngoại lệ); ghi lại yêu cầu."""

    def __init__(self, *items):
        self.items = list(items)
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.items.pop(0) if len(self.items) > 1 else self.items[0]
        if isinstance(item, Exception):
            raise item
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(200, json=item)

    def llm(self, model: str = "gemini-3.8-flash", **kw) -> GeminiLlm:
        return GeminiLlm(KEY, model, http=httpx.AsyncClient(transport=httpx.MockTransport(self.handler)), **kw)

    def body(self, i: int = -1) -> dict:
        return json.loads(self.requests[i].content)


def reply(data, finish="STOP", thoughts=None, usage=None, model="gemini-3.8-flash") -> dict:
    parts = []
    if thoughts:
        parts.append({"text": thoughts, "thought": True})
    parts.append({"text": data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)})
    return {
        "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}],
        "usageMetadata": usage or {"promptTokenCount": 120, "candidatesTokenCount": 40, "thoughtsTokenCount": 15, "totalTokenCount": 175},
        "modelVersion": model,
    }


def error(status: int, message: str = "lỗi") -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": status, "message": message, "status": "X"}})


async def call(llm: GeminiLlm, **kw):
    params = {"api": "compose-lesson", "system": "hệ thống", "user": "người dùng", "schema": {"type": "object"}, "effort": "medium", "max_tokens": 1000, "timeout": 30.0}
    params.update(kw)
    return await llm.complete_json(**params)


async def test_request_body_uses_json_schema_thinking_level_and_header_key():
    fake = FakeGemini(reply({"a": 1}))
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"], "additionalProperties": False}
    result = await call(fake.llm(), schema=schema, effort="low", max_tokens=777)

    req = fake.requests[0]
    assert req.url.path.endswith("/models/gemini-3.8-flash:generateContent")
    assert req.headers["x-goog-api-key"] == KEY and KEY not in str(req.url)  # khóa chỉ ở tiêu đề
    body = fake.body()
    assert body["systemInstruction"] == {"parts": [{"text": "hệ thống"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "người dùng"}]}]
    config = body["generationConfig"]
    assert config == {
        "responseMimeType": "application/json",
        "maxOutputTokens": 777,
        "responseJsonSchema": schema,
        "thinkingConfig": {"thinkingLevel": "low"},
    }
    assert result.data == {"a": 1} and result.model == "gemini-3.8-flash"


async def test_thinking_parts_are_skipped_and_usage_counts_thoughts_as_output():
    fake = FakeGemini(reply({"ok": True}, thoughts="đang nghĩ...", usage={"promptTokenCount": 300, "cachedContentTokenCount": 100,
                                                                         "candidatesTokenCount": 50, "thoughtsTokenCount": 70}))
    result = await call(fake.llm())
    assert result.data == {"ok": True}
    assert (result.usage.input_tokens, result.usage.cache_read_tokens, result.usage.output_tokens) == (200, 100, 120)
    assert result.usage.total_input == 300


async def test_forced_thinking_level_overrides_effort():
    fake = FakeGemini(reply({"a": 1}))
    await call(fake.llm(thinking_level="low"), effort="medium")
    assert fake.body()["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}


async def test_max_tokens_is_truncated_and_bad_json_is_a_parse_error():
    assert (await call(FakeGemini(reply("{", finish="MAX_TOKENS")).llm())).truncated is True
    result = await call(FakeGemini(reply("{không phải json")).llm())
    assert result.data is None and result.parse_error
    empty = {"candidates": [{"content": {"parts": []}, "finishReason": "STOP"}], "usageMetadata": {}}
    assert (await call(FakeGemini(empty).llm())).parse_error


@pytest.mark.parametrize("payload", [
    {"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": {"promptTokenCount": 10}},
    reply("{}", finish="SAFETY"),
    reply("{}", finish="PROHIBITED_CONTENT"),
    reply("{}", finish="RECITATION"),
])
async def test_blocked_prompt_or_safety_stop_is_a_422_refusal(payload):
    with pytest.raises(ServiceError) as info:
        await call(FakeGemini(payload).llm())
    assert info.value.status == 422 and info.value.code == "model_refused"


@pytest.mark.parametrize(
    "item,status,code",
    [
        (httpx.ReadTimeout("chậm"), 504, "llm_timeout"),
        (httpx.ConnectError("không nối được"), 503, "llm_unreachable"),
        (error(429, "Resource has been exhausted"), 503, "llm_rate_limited"),
        (error(503, "The model is overloaded"), 503, "llm_unavailable"),
        (error(500, "Internal error"), 502, "llm_unavailable"),
        (error(401), 503, "llm_not_ready"),
        (error(403), 503, "llm_not_ready"),
        (error(404, "model not found"), 503, "llm_not_ready"),
        (error(400, "API key not valid. Please pass a valid API key."), 503, "llm_not_ready"),
        (error(400, "Request contains an invalid argument."), 502, "llm_bad_request"),
    ],
)
async def test_gemini_errors_map_to_backend_status_codes(item, status, code):
    fake = FakeGemini(item)
    with pytest.raises(ModelUnavailable) as info:
        await call(fake.llm())
    assert info.value.status == status and info.value.code == code
    assert info.value.retryable is True
    assert len(fake.requests) == 1  # việc thử lại do backend quyết định


def quota_error(seconds: str = "31625s") -> httpx.Response:
    return httpx.Response(429, json={"error": {"code": 429, "message": "You exceeded your current quota", "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": seconds},
    ]}})


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize("failure", [quota_error(), error(503, "This model is currently experiencing high demand."), error(404, "no longer available")])
async def test_quota_overload_or_missing_model_moves_to_the_next_model_in_the_same_request(failure):
    fake = FakeGemini(failure, reply({"a": 1}, model="gemini-3.6-flash"))
    llm = fake.llm(fallback_models=["gemini-3.5-flash", "gemini-3.5-flash-lite"])
    result = await call(llm)
    assert result.data == {"a": 1} and result.model == "gemini-3.6-flash"
    assert [r.url.path.rsplit("/", 1)[-1] for r in fake.requests] == ["gemini-3.8-flash:generateContent", "gemini-3.5-flash:generateContent"]


async def test_exhausted_model_rests_until_the_suggested_delay_then_is_used_again():
    clock = Clock()
    fake = FakeGemini(quota_error("120s"), reply({"a": 1}))
    llm = GeminiLlm(KEY, "gemini-3.8-flash", fallback_models=["gemini-3.5-flash"], clock=clock,
                    http=httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    await call(llm)
    await call(llm)  # mô hình chính đang nghỉ: gọi thẳng mô hình dự phòng
    assert [r.url.path.rsplit("/", 1)[-1].split(":")[0] for r in fake.requests] == ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash"]
    clock.now += 121
    await call(llm)
    assert fake.requests[-1].url.path.endswith("gemini-3.8-flash:generateContent")


async def test_all_models_exhausted_is_503_rate_limited_without_calling_again():
    clock = Clock()
    fake = FakeGemini(quota_error())
    llm = GeminiLlm(KEY, "gemini-3.8-flash", fallback_models=["gemini-3.5-flash"], clock=clock,
                    http=httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    with pytest.raises(ModelUnavailable) as info:
        await call(llm)
    assert (info.value.status, info.value.code, len(fake.requests)) == (503, "llm_rate_limited", 2)
    with pytest.raises(ModelUnavailable) as again:
        await call(llm)
    assert again.value.code == "llm_rate_limited" and len(fake.requests) == 2  # không gọi lại mô hình đang nghỉ


async def test_timeout_does_not_try_other_models():
    fake = FakeGemini(httpx.ReadTimeout("chậm"))
    with pytest.raises(ModelUnavailable) as info:
        await call(fake.llm(fallback_models=["gemini-3.5-flash"]))
    assert info.value.code == "llm_timeout" and len(fake.requests) == 1  # thời gian của yêu cầu đã hết


async def test_schema_rejection_falls_back_to_plain_json_in_the_prompt():
    fake = FakeGemini(error(400, "Invalid JSON payload: unknown keyword in response_json_schema"), reply('Đây: {"a": 2}'))
    llm = fake.llm()
    result = await call(llm, schema={"type": "object", "properties": {"a": {"type": "integer"}}})
    assert result.data == {"a": 2} and llm.structured is False
    second = fake.body(1)
    assert "responseJsonSchema" not in second["generationConfig"]
    assert '"a"' in second["systemInstruction"]["parts"][0]["text"]  # lược đồ nằm trong prompt


async def test_unsupported_thinking_level_drops_the_thinking_config():
    fake = FakeGemini(error(400, "Thinking level MEDIUM is not supported for this model."), reply({"a": 1}))
    result = await call(fake.llm("gemini-3.5-flash-lite"))
    assert result.data == {"a": 1} and "thinkingConfig" not in fake.body(1)["generationConfig"]


async def test_missing_api_key_is_503_without_network():
    fake = FakeGemini(reply({}))
    llm = GeminiLlm(None, "gemini-3.8-flash", http=httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    with pytest.raises(ModelUnavailable) as info:
        await call(llm)
    assert info.value.code == "llm_not_configured" and not fake.requests


def test_factory_picks_the_provider_from_settings():
    gemini = build_llm(Settings(ai_internal_key=INTERNAL_KEY, ai_provider="gemini", gemini_api_key=KEY, gemini_model="gemini-3.5-flash"))
    assert isinstance(gemini, GeminiLlm) and gemini.model == "gemini-3.5-flash"
    assert gemini.models == ["gemini-3.5-flash", "gemini-3.5-flash-lite"]  # mô hình chính không lặp lại trong danh sách dự phòng
    single = build_llm(Settings(ai_internal_key=INTERNAL_KEY, ai_provider="gemini", gemini_api_key=KEY, gemini_fallback_models=""))
    assert single.models == ["gemini-3.8-flash"]
    claude = build_llm(Settings(ai_internal_key=INTERNAL_KEY, anthropic_api_key="khong-dung"))
    assert isinstance(claude, AnthropicLlm) and claude.model == "claude-haiku-5-5"
    no_key = Settings(ai_internal_key=INTERNAL_KEY, ai_provider="gemini", anthropic_api_key="co-khoa-claude-nhung-khong-dung")
    assert no_key.llm_configured() is False and no_key.model_name() == "gemini-3.8-flash"


async def test_full_pipeline_with_fake_gemini_returns_valid_lesson(make_client):
    req = compose_request(2)
    fake = FakeGemini(reply(lesson_output(2, req)))
    r = await make_client(fake.llm()).post("/v1/compose-lesson", json=req)
    assert r.status_code == 200, r.text
    assert len(fake.requests) == 1


async def test_health_reports_provider_and_model(make_client):
    r = await make_client(FakeGemini(reply({})).llm(), ai_provider="gemini", gemini_api_key=KEY).get("/health")
    assert r.json() == {"status": "ok", "provider": "gemini", "model": "gemini-3.8-flash", "llmConfigured": True, "tts": "off"}
