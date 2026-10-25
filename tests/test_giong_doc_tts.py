"""POST /v1/tts và trạng thái giọng đọc trong /health. Không nhập vieneu: dùng mô hình giả phát sóng hình sin."""
from __future__ import annotations

import threading
import time

import httpx
import numpy as np
import pytest

from app.config import Settings
from app.giong_doc import dong_co
from app.giong_doc.dong_co import GiongDoc
from app.main import create_app

from .conftest import HEADERS, INTERNAL_KEY, FakeLlm, ok

SR = 24000


class MoHinhGia:
    """Giống giao diện của Vieneu: sample_rate và infer(text, voice, max_chars) -> sóng float32 (0,5 giây hình sin mỗi mẩu)."""

    sample_rate = SR

    def __init__(self):
        self.cac_lan_goi: list[tuple[str, str, int]] = []
        self.tre_giay = 0.0

    def infer(self, text: str, voice: str, max_chars: int) -> np.ndarray:
        self.cac_lan_goi.append((text, voice, max_chars))
        if self.tre_giay:
            time.sleep(self.tre_giay)
        t = np.arange(int(SR * 0.5)) / SR
        return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def dong_co_san_sang(mo_hinh: MoHinhGia | None = None) -> tuple[GiongDoc, MoHinhGia]:
    mo_hinh = mo_hinh or MoHinhGia()
    dc = GiongDoc(True, loader=lambda do_chinh_xac, so_luong: mo_hinh)
    dc.nap()
    return dc, mo_hinh


def tao_client(giong_doc: GiongDoc) -> httpx.AsyncClient:
    cfg = Settings(ai_internal_key=INTERNAL_KEY, anthropic_api_key="khong-dung")
    app = create_app(cfg, FakeLlm(ok({})), configure_logging=False, giong_doc=giong_doc)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=HEADERS)


def la_mp3(du_lieu: bytes) -> bool:
    return du_lieu[:3] == b"ID3" or (len(du_lieu) > 2 and du_lieu[0] == 0xFF and du_lieu[1] & 0xE0 == 0xE0)


def cho_den(dieu_kien, giay: float = 3.0) -> bool:
    han = time.monotonic() + giay
    while time.monotonic() < han:
        if dieu_kien():
            return True
        time.sleep(0.02)
    return dieu_kien()


# ---------------------------------------------------------------- bảo vệ bằng khóa nội bộ
@pytest.mark.parametrize("khoa", [None, "", "sai-khoa", INTERNAL_KEY + "x"])
async def test_thieu_hoac_sai_khoa_noi_bo_la_401_va_khong_sinh_gi(khoa):
    dc, mo_hinh = dong_co_san_sang()
    client = tao_client(dc)
    client.headers.pop("X-Internal-Key")
    headers = {} if khoa is None else {"X-Internal-Key": khoa}
    r = await client.post("/v1/tts", json={"text": "Xin chào."}, headers=headers)
    assert r.status_code == 401 and r.json()["errorCode"] == "invalid_internal_key"
    assert mo_hinh.cac_lan_goi == []


# ---------------------------------------------------------------- kiểm tra đầu vào: 422
@pytest.mark.parametrize("than", [
    {"text": ""},
    {"text": "   \n "},
    {"text": "a" * 1001},
    {"text": "Xin chào.", "voice": "giong-la"},
    {"voice": "vieneu-mai-anh"},
    {"text": 123},
])
async def test_dau_vao_sai_la_422_va_khong_sinh_gi(than):
    dc, mo_hinh = dong_co_san_sang()
    r = await tao_client(dc).post("/v1/tts", json=than)
    assert r.status_code == 422 and r.json()["errorCode"] == "invalid_request"
    assert mo_hinh.cac_lan_goi == []


async def test_dau_vao_422_ke_ca_khi_giong_doc_dang_tat():
    r = await tao_client(GiongDoc(False)).post("/v1/tts", json={"text": ""})
    assert r.status_code == 422


async def test_dung_1000_ky_tu_la_hop_le():
    dc, _ = dong_co_san_sang()
    r = await tao_client(dc).post("/v1/tts", json={"text": ("Hà Nội. " * 125)[:1000]})
    assert r.status_code == 200


async def test_chi_co_dau_cau_la_422_khong_co_chu_de_doc():
    dc, mo_hinh = dong_co_san_sang()
    r = await tao_client(dc).post("/v1/tts", json={"text": "... !!! ???"})
    assert r.status_code == 422 and r.json()["errorCode"] == "no_speakable_text"
    assert mo_hinh.cac_lan_goi == []


