"""Tách câu hiển thị và chia mẩu cho máy đọc.

- Câu hiển thị: câu gốc của bản tóm tắt, dùng để tô sáng khi phát. Tách ở . ! ? … (vi, en, ko) và 。！？ (zh, ja),
  giữ dấu ngoặc kép đóng đi theo câu, không tách sau chữ viết tắt quen (TP., TS., PGS., v.v.) hay chữ cái đơn
  viết hoa ("H. Parmentier").
- Mẩu đọc: một câu quá dài được cắt thành nhiều mẩu <= toi_da ký tự ở dấu phẩy, chấm phẩy rồi khoảng trắng
  (không bao giờ cắt giữa từ). Mốc thời gian vẫn tính theo câu hiển thị, không theo mẩu.

Chỉ dùng thư viện chuẩn. Dùng chung cho dịch vụ AI (POST /v1/tts) và công cụ tạo thuyết minh tạo sẵn.
"""
from __future__ import annotations

import re

SO_CAU_TOI_DA = 300           # API nhận tối đa 300 câu một thuyết minh
MAU_TOI_DA = 250              # ký tự mỗi mẩu đưa vào máy đọc

# Chữ viết tắt kết thúc bằng dấu chấm mà không phải hết câu (so khớp phần đứng trước dấu chấm).
VIET_TAT_KHONG_CAT = {
    "TP", "Tp", "TS", "ThS", "PGS", "GS", "KTS", "TX", "TT", "v.v", "V.v",
    "Mr", "Mrs", "Ms", "Dr", "St", "Prof", "No", "vs", "Jr", "Sr",
}

# Kết câu kiểu La-tinh: dấu chấm/than/hỏi/ba chấm (+ ngoặc đóng) rồi khoảng trắng hoặc hết chuỗi.
_KET_LATIN = re.compile(r"[.!?…]+[”\"'’)\]]*(?=\s|$)")
# Kết câu kiểu Trung/Nhật: không cần khoảng trắng phía sau.
_KET_CJK = re.compile(r"[。！？]+[」』）”\"]*")
_KET_CAU = re.compile(f"{_KET_LATIN.pattern}|{_KET_CJK.pattern}")
_TU_CUOI = re.compile(r"[\"'“‘(\[]*([^\s\"'“‘(\[]+)$")
_CO_CHU = re.compile(r"\w", re.UNICODE)
# Các ranh giới cắt mẩu giữ nguyên khoảng trắng gốc (đi theo phần sau) để ghép lại không thêm bớt ký tự.
_RANH_DAU_KHAC = re.compile(r"(?<=[.!?。！？…])")
_RANH_MENH_DE = re.compile(r"(?<=[,;:，、；：])")
_RANH_KHOANG_TRANG = re.compile(r"(?<= )")


def _la_viet_tat(truoc: str) -> bool:
    """Phần văn bản đứng trước dấu chấm có kết thúc bằng chữ viết tắt hay chữ cái đơn viết hoa không."""
    m = _TU_CUOI.search(truoc)
    if not m:
        return False
    tu = m.group(1)
    return tu in VIET_TAT_KHONG_CAT or re.fullmatch(r"[A-Z]", tu) is not None


def tach_cau(van_ban: str) -> list[str]:
    """Văn bản -> danh sách câu hiển thị (khoảng trắng gộp lại, xuống dòng cũng là hết câu)."""
    cau: list[str] = []
    for doan in re.split(r"[\r\n]+", van_ban):
        doan = doan.strip()
        if not doan:
            continue
        bat_dau = 0
        for m in _KET_CAU.finditer(doan):
            # Chỉ dấu chấm mới có thể là viết tắt; "!" "?" "…" luôn hết câu.
            if m.group(0).startswith(".") and _la_viet_tat(doan[bat_dau:m.start()]):
                continue
            cau.append(doan[bat_dau:m.end()])
            bat_dau = m.end()
        if bat_dau < len(doan):
            cau.append(doan[bat_dau:])
    return _gon_cau([re.sub(r"\s+", " ", c).strip() for c in cau])


def _gon_cau(cau: list[str]) -> list[str]:
    """Bỏ câu rỗng, ghép mẩu không có chữ (chỉ dấu) vào câu trước, giới hạn số câu."""
    ket: list[str] = []
    for c in cau:
        if not c:
            continue
        if not _CO_CHU.search(c) and ket:
            ket[-1] = ket[-1] + " " + c
        elif _CO_CHU.search(c):
            ket.append(c)
    if len(ket) > SO_CAU_TOI_DA:
        ket[SO_CAU_TOI_DA - 1:] = [" ".join(ket[SO_CAU_TOI_DA - 1:])]
    return ket


def _gop(phan: list[str], toi_da: int) -> list[str]:
    """Nối các phần liên tiếp (giữ nguyên khoảng trắng gốc) cho tới gần toi_da; mỗi mẩu trả về đã bỏ khoảng trắng hai đầu."""
    ket, hien = [], ""
    for p in phan:
        if not p.strip():
            continue
        ung = hien + p
        if len(ung.strip()) <= toi_da or not hien.strip():
            hien = ung
        else:
            ket.append(hien.strip())
            hien = p
    if hien.strip():
        ket.append(hien.strip())
    return ket


def _cat_cung(manh: str, toi_da: int) -> list[str]:
    """Phương án cuối cho chuỗi không có khoảng trắng (chữ Hán, kana): cắt đúng toi_da ký tự."""
    return [manh[i:i + toi_da] for i in range(0, len(manh), toi_da)]


def chia_mau(cau: str, toi_da: int = MAU_TOI_DA) -> list[str]:
    """Một câu -> danh sách mẩu <= toi_da ký tự, cắt ở dấu câu rồi mệnh đề rồi khoảng trắng; ghép lại được câu gốc."""
    cau = re.sub(r"\s+", " ", cau).strip()
    if len(cau) <= toi_da:
        return [cau] if cau else []
    mau: list[str] = []
    for phan in _gop(_RANH_DAU_KHAC.split(cau), toi_da):
        if len(phan) <= toi_da:
            mau.append(phan)
            continue
        for manh in _gop(_RANH_MENH_DE.split(phan), toi_da):
            if len(manh) <= toi_da:
                mau.append(manh)
            else:
                for tu in _gop(_RANH_KHOANG_TRANG.split(manh), toi_da):
                    mau.extend([tu] if len(tu) <= toi_da else _cat_cung(tu, toi_da))
    return mau


if __name__ == "__main__":
    import sys
    for i, c in enumerate(tach_cau(" ".join(sys.argv[1:])), 1):
        print(f"[{i}] {c}")
        for m in chia_mau(c):
            if m != c:
                print(f"    - ({len(m)}) {m}")
