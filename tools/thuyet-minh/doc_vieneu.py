"""Máy đọc tiếng Việt: VieNeu-TTS v3 Turbo (ONNX, CPU), chạy trong venv vieneu.

Dùng:  python -X utf8 doc_vieneu.py <tệp việc.json>      (xem chay_viec.py về dạng tệp việc)
Giọng: vieneu-mai-anh -> preset "Mai Anh" của VieNeu.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))      # thư mục gốc repo: mã dùng chung nằm ở app/giong_doc
from chay_viec import chay

from app.giong_doc.mo_hinh import GIONG, tai_vieneu


def tai_mo_hinh():
    # Công cụ chạy offline trên máy dev nên giữ fp32 (chất lượng tối đa), số luồng do VieNeu tự chọn.
    return tai_vieneu("fp32", 0)


def main() -> int:
    if len(sys.argv) != 2:
        print("Dùng: doc_vieneu.py <tệp việc.json>")
        return 2
    t0 = time.perf_counter()
    mo_hinh = tai_mo_hinh()
    print(f"VieNeu v3 Turbo (fp32): nạp mô hình {time.perf_counter() - t0:.1f} s, {mo_hinh.sample_rate} Hz", flush=True)

    def lay_may_doc(voice: str):
        preset = GIONG[voice]
        return (lambda mau: np.asarray(mo_hinh.infer(mau, voice=preset, max_chars=400), dtype=np.float32)), mo_hinh.sample_rate

    return chay(sys.argv[1], lay_may_doc)


if __name__ == "__main__":
    sys.exit(main())
