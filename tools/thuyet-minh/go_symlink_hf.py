"""Thay các symlink trong thư mục snapshots của Hugging Face cache bằng bản sao thật (mã nằm ở app/giong_doc/go_symlink_hf.py).

Dùng: python go_symlink_hf.py [<HF_HOME>]   (mặc định lấy biến môi trường HF_HOME)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.giong_doc.go_symlink_hf import go_symlink

if __name__ == "__main__":
    hf = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("HF_HOME", ""))
    print("Đã thay", go_symlink(hf), "symlink bằng tệp thật trong", hf)
