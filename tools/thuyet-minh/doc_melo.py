"""Máy đọc Anh / Hàn / Trung / Nhật: MeloTTS (PyTorch, CPU), chạy trong venv melo.

Dùng:  python -X utf8 doc_melo.py <tệp việc.json>      (xem chay_viec.py về dạng tệp việc)
Mỗi ngôn ngữ là một mô hình riêng, nạp lần đầu gặp rồi giữ lại cho các mục sau trong cùng tệp việc.
"""
from __future__ import annotations

import os
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chay_viec import chay

# giọng -> (mã ngôn ngữ MeloTTS, khóa giọng trong spk2id)
GIONG = {
    "melo-en-us": ("EN", "EN-US"),
    "melo-kr": ("KR", "KR"),
    "melo-zh": ("ZH", "ZH"),
    "melo-jp": ("JP", "JP"),
}

# Chữ Latin trong ngoặc ở bản Hàn, Trung, Nhật là tên gốc tiếng Việt viết kèm để người đọc đối chiếu: không đọc thành tiếng.
_NGOAC_LATIN = re.compile(r"\s*[(（][^()（）]*[A-Za-zÀ-ỹĐđ][^()（）]*[)）]")


def lam_sach(mau: str, voice: str) -> str:
    """Chữ đưa vào MeloTTS: bỏ tên gốc trong ngoặc (trừ tiếng Anh) và bỏ dấu tiếng Việt của tên riêng, để bộ chuyển chữ thành âm
    của từng ngôn ngữ đọc được (chữ hiển thị và mốc câu không đổi vì vẫn tạo theo từng câu)."""
    sach = mau if voice == "melo-en-us" else _NGOAC_LATIN.sub("", mau)
    sach = _CHU_LATIN.sub(_bo_dau, sach)  # chỉ đụng chữ Latin: dấu của kana (が) cũng là dấu kết hợp, không được bỏ
    if voice == "melo-jp":
        sach = "".join(_AM_CHU_HAN_HIEM.get(c, c) for c in sach)
    sach = re.sub(r"\s+", " ", sach).strip()
    return sach or mau


# Chữ Hán trong tên riêng mà bộ đọc tiếng Nhật của MeloTTS không có cách đọc (gặp là dừng): thay bằng âm On.
_AM_CHU_HAN_HIEM = {"雒": "ラク", "漳": "ショウ"}


def doc_an_toan(doc, mau: str):
    """Bộ đọc tiếng Nhật báo AssertionError((chữ không đọc được, ...)) khi gặp chữ Hán lạ ngoài bảng trên:
    bỏ các chữ đó rồi đọc lại một lần, để cả bài không hỏng vì một chữ."""
    try:
        return doc(mau)
    except AssertionError as e:
        chi_tiet = e.args[0] if e.args else None
        chu_la = chi_tiet[0] if isinstance(chi_tiet, tuple) and chi_tiet and isinstance(chi_tiet[0], list) else None
        if not chu_la:
            raise
        bot = "".join(c for c in mau if c not in set(chu_la))
        if not bot.strip() or bot == mau:
            raise
        return doc(bot)


_CHU_LATIN = re.compile(r"[A-Za-zÀ-ỹĐđ]+")


def _bo_dau(m: re.Match) -> str:
    tu = m.group(0).replace("Đ", "D").replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", tu) if unicodedata.category(c) != "Mn")


def main() -> int:
    if len(sys.argv) != 2:
        print("Dùng: doc_melo.py <tệp việc.json>")
        return 2
    import numpy as np
    import torch
    torch.set_num_threads(max(1, os.cpu_count() or 1))
    from melo.api import TTS

    da_nap: dict[str, tuple] = {}

    def lay_may_doc(voice: str):
        ma_ngon_ngu, khoa_giong = GIONG[voice]
        if ma_ngon_ngu not in da_nap:
            t0 = time.perf_counter()
            mo_hinh = TTS(language=ma_ngon_ngu, device="cpu")
            spk = mo_hinh.hps.data.spk2id[khoa_giong]
            sr = mo_hinh.hps.data.sampling_rate
            print(f"MeloTTS {ma_ngon_ngu}: nạp mô hình {time.perf_counter() - t0:.1f} s, {sr} Hz", flush=True)
            da_nap[ma_ngon_ngu] = (mo_hinh, spk, sr)
        mo_hinh, spk, sr = da_nap[ma_ngon_ngu]
        def doc(chu: str):
            return mo_hinh.tts_to_file(chu, spk, None, speed=1.0, quiet=True)
        return (lambda mau: np.asarray(doc_an_toan(doc, lam_sach(mau, voice)), dtype=np.float32)), sr

    return chay(sys.argv[1], lay_may_doc)


if __name__ == "__main__":
    sys.exit(main())
