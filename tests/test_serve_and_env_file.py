"""Chạy dưới IIS trên máy demo (cổng do module của IIS cấp, tệp cấu hình chỉ định bằng AI_ENV_FILE) và trong container
(địa chỉ nghe và cổng đặt bằng AI_HOST, AI_PORT)."""
import pytest

from app.config import Settings, env_files
from app.serve import DEFAULT_HOST, DEFAULT_PORT, host_from_env, port_from_env


def test_port_comes_from_iis_module():
    assert port_from_env({"ASPNETCORE_PORT": "17321"}) == 17321


def test_port_defaults_when_run_by_hand():
    assert port_from_env({}) == DEFAULT_PORT
    assert port_from_env({"ASPNETCORE_PORT": "  "}) == DEFAULT_PORT


def test_port_comes_from_container_variable():
    assert port_from_env({"AI_PORT": "8000"}) == 8000
    # Dưới IIS cổng của module luôn thắng.
    assert port_from_env({"ASPNETCORE_PORT": "17321", "AI_PORT": "8000"}) == 17321


@pytest.mark.parametrize("raw", ["0", "70000", "abc"])
def test_port_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        port_from_env({"ASPNETCORE_PORT": raw})
    with pytest.raises(ValueError):
        port_from_env({"AI_PORT": raw})


def test_host_listens_on_loopback_unless_container_asks():
    assert host_from_env({}) == DEFAULT_HOST == "127.0.0.1"
    assert host_from_env({"AI_HOST": " "}) == DEFAULT_HOST
    assert host_from_env({"AI_HOST": "0.0.0.0"}) == "0.0.0.0"


def test_explicit_env_file_has_highest_file_priority(tmp_path, monkeypatch):
    appdata = tmp_path / "AppData"
    (appdata / "DSVHVN").mkdir(parents=True)
    (appdata / "DSVHVN" / "ai-service.env").write_text("AI_MODEL=tu-appdata\nAI_INTERNAL_KEY=k-appdata\n", encoding="utf-8")
    demo = tmp_path / "cau-hinh" / "ai.env"
    demo.parent.mkdir()
    demo.write_text("AI_MODEL=tu-may-demo\nAI_PROVIDER=gemini\n", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("AI_ENV_FILE", str(demo))
    for name in ("AI_MODEL", "AI_INTERNAL_KEY", "AI_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    files = env_files()
    assert files[-1] == str(demo)
    s = Settings(_env_file=(files[0], files[-1]))  # type: ignore[call-arg]
    assert s.ai_model == "tu-may-demo" and s.ai_provider == "gemini" and s.internal_key_value() == "k-appdata"


def test_blank_env_file_variable_is_ignored(monkeypatch):
    monkeypatch.setenv("AI_ENV_FILE", "   ")
    assert all(f.strip() for f in env_files())
    assert not any(f == "" for f in env_files())
