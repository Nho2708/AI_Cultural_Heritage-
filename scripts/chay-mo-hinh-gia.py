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

import uvicorn
from mo_hinh_gia import MoHinhGia

from app.config import load_settings
from app.errors import ModelUnavailable, ServiceError
from app.llm.client import LlmResult, TokenUsage
from app.main import create_app


class MoHinhLoi(MoHinhGia):
    """Mô hình giả cố tình lỗi để xem backend xử lý các mã phản hồi của dịch vụ AI ra sao."""

    def __init__(self, kieu: str) -> None:
        super().__init__()
        self.kieu = kieu

    async def complete_json(self, **kwargs) -> LlmResult:
        self.calls += 1
        if self.kieu == "dau-ra-sai":
            return LlmResult({"khong-dung-luoc-do": True}, TokenUsage(100, 50), self.model)
        if self.kieu == "tu-choi":
            raise ServiceError(422, "model_refused", "Mô hình từ chối xử lý nội dung này.")
        raise ModelUnavailable(503, "llm_rate_limited", "Nhà cung cấp mô hình đang giới hạn tần suất.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--loi", choices=["dau-ra-sai", "tu-choi", "qua-tai"], help="Cố tình lỗi để xem cách backend xử lý.")
    args = parser.parse_args()
    app = create_app(load_settings(), MoHinhLoi(args.loi) if args.loi else MoHinhGia())
    uvicorn.run(app, host=args.host, port=args.port, log_config=None)


if __name__ == "__main__":
    main()
