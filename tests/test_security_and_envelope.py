"""Khóa nội bộ, mã tương quan, sức khỏe, lỗi đầu vào, cấu hình và log không lộ khóa."""
from __future__ import annotations

import json
import logging

import httpx
import pytest

from app.config import Settings, env_files
from app.logging_setup import JsonFormatter, correlation_id_var
from app.main import create_app

from .conftest import FakeLlm, INTERNAL_KEY, ok
from .factories import compose_request, lesson_output

ENDPOINTS = ["compose-lesson", "generate-questions", "summarize-heritage", "translate-heritage", "rank-related"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
async def test_missing_or_wrong_internal_key_is_401_with_no_model_call(make_client, endpoint):
    llm = FakeLlm(ok({}))
    client = make_client(llm)
    client.headers.pop("X-Internal-Key")
    r = await client.post(f"/v1/{endpoint}", json={})
    assert r.status_code == 401 and r.json()["errorCode"] == "invalid_internal_key"
    for bad in ("sai-khoa", INTERNAL_KEY + "x", INTERNAL_KEY[:-1], ""):
        r = await client.post(f"/v1/{endpoint}", json={}, headers={"X-Internal-Key": bad})
        assert r.status_code == 401
        assert r.json()["errorCode"] == "invalid_internal_key"
    assert llm.calls == []


async def test_401_comes_before_body_validation(make_client):
    client = make_client(FakeLlm(ok({})))
    r = await client.post("/v1/compose-lesson", content=b"{khong phai json", headers={"X-Internal-Key": "sai", "Content-Type": "application/json"})
    assert r.status_code == 401


async def test_health_needs_no_key_and_reveals_no_secret(make_client):
    client = make_client(FakeLlm(ok({})))
    r = await client.get("/health", headers={})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["model"] == "claude-haiku-5-5" and body["llmConfigured"] is True
    assert INTERNAL_KEY not in r.text and "khong-dung" not in r.text


async def test_correlation_id_is_echoed_and_generated(make_client):
    client = make_client(FakeLlm(ok({})))
    r = await client.get("/health", headers={"X-Correlation-Id": "abc-123"})
    assert r.headers["X-Correlation-Id"] == "abc-123"
    client.headers.pop("X-Correlation-Id")
    r = await client.get("/health")
    assert len(r.headers["X-Correlation-Id"]) >= 16
    r = await client.get("/health", headers={"X-Correlation-Id": "x" * 200 + "<script>"})
    cid = r.headers["X-Correlation-Id"]
    assert len(cid) <= 64 and "<" not in cid


async def test_invalid_body_is_422_without_echoing_input(make_client):
    client = make_client(FakeLlm(ok({})))
    r = await client.post("/v1/compose-lesson", json={"gradeLevel": 7, "heritages": [], "secretField": "NOI-DUNG-NHAY-CAM"})
    assert r.status_code == 422
    body = r.json()
    assert body["errorCode"] == "invalid_request"
    assert "NOI-DUNG-NHAY-CAM" not in r.text
    assert any(d["field"].startswith("gradeLevel") for d in body["details"])
    assert body["correlationId"] == "test-corr-1"


async def test_unknown_enum_is_422(make_client):
    client = make_client(FakeLlm(ok({})))
    req = compose_request(2)
    req["length"] = "HUGE"
    assert (await client.post("/v1/compose-lesson", json=req)).status_code == 422


async def test_unexpected_server_error_is_json_500(make_client):
    class Boom(FakeLlm):
        async def complete_json(self, **kw):
            raise ZeroDivisionError("noi dung nhay cam")

    client = make_client(Boom(ok({})))
    r = await client.post("/v1/compose-lesson", json=compose_request(2))
    assert r.status_code == 500
    assert r.json()["errorCode"] == "internal_error"
    assert "nhay cam" not in r.text


def test_service_refuses_to_start_without_internal_key():
    with pytest.raises(RuntimeError, match="AI_INTERNAL_KEY"):
        create_app(Settings(ai_internal_key=None), FakeLlm(ok({})), configure_logging=False)


def test_settings_load_from_env_file_and_hide_secrets(tmp_path, monkeypatch):
    env = tmp_path / "x.env"
    env.write_text("ANTHROPIC_API_KEY=sk-ant-gia-lap-123\nAI_INTERNAL_KEY=khoa-gia\nAI_MODEL=claude-haiku-5-5\nBIEN_LA=1\n", encoding="utf-8")
    for name in ("ANTHROPIC_API_KEY", "AI_INTERNAL_KEY", "AI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=str(env))  # type: ignore[call-arg]
    assert s.internal_key_value() == "khoa-gia" and s.llm_configured() and s.ai_model == "claude-haiku-5-5"
    assert "sk-ant-gia-lap-123" not in repr(s) and "khoa-gia" not in repr(s) and "khoa-gia" not in str(s)


def test_process_environment_overrides_env_file(tmp_path, monkeypatch):
    env = tmp_path / "x.env"
    env.write_text("AI_INTERNAL_KEY=tu-tep\nAI_MODEL=mo-hinh-tep\n", encoding="utf-8")
    monkeypatch.setenv("AI_MODEL", "mo-hinh-moi-truong")
    monkeypatch.delenv("AI_INTERNAL_KEY", raising=False)
    s = Settings(_env_file=str(env))  # type: ignore[call-arg]
    assert s.ai_model == "mo-hinh-moi-truong" and s.internal_key_value() == "tu-tep"


def test_env_file_order_local_overrides_appdata(tmp_path, monkeypatch):
    appdata = tmp_path / "AppData"
    (appdata / "DSVHVN").mkdir(parents=True)
    (appdata / "DSVHVN" / "ai-service.env").write_text("AI_MODEL=tu-appdata\nAI_INTERNAL_KEY=k-appdata\n", encoding="utf-8")
    local = tmp_path / ".env"
    local.write_text("AI_MODEL=tu-cuc-bo\n", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.delenv("AI_INTERNAL_KEY", raising=False)
    files = env_files()
    assert files[0].endswith("ai-service.env") and files[-1].endswith(".env")
    s = Settings(_env_file=(files[0], str(local)))  # type: ignore[call-arg]
    assert s.ai_model == "tu-cuc-bo" and s.internal_key_value() == "k-appdata"


async def test_logs_never_contain_keys_or_content(make_client, caplog):
    secret_content = "NOI-DUNG-RIENG-TU-CUA-DI-SAN"
    req = compose_request(2)
    req["heritages"][0]["content"] = secret_content
    llm = FakeLlm(ok(lesson_output(2, compose_request(2)), 10, 5))
    client = make_client(llm)
    with caplog.at_level(logging.DEBUG):
        await client.post("/v1/compose-lesson", json=req)
    text = "\n".join(JsonFormatter().format(r) for r in caplog.records)
    assert text
    for forbidden in (INTERNAL_KEY, "khong-dung", secret_content):
        assert forbidden not in text


def test_json_log_line_has_correlation_id():
    token = correlation_id_var.set("cid-9")
    try:
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "xin chào", None, None)
        record.api = "compose-lesson"
        record.inputTokens = 7
        data = json.loads(JsonFormatter().format(record))
    finally:
        correlation_id_var.reset(token)
    assert data["correlationId"] == "cid-9" and data["api"] == "compose-lesson" and data["inputTokens"] == 7 and data["msg"] == "xin chào"