# ---------------------------------------------------------------- 503 kèm Retry-After
async def test_tat_la_503_co_retry_after():
    r = await tao_client(GiongDoc(False)).post("/v1/tts", json={"text": "Xin chào."})
    assert r.status_code == 503 and r.json()["errorCode"] == "tts_disabled"
    assert int(r.headers["Retry-After"]) > 0
    assert r.json()["correlationId"] == "test-corr-1"


async def test_dang_nap_la_503_co_retry_after():
    dc = GiongDoc(True, loader=lambda *_: MoHinhGia())
    dc._trang_thai = dong_co.DANG_NAP
    r = await tao_client(dc).post("/v1/tts", json={"text": "Xin chào."})
    assert r.status_code == 503 and r.json()["errorCode"] == "tts_loading"
    assert int(r.headers["Retry-After"]) > 0


async def test_nap_hong_la_503_co_retry_after_va_dich_vu_van_song():
    def hong(*_):
        raise RuntimeError("không có mạng")

    dc = GiongDoc(True, loader=hong)
    dc.nap()
    assert dc.trang_thai == "error"
    client = tao_client(dc)
    r = await client.post("/v1/tts", json={"text": "Xin chào."})
    assert r.status_code == 503 and r.json()["errorCode"] == "tts_failed"
    assert int(r.headers["Retry-After"]) > 0
    assert (await client.get("/health")).status_code == 200


def test_nap_hong_thi_thu_nap_lai_sau_mot_khoang(monkeypatch):
    so_lan = []

    def loader(*_):
        so_lan.append(1)
        if len(so_lan) == 1:
            raise OSError("mạng đứt")
        return MoHinhGia()

    dc = GiongDoc(True, loader=loader)
    dc.nap()
    assert dc.trang_thai == "error"
    with pytest.raises(dong_co.GiongDocKhongSan) as e:      # chưa đủ thời gian: giữ nguyên lỗi
        dc.tong_hop("Xin chào.")
    assert e.value.ma == "tts_failed"
    monkeypatch.setattr(dong_co, "NAP_LAI_SAU_GIAY", 0.0)
    with pytest.raises(dong_co.GiongDocKhongSan) as e:      # đủ thời gian: bắt đầu nạp lại ở luồng nền
        dc.tong_hop("Xin chào.")
    assert e.value.ma == "tts_loading"
    assert cho_den(lambda: dc.trang_thai == "ready") and len(so_lan) == 2


async def test_dang_ban_qua_lau_la_503(monkeypatch):
    dc, mo_hinh = dong_co_san_sang()
    mo_hinh.tre_giay = 0.6
    monkeypatch.setattr(dong_co, "CHO_LUOT_GIAY", 0.05)
    luong = threading.Thread(target=dc.tong_hop, args=("Xin chào.",))
    luong.start()
    assert cho_den(lambda: len(mo_hinh.cac_lan_goi) == 1)      # luồng kia đã giữ lượt sinh
    r = await tao_client(dc).post("/v1/tts", json={"text": "Tạm biệt."})
    luong.join()
    assert r.status_code == 503 and r.json()["errorCode"] == "tts_busy" and "Retry-After" in r.headers


