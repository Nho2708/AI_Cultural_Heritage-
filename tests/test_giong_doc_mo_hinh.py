"""Chọn độ chính xác theo CPU (VNNI), số luồng, nạp mô hình (không nhập vieneu thật) và phần ghép/mã hóa âm thanh dùng chung."""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from app.giong_doc import mo_hinh
from app.giong_doc.am_thanh import chuan_hoa_am_luong, ghep_theo_cau, luu_mp3, ma_hoa_mp3
from app.giong_doc.chuan_bi import chuan_bi_cau
from app.giong_doc.mo_hinh import chon_do_chinh_xac, cpu_co_vnni

CPUINFO_CO_VNNI = "processor\t: 0\nmodel name\t: Intel\nflags\t\t: fpu avx2 avx512f avx512_vnni avx512bw\n\nprocessor\t: 1\n"
CPUINFO_AVX_VNNI = "flags : fpu avx2 avx_vnni sse4_2\n"
CPUINFO_KHONG_VNNI = "flags : fpu avx2 avx512f avx512bw sse4_2\n"


def test_cpu_co_vnni_doc_co_flags():
    assert cpu_co_vnni(CPUINFO_CO_VNNI) is True
    assert cpu_co_vnni(CPUINFO_AVX_VNNI) is True
    assert cpu_co_vnni(CPUINFO_KHONG_VNNI) is False
    assert cpu_co_vnni("") is False
    assert cpu_co_vnni("model name : avx512_vnni\nflags : fpu avx2\n") is False      # chỉ tính dòng flags
    assert cpu_co_vnni("flags : fpu avx512_vnni_gia\n") is False                      # khớp nguyên cờ


def test_cpu_co_vnni_nen_tang_khac_linux_la_false_cho_an_toan():
    assert cpu_co_vnni(nen_tang="win32") is False
    assert cpu_co_vnni(nen_tang="darwin") is False


@pytest.mark.parametrize("cau_hinh, vnni, ket_qua", [
    ("auto", True, "int8"),
    ("auto", False, "fp32"),
    ("", True, "int8"),
    ("AUTO", False, "fp32"),
    ("int8", False, "int8"),
    ("fp32", True, "fp32"),
    (" Int8 ", False, "int8"),
])
def test_chon_do_chinh_xac(cau_hinh, vnni, ket_qua):
    assert chon_do_chinh_xac(cau_hinh, vnni) == ket_qua


def test_dat_so_luong_khong_ghi_de_bien_da_dat(monkeypatch):
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    monkeypatch.setenv("MKL_NUM_THREADS", "7")
    monkeypatch.delenv("OPENBLAS_NUM_THREADS", raising=False)
    mo_hinh.dat_so_luong(3)
    assert os.environ["OMP_NUM_THREADS"] == "3" and os.environ["OPENBLAS_NUM_THREADS"] == "3"
    assert os.environ["MKL_NUM_THREADS"] == "7"
    monkeypatch.delenv("OMP_NUM_THREADS")
    monkeypatch.delenv("OPENBLAS_NUM_THREADS")


def _vieneu_gia(monkeypatch, tao):
    module = types.ModuleType("vieneu")
    module.Vieneu = tao
    monkeypatch.setitem(sys.modules, "vieneu", module)


def test_tai_vieneu_truyen_tham_so(monkeypatch):
    da_goi = {}

    def tao(**kw):
        da_goi.update(kw)
        return "mo-hinh"

    _vieneu_gia(monkeypatch, tao)
    assert mo_hinh.tai_vieneu("int8", 2) == "mo-hinh"
    assert da_goi == {"mode": "v3turbo", "backend": "onnx", "precision": "int8", "threads": 2}


def test_tai_vieneu_go_symlink_roi_nap_lai_khi_onnx_tu_choi_tep_ngoai(monkeypatch, tmp_path):
    lan = []

    def tao(**kw):
        lan.append(kw)
        if len(lan) == 1:
            raise RuntimeError("External data path validation failed")
        return "mo-hinh"

    da_go = []
    _vieneu_gia(monkeypatch, tao)
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setattr(mo_hinh, "go_symlink", lambda goc: da_go.append(goc))
    assert mo_hinh.tai_vieneu("fp32", 0) == "mo-hinh"
    assert len(lan) == 2 and da_go == [Path(tmp_path)]


