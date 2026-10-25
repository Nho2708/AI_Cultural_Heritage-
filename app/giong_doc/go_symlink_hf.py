"""Thay các symlink trong thư mục snapshots của Hugging Face cache bằng bản sao thật.

Dịch vụ AI tự gọi hàm này khi nạp mô hình gặp lỗi đó. Lý do: ONNX Runtime 1.31 từ chối tệp dữ liệu ngoài (.data) khi đường dẫn thật của symlink nằm ngoài thư mục mô hình.
Dùng: python -m app.giong_doc.go_symlink_hf [<HF_HOME>]   (mặc định lấy biến môi trường HF_HOME; chạy từ thư mục gốc repo)
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def go_symlink(goc: Path) -> int:
    so = 0
    for d in goc.rglob("snapshots"):
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if p.is_symlink() and p.is_file():
                that = p.resolve()
                tam = p.with_name(p.name + ".tmp-copy")
                shutil.copyfile(that, tam)
                p.unlink()
                os.replace(tam, p)
                so += 1
    return so


if __name__ == "__main__":
    hf = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("HF_HOME", ""))
    print("Đã thay", go_symlink(hf), "symlink bằng tệp thật trong", hf)
