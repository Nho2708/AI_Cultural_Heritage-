"""Nạp VieNeu-TTS v3 Turbo (ONNX, CPU) và chọn độ chính xác theo CPU. Gói vieneu chỉ được nhập bên trong hàm nạp."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .go_symlink_hf import go_symlink

# Mã giọng của API -> tên preset trong VieNeu.
GIONG = {"vieneu-mai-anh": "Mai Anh"}
GIONG_MAC_DINH = "vieneu-mai-anh"

# Cờ CPU (trong /proc/cpuinfo) cho biết có tập lệnh VNNI; int8 của VieNeu cần VNNI, không có thì tiếng bị méo.
CO_VNNI = ("avx512_vnni", "avx_vnni")


def cpu_co_vnni(cpuinfo: str | None = None, nen_tang: str | None = None) -> bool:
    """CPU có VNNI không. Chỉ đọc được trên Linux (/proc/cpuinfo); nền tảng khác hoặc không đọc được thì trả False cho an toàn."""
    if cpuinfo is None:
        if (nen_tang or sys.platform) != "linux":
            return False
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
    for dong in cpuinfo.splitlines():
        ten, _, gia_tri = dong.partition(":")
        if ten.strip().lower() == "flags":
            return any(co in gia_tri.split() for co in CO_VNNI)
    return False


def chon_do_chinh_xac(cau_hinh: str, co_vnni: bool) -> str:
    """"int8" hoặc "fp32": cấu hình ép sẵn thì theo cấu hình, "auto" thì int8 khi CPU có VNNI, không thì fp32."""
    cau_hinh = (cau_hinh or "auto").strip().lower()
    if cau_hinh in ("int8", "fp32"):
        return cau_hinh
    return "int8" if co_vnni else "fp32"


def dat_so_luong(so_luong: int) -> None:
    """Giới hạn số luồng của thư viện tính toán trước khi nạp mô hình (biến người vận hành đã đặt sẵn thì giữ)."""
    if so_luong > 0:
        for ten in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
            os.environ.setdefault(ten, str(so_luong))


def tai_vieneu(do_chinh_xac: str = "fp32", so_luong: int = 0):
    """Nạp mô hình; so_luong = 0 để VieNeu tự chọn."""
    from vieneu import Vieneu

    def tao():
        return Vieneu(mode="v3turbo", backend="onnx", precision=do_chinh_xac, threads=so_luong)

    try:
        return tao()
    except Exception as e:
        # ONNX Runtime từ chối tệp dữ liệu ngoài khi snapshot của Hugging Face cache là symlink: thay bằng tệp thật rồi nạp lại.
        if "External data path" not in str(e) or not os.environ.get("HF_HOME"):
            raise
        go_symlink(Path(os.environ["HF_HOME"]))
        return tao()