# ---------------------------------------------------------------- 200 với mô hình giả
async def test_thanh_cong_tra_mp3_mono_kem_tieu_de():
    dc, mo_hinh = dong_co_san_sang()
    r = await tao_client(dc).post("/v1/tts", json={"text": "Mỹ Sơn có từ xa xưa. Xin chào!", "voice": "vieneu-mai-anh"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.headers["X-Voice"] == "vieneu-mai-anh"
    thoi_luong = int(r.headers["X-Duration-Ms"])
    assert la_mp3(r.content)
    # Hai câu x 0,5 giây + im lặng đầu / giữa câu / cuối (150 + 350 + 200 ms)
    assert 1500 < thoi_luong < 1900
    # CBR 80 kbps: kích thước tệp khớp thời lượng (sai số cho tiêu đề và khung cuối)
    assert abs(len(r.content) - thoi_luong * 80 / 8) < 0.15 * thoi_luong * 80 / 8
    assert len(mo_hinh.cac_lan_goi) == 2 and all(g[1] == "Mai Anh" for g in mo_hinh.cac_lan_goi)
    assert r.headers["X-Correlation-Id"] == "test-corr-1"


async def test_giong_mac_dinh_khi_khong_gui_voice():
    dc, _ = dong_co_san_sang()
    r = await tao_client(dc).post("/v1/tts", json={"text": "Xin chào."})
    assert r.status_code == 200 and r.headers["X-Voice"] == "vieneu-mai-anh"


async def test_chu_duoc_chuan_hoa_truoc_khi_dua_vao_may_doc():
    dc, mo_hinh = dong_co_san_sang()
    r = await tao_client(dc).post("/v1/tts", json={"text": "Ngày 10/5/2012, TP. Hà Nội có 82 bia."})
    assert r.status_code == 200
    doc = " ".join(g[0] for g in mo_hinh.cac_lan_goi)
    assert "2012" not in doc and "82" not in doc and "tám mươi hai" in doc


async def test_cau_dai_duoc_chia_mau_va_moi_mau_toi_da_250_ky_tu():
    dc, mo_hinh = dong_co_san_sang()
    cau = ", ".join(["đền tháp cổ nằm giữa thung lũng xanh"] * 20) + "."
    r = await tao_client(dc).post("/v1/tts", json={"text": cau})
    assert r.status_code == 200
    assert len(mo_hinh.cac_lan_goi) >= 3
    assert all(len(g[0]) <= 250 and g[2] == 400 for g in mo_hinh.cac_lan_goi)


def test_mot_luc_chi_sinh_mot_yeu_cau():
    dang_chay: list[int] = []
    toi_da: list[int] = []

    class DoDongThoi(MoHinhGia):
        def infer(self, text, voice, max_chars):
            dang_chay.append(1)
            toi_da.append(len(dang_chay))
            time.sleep(0.03)
            ket = super().infer(text, voice, max_chars)
            dang_chay.pop()
            return ket

    dc, _ = dong_co_san_sang(DoDongThoi())
    luong = [threading.Thread(target=dc.tong_hop, args=(f"Câu số {i}.",)) for i in range(4)]
    for t in luong:
        t.start()
    for t in luong:
        t.join()
    assert max(toi_da) == 1 and len(toi_da) == 4


# ---------------------------------------------------------------- /health và khởi động
async def test_health_bao_trang_thai_giong_doc_va_luon_200():
    assert (await tao_client(GiongDoc(False)).get("/health")).json()["tts"] == "off"

    dc = GiongDoc(True, loader=lambda *_: MoHinhGia())
    dc._trang_thai = dong_co.DANG_NAP
    client = tao_client(dc)
    r = await client.get("/health", headers={})
    assert r.status_code == 200 and r.json()["tts"] == "loading"

    dc.nap()
    assert (await client.get("/health")).json()["tts"] == "ready"

    def hong(*_):
        raise RuntimeError("x")

    dc_hong = GiongDoc(True, loader=hong)
    dc_hong.nap()
    assert (await tao_client(dc_hong).get("/health")).json()["tts"] == "error"


def test_khoi_dong_nap_o_luong_nen_va_khong_lam_gi_khi_tat():
    cho = threading.Event()

    def loader(*_):
        cho.wait(2)
        return MoHinhGia()

    dc = GiongDoc(True, loader=loader)
    dc.khoi_dong()
    assert dc.trang_thai == "loading"           # trả về ngay, chưa đợi nạp xong
    cho.set()
    assert cho_den(lambda: dc.trang_thai == "ready")

    tat = GiongDoc(False, loader=loader)
    tat.khoi_dong()
    assert tat.trang_thai == "off"


async def test_lifespan_khoi_dong_nap_khi_bat():
    dc = GiongDoc(True, loader=lambda *_: MoHinhGia())
    cfg = Settings(ai_internal_key=INTERNAL_KEY, anthropic_api_key="khong-dung")
    app = create_app(cfg, FakeLlm(ok({})), configure_logging=False, giong_doc=dc)
    assert dc.trang_thai == "off"
    async with app.router.lifespan_context(app):
        assert cho_den(lambda: dc.trang_thai == "ready")


def test_cau_hinh_mac_dinh_tat_giong_doc_hai_luong_tu_chon_do_chinh_xac():
    cfg = Settings(ai_internal_key=INTERNAL_KEY)
    assert cfg.giong_doc_bat is False and cfg.giong_doc_luong == 2 and cfg.giong_doc_do_chinh_xac == "auto"
    bat = Settings(ai_internal_key=INTERNAL_KEY, giong_doc_bat="1", giong_doc_luong="4", giong_doc_do_chinh_xac="fp32")
    assert bat.giong_doc_bat is True and bat.giong_doc_luong == 4 and bat.giong_doc_do_chinh_xac == "fp32"
    assert create_app(cfg, FakeLlm(ok({})), configure_logging=False).state.giong_doc.trang_thai == "off"
