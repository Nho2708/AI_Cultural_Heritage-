"""Lỗi của dịch vụ và cách ánh xạ sang mã HTTP mà backend chờ.

Backend coi 5xx, 408, 429 và lỗi mạng là lỗi thử lại được; 400, 401, 403, 422 là lỗi không thử lại.
Đầu ra mô hình sai lược đồ, mô hình quá tải hay cắt cụt => 502, 503, 504 (thử lại được).
Đầu vào sai, mô hình từ chối nội dung => 422 (không thử lại).
"""
from __future__ import annotations


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, *, details: list[dict] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or []

    @property
    def retryable(self) -> bool:
        return self.status >= 500 or self.status in (408, 429)


class InvalidInput(ServiceError):
    def __init__(self, code: str, message: str, details: list[dict] | None = None):
        super().__init__(422, code, message, details=details)


class ModelUnavailable(ServiceError):
    """Mô hình lỗi tạm thời: 503 (quá tải, giới hạn tần suất, chưa cấu hình), 502 (lỗi máy chủ, đầu ra hỏng), 504 (quá giờ)."""
