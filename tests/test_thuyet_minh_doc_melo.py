"""Chữ đưa vào MeloTTS: bỏ tên gốc tiếng Việt trong ngoặc ở bản Hàn, Trung, Nhật và bỏ dấu tiếng Việt, không đụng chữ của ngôn ngữ đích."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "thuyet-minh"))

import pytest
from doc_melo import doc_an_toan, lam_sach


def test_bo_ten_goc_trong_ngoac_o_ban_nhat_va_giu_dau_kana():
    assert lam_sach("ホイアン（Hội An）は世界遺産です。がぎぐ", "melo-jp") == "ホイアンは世界遺産です。がぎぐ"


def test_bo_ten_goc_trong_ngoac_o_ban_han():
    assert lam_sach("푸쭉(Phù Đổng) 축제는 하노이에서 열립니다.", "melo-kr") == "푸쭉 축제는 하노이에서 열립니다."


def test_bo_dau_ten_rieng_con_lai_o_ban_trung():
    assert lam_sach("扶董天王在Phủ Dầy举行。", "melo-zh") == "扶董天王在Phu Day举行。"


def test_ban_anh_giu_ngoac_va_bo_dau():
    assert lam_sach("The Ancient Town of Hội An (Quảng Nam) is a port.", "melo-en-us") == "The Ancient Town of Hoi An (Quang Nam) is a port."


def test_khong_con_chu_nao_thi_giu_nguyen():
    assert lam_sach("(Đà Nẵng)", "melo-jp") == "(Đà Nẵng)"


def test_ban_nhat_thay_chu_han_hiem_bang_am_on():
    assert lam_sach("甌雒国の都でした。霞漳会館です。", "melo-jp") == "甌ラク国の都でした。霞ショウ会館です。"


def test_ban_trung_giu_nguyen_chu_han_hiem():
    assert lam_sach("霞漳会馆", "melo-zh") == "霞漳会馆"


def test_doc_an_toan_bo_chu_khong_doc_duoc_roi_doc_lai():
    da_doc = []

    def doc(chu):
        da_doc.append(chu)
        if "鬱" in chu:
            raise AssertionError((["鬱"], chu, []))
        return [0.0]

    assert doc_an_toan(doc, "鬱金の寺です。") == [0.0]
    assert da_doc == ["鬱金の寺です。", "金の寺です。"]


def test_doc_an_toan_loi_khac_thi_bao_ra():
    def doc(chu):
        raise AssertionError("lỗi khác")

    with pytest.raises(AssertionError):
        doc_an_toan(doc, "寺です。")
