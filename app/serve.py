"""Chạy dịch vụ dưới IIS (ASP.NET Core Module, chế độ out-of-process) trên máy demo: python -m app.serve

Module của IIS tự chọn một cổng trống, truyền qua biến ASPNETCORE_PORT rồi chuyển yêu cầu từ site (127.0.0.1:8090) vào cổng đó.
Chạy tay không có biến này thì dùng cổng 8000 như run.ps1. Chỉ nghe trên 127.0.0.1: dịch vụ không mở ra mạng ngoài.
"""
from __future__ import annotations

import os

DEFAULT_PORT = 8000


def port_from_env(environ: dict[str, str] | None = None) -> int:
    raw = (environ if environ is not None else os.environ).get("ASPNETCORE_PORT", "").strip()
    if not raw:
        return DEFAULT_PORT
    port = int(raw)
    if not 0 < port < 65536:
        raise ValueError(f"ASPNETCORE_PORT không hợp lệ: {raw}")
    return port


def main() -> None:
    import uvicorn

    # Lỗi ghi ra stdout/stderr được module của IIS chép vào nhật ký (stdoutLogFile); log_config=None để giữ định dạng JSON của dịch vụ.
    uvicorn.run("app.asgi:app", host="127.0.0.1", port=port_from_env(), log_config=None, access_log=False)


if __name__ == "__main__":
    main()
