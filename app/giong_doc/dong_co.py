"""Động cơ giọng đọc của dịch vụ: nạp mô hình ở luồng nền, mỗi lúc chỉ sinh một yêu cầu.

Trạng thái: "off" (tắt bằng cấu hình), "loading" (đang nạp), "ready" (sẵn sàng), "error" (nạp hỏng).
Gói vieneu chỉ được nhập khi nạp mô hình, nên dịch vụ chạy bình thường ở máy không cài gói giọng đọc (CI, máy demo IIS).
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .am_thanh import chuan_hoa_am_luong, ghep_theo_cau, ma_hoa_mp3
from .chuan_bi import chuan_bi_cau
from .mo_hinh import GIONG, GIONG_MAC_DINH, chon_do_chinh_xac, cpu_co_vnni, dat_so_luong, tai_vieneu

log = logging.getLogger("ai.tts")

TAT, DANG_NAP, SAN_SANG, LOI = "off", "loading", "ready", "error"
MAU_TOI_DA_KY_TU = 400          # max_chars truyền cho VieNeu (mẩu của dịch vụ đã <= 250)
CHO_LUOT_GIAY = 30.0            # chờ lượt sinh tối đa ngần này giây khi đang có yêu cầu khác
NAP_LAI_SAU_GIAY = 60.0         # nạp hỏng: yêu cầu kế tiếp sau ngần này giây mới thử nạp lại


class GiongDocKhongSan(Exception):
    """Máy đọc chưa dùng được lúc này; goi_lai_sau là số giây gợi ý cho Retry-After."""

    def __init__(self, ma: str, thong_bao: str, goi_lai_sau: int):
        super().__init__(thong_bao)
        self.ma = ma
        self.thong_bao = thong_bao
        self.goi_lai_sau = goi_lai_sau


class KhongCoChuDoc(Exception):
    """Sau khi chuẩn hóa không còn gì để đọc (chữ chỉ có dấu câu hay ký tự không phát âm)."""


@dataclass(frozen=True)
class KetQuaDoc:
    mp3: bytes
    thoi_luong_ms: int
    giong: str


Loader = Callable[[str, int], object]


class GiongDoc:
    def __init__(self, bat: bool, so_luong: int = 2, do_chinh_xac: str = "auto", loader: Loader | None = None):
        self.bat = bat
        self.so_luong = so_luong
        self.do_chinh_xac = do_chinh_xac
        self._loader = loader or tai_vieneu
        self._trang_thai = TAT
        self._mo_hinh = None
        self._khoa_trang_thai = threading.Lock()
        self._khoa_sinh = threading.Lock()
        self._nap_luc = 0.0
        self.do_chinh_xac_dang_dung: str | None = None

    @property
    def trang_thai(self) -> str:
        return self._trang_thai

    def khoi_dong(self) -> None:
        """Bật nạp mô hình ở luồng nền (không làm gì nếu tắt hoặc đã nạp/đang nạp)."""
        if not self.bat:
            return
        with self._khoa_trang_thai:
            if self._trang_thai in (DANG_NAP, SAN_SANG):
                return
            self._trang_thai = DANG_NAP
        threading.Thread(target=self.nap, name="giong-doc-nap", daemon=True).start()

    def nap(self) -> None:
        """Nạp mô hình (chạy trong luồng nền; test gọi trực tiếp). Lỗi chỉ ghi kiểu lỗi, không làm dịch vụ dừng."""
        with self._khoa_trang_thai:
            self._trang_thai = DANG_NAP
        self._nap_luc = time.monotonic()
        try:
            dat_so_luong(self.so_luong)
            do_chinh_xac = chon_do_chinh_xac(self.do_chinh_xac, cpu_co_vnni())
            t0 = time.perf_counter()
            mo_hinh = self._loader(do_chinh_xac, self.so_luong)
            self._mo_hinh = mo_hinh
            self.do_chinh_xac_dang_dung = do_chinh_xac
            self._trang_thai = SAN_SANG
            log.info("Đã nạp giọng đọc", extra={"ms": int((time.perf_counter() - t0) * 1000), "precision": do_chinh_xac})
        except Exception as exc:  # noqa: BLE001 - nạp hỏng (thiếu gói, không tải được mô hình...) chỉ làm /v1/tts trả 503
            self._trang_thai = LOI
            log.error("Không nạp được giọng đọc", extra={"errorCode": type(exc).__name__, "reason": str(exc)[:200]})

    def _kiem_san_sang(self) -> None:
        trang_thai = self._trang_thai
        if trang_thai == SAN_SANG:
            return
        if trang_thai == TAT:
            raise GiongDocKhongSan("tts_disabled", "Giọng đọc trên máy chủ đang tắt.", 300)
        if trang_thai == DANG_NAP:
            raise GiongDocKhongSan("tts_loading", "Giọng đọc đang được nạp, thử lại sau ít giây.", 15)
        if time.monotonic() - self._nap_luc >= NAP_LAI_SAU_GIAY:
            self.khoi_dong()
            raise GiongDocKhongSan("tts_loading", "Giọng đọc đang được nạp lại, thử lại sau ít giây.", 15)
        raise GiongDocKhongSan("tts_failed", "Không nạp được giọng đọc trên máy chủ.", 60)

    def tong_hop(self, van_ban: str, giong: str = GIONG_MAC_DINH) -> KetQuaDoc:
        """Chữ -> MP3 mono. Chặn luồng gọi (chạy trong luồng riêng của FastAPI, không chạy trên vòng lặp sự kiện)."""
        self._kiem_san_sang()
        if giong not in GIONG:
            raise ValueError(f"Giọng không được hỗ trợ: {giong}")
        cau = chuan_bi_cau(van_ban, "vi")
        if not cau:
            raise KhongCoChuDoc
        mo_hinh = self._mo_hinh
        sr = int(mo_hinh.sample_rate)
        preset = GIONG[giong]

        def sinh(mau: str) -> np.ndarray:
            return np.asarray(mo_hinh.infer(mau, voice=preset, max_chars=MAU_TOI_DA_KY_TU), dtype=np.float32)

        if not self._khoa_sinh.acquire(timeout=CHO_LUOT_GIAY):
            raise GiongDocKhongSan("tts_busy", "Giọng đọc đang bận, thử lại sau ít giây.", 5)
        try:
            t0 = time.perf_counter()
            song, _ = ghep_theo_cau(cau, sinh, sr)
            song = chuan_hoa_am_luong(song)
            mp3 = ma_hoa_mp3(song, sr)
            thoi_luong_ms = round(song.size * 1000 / sr)
            log.info("Đã tạo giọng đọc", extra={"ms": int((time.perf_counter() - t0) * 1000), "chars": len(van_ban), "durationMs": thoi_luong_ms})
        finally:
            self._khoa_sinh.release()
        return KetQuaDoc(mp3=mp3, thoi_luong_ms=thoi_luong_ms, giong=giong)
