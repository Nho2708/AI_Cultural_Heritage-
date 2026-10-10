"""Chạy dịch vụ AI với MÔ HÌNH GIẢ (không gọi Claude) để kiểm đường đi backend -> dịch vụ AI -> backend.

    .venv\\Scripts\\python scripts\\chay-mo-hinh-gia.py --port 8000

Khóa nội bộ lấy từ .env hoặc %APPDATA%\\DSVHVN\\ai-service.env như bản thật. Đầu ra là dữ liệu hợp lệ dựng từ chính yêu cầu, không phải chất lượng mô hình.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import uvicorn  # noqa: E402

from app.config import load_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from mo_hinh_gia import MoHinhGia  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    app = create_app(load_settings(), MoHinhGia())
    uvicorn.run(app, host=args.host, port=args.port, log_config=None)


if __name__ == "__main__":
    main()