def test_tai_vieneu_loi_khac_thi_nem_ra(monkeypatch):
    def tao(**kw):
        raise RuntimeError("hết bộ nhớ")

    _vieneu_gia(monkeypatch, tao)
    with pytest.raises(RuntimeError, match="hết bộ nhớ"):
        mo_hinh.tai_vieneu()


# ---------------------------------------------------------------- âm thanh dùng chung
def _sin(giay: float, sr: int = 24000, bien_do: float = 0.1) -> np.ndarray:
    return (bien_do * np.sin(2 * np.pi * 220 * np.arange(int(sr * giay)) / sr)).astype(np.float32)


def test_ghep_theo_cau_ghi_moc_va_chuan_hoa_am_luong():
    cau = [{"text": "Một.", "chunks": ["a"]}, {"text": "Hai.", "chunks": ["b", "c"]}]
    song, moc = ghep_theo_cau(cau, lambda _: _sin(1.0), 24000)
    assert [m["text"] for m in moc] == ["Một.", "Hai."]
    assert moc[0]["startMs"] == 150 and moc[1]["startMs"] > moc[0]["endMs"]
    rms = float(np.sqrt(np.mean(song ** 2)))
    assert abs(20 * np.log10(rms) - (-20.0)) < 1.0 and float(np.max(np.abs(song))) <= 10 ** (-1 / 20) + 1e-6


def test_chuan_hoa_am_luong_gioi_han_dinh_va_chiu_duoc_rong():
    assert chuan_hoa_am_luong(np.zeros(0, dtype=np.float32)).size == 0
    x = chuan_hoa_am_luong(np.concatenate([_sin(1.0, bien_do=0.01), np.array([1.0], dtype=np.float32)]))
    assert float(np.max(np.abs(x))) <= 10 ** (-1 / 20) + 1e-6


def test_ma_hoa_mp3_va_luu_mp3_cho_cung_byte(tmp_path):
    song = _sin(2.0)
    mp3 = ma_hoa_mp3(song, 24000, 80)
    assert mp3[:3] == b"ID3" or mp3[0] == 0xFF
    assert abs(len(mp3) - 2.0 * 80 * 1000 / 8) < 2500
    luu_mp3(song, 24000, tmp_path / "a" / "b.mp3")
    assert (tmp_path / "a" / "b.mp3").read_bytes() == mp3
    assert not list((tmp_path / "a").glob("*.tmp"))


def test_ma_hoa_mp3_lay_mau_lai_khi_tan_so_la():
    mp3 = ma_hoa_mp3(_sin(1.0, sr=20000), 20000, 64)        # 20000 Hz không có trong bảng của lameenc
    assert len(mp3) > 1000


def test_chuan_bi_cau_chi_chuan_hoa_tieng_viet():
    vi = chuan_bi_cau("Có 82 bia ở TP. Hà Nội.", "vi")
    assert vi[0]["text"] == "Có 82 bia ở TP. Hà Nội." and "tám mươi hai" in vi[0]["chunks"][0]
    en = chuan_bi_cau("There are 82 steles.", "en")
    assert en[0]["chunks"] == ["There are 82 steles."]
    assert chuan_bi_cau("   ", "vi") == []


def test_go_symlink_thay_symlink_trong_snapshots_bang_tep_that(tmp_path):
    from app.giong_doc.go_symlink_hf import go_symlink

    blob = tmp_path / "hub" / "blobs" / "abc"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"du lieu")
    snap = tmp_path / "hub" / "models--x" / "snapshots" / "v1"
    snap.mkdir(parents=True)
    try:
        (snap / "model.data").symlink_to(blob)
    except OSError:
        pytest.skip("Không tạo được symlink trên máy này (thiếu quyền)")
    assert go_symlink(tmp_path) == 1
    tep = snap / "model.data"
    assert not tep.is_symlink() and tep.read_bytes() == b"du lieu"
    assert go_symlink(tmp_path) == 0
