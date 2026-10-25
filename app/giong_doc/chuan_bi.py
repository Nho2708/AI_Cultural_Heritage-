"""Chữ -> các câu kèm mẩu đưa vào máy đọc. Chỉ thư viện chuẩn."""
from __future__ import annotations

from .chia_cau import chia_mau, tach_cau
from .chuan_hoa_vi import chuan_hoa_doan


def chuan_bi_cau(van_ban: str, ngon_ngu: str) -> list[dict]:
    """Câu hiển thị là câu gốc; mẩu đưa vào máy đọc được chuẩn hóa (tiếng Việt) và cắt <= 250 ký tự."""
    cau = []
    for c in tach_cau(van_ban):
        doc = chuan_hoa_doan(c) if ngon_ngu == "vi" else c
        cau.append({"text": c, "chunks": chia_mau(doc) or [c]})
    return cau
