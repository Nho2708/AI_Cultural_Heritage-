"""Máy đọc tiếng Việt: VieNeu-TTS v3 Turbo (ONNX, CPU), chạy trong venv vieneu.

Dùng:  python -X utf8 doc_vieneu.py <tệp việc.json>      (xem chay_viec.py về dạng tệp việc)
Giọng: vieneu-mai-anh -> preset "Mai Anh" của VieNeu.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chay_viec import chay
from go_symlink_hf import go_symlink

GIONG = {"vieneu-mai-anh": "Mai Anh"}


def tai_mo_hinh():
    from vieneu import Vieneu
    try:
        return Vieneu(mode="v3turbo", backend="onnx", precision="fp32")
    except Exception as e:
        # ONNX Runtime từ chối tệp dữ liệu ngoài khi snapshot của Hugging Face cache là symlink: thay bằng tệp thật rồi nạp lại.
        if "External data path" not in str(e) or not os.environ.get("HF_HOME"):
            raise
        go_symlink(Path(os.environ["HF_HOME"]))
        return Vieneu(mode="v3turbo", backend="onnx", precision="fp32")


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
