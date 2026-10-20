"""Chữ đưa vào MeloTTS: bỏ tên gốc tiếng Việt trong ngoặc ở bản Hàn, Trung, Nhật và bỏ dấu tiếng Việt, không đụng chữ của ngôn ngữ đích."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "thuyet-minh"))

from doc_melo import lam_sach


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
