"""Điểm chạy dịch vụ: python -m app.serve

Dưới IIS trên máy demo (ASP.NET Core Module, chế độ out-of-process): module của IIS tự chọn một cổng trống, truyền qua biến
ASPNETCORE_PORT rồi chuyển yêu cầu từ site (127.0.0.1:8090) vào cổng đó. Trong container trên máy chủ Google Cloud: ảnh đặt
AI_HOST=0.0.0.0 và AI_PORT=8000 để API ở container khác gọi được. Chạy tay không có biến nào thì dùng cổng 8000 như run.ps1.
Mặc định chỉ nghe trên 127.0.0.1: dịch vụ không mở ra mạng ngoài.
"""
from __future__ import annotations

import os

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def port_from_env(environ: dict[str, str] | None = None) -> int:
    env = environ if environ is not None else os.environ
    raw = env.get("ASPNETCORE_PORT", "").strip() or env.get("AI_PORT", "").strip()
    if not raw:
        return DEFAULT_PORT
    port = int(raw)
    if not 0 < port < 65536:
        raise ValueError(f"Cổng không hợp lệ: {raw}")
    return port


def host_from_env(environ: dict[str, str] | None = None) -> str:
    return (environ if environ is not None else os.environ).get("AI_HOST", "").strip() or DEFAULT_HOST


def main() -> None:
    import uvicorn

    # Lỗi ghi ra stdout/stderr (IIS chép vào nhật ký stdoutLogFile, Docker giữ ở docker logs); log_config=None để giữ định dạng
    # JSON của dịch vụ.
    uvicorn.run("app.asgi:app", host=host_from_env(), port=port_from_env(), log_config=None, access_log=False)


if __name__ == "__main__":
    main()
