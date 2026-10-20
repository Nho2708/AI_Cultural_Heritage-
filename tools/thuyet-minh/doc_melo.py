"""Máy đọc Anh / Hàn / Trung / Nhật: MeloTTS (PyTorch, CPU), chạy trong venv melo.

Dùng:  python -X utf8 doc_melo.py <tệp việc.json>      (xem chay_viec.py về dạng tệp việc)
Mỗi ngôn ngữ là một mô hình riêng, nạp lần đầu gặp rồi giữ lại cho các mục sau trong cùng tệp việc.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chay_viec import chay

# giọng -> (mã ngôn ngữ MeloTTS, khóa giọng trong spk2id)
GIONG = {
    "melo-en-us": ("EN", "EN-US"),
    "melo-kr": ("KR", "KR"),
    "melo-zh": ("ZH", "ZH"),
    "melo-jp": ("JP", "JP"),
}


def main() -> int:
    if len(sys.argv) != 2:
        print("Dùng: doc_melo.py <tệp việc.json>")
        return 2
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
        return (lambda mau: np.asarray(mo_hinh.tts_to_file(mau, spk, None, speed=1.0, quiet=True), dtype=np.float32)), sr

    return chay(sys.argv[1], lay_may_doc)


if __name__ == "__main__":
    sys.exit(main())
