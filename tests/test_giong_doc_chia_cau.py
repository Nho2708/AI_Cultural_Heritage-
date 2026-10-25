"""Tách câu hiển thị và chia mẩu đọc của giọng đọc (app/giong_doc/chia_cau.py). Không cần gói nào ngoài thư viện chuẩn."""
from __future__ import annotations

from app.giong_doc.chia_cau import SO_CAU_TOI_DA, chia_mau, tach_cau


def test_tach_o_cham_than_hoi_ba_cham():
    assert tach_cau("Câu một. Câu hai! Câu ba? Câu bốn… Câu năm") == ["Câu một.", "Câu hai!", "Câu ba?", "Câu bốn…", "Câu năm"]


def test_khong_tach_sau_viet_tat_va_chu_cai_don():
    assert tach_cau("Nhà khảo cổ H. Parmentier khảo sát năm 1903. Ông ở TP. Hà Nội.") == \
        ["Nhà khảo cổ H. Parmentier khảo sát năm 1903.", "Ông ở TP. Hà Nội."]
    assert tach_cau("GS. Trần Quốc Vượng, PGS. Nguyễn Lân Cường và TS. Lê Thị Liên v.v. đều tham gia. Hết.") == \
        ["GS. Trần Quốc Vượng, PGS. Nguyễn Lân Cường và TS. Lê Thị Liên v.v. đều tham gia.", "Hết."]
    assert tach_cau("Mr. Kazik helped. Dr. Lee agreed.") == ["Mr. Kazik helped.", "Dr. Lee agreed."]


def test_giu_ngoac_kep_dong_theo_cau():
    assert tach_cau('Ông nói "Đi thôi." Rồi đi.') == ['Ông nói "Đi thôi."', "Rồi đi."]
    assert tach_cau("He said “Go.” Then left (really).") == ["He said “Go.”", "Then left (really)."]


def test_trung_nhat_tach_o_dau_cau_toan_dau_khong_can_khoang_trang():
    assert tach_cau("下龙湾位于越南东北部。这里有许多岛屿！真美吗？是的") == ["下龙湾位于越南东北部。", "这里有许多岛屿！", "真美吗？", "是的"]
    assert tach_cau("「行こう。」と言った。") == ["「行こう。」", "と言った。"]


def test_han_tach_o_dau_cham():
    assert tach_cau("후에는 수도였습니다. 황성이 있습니다.") == ["후에는 수도였습니다.", "황성이 있습니다."]


def test_xuong_dong_cung_la_het_cau_va_gop_khoang_trang():
    assert tach_cau("Dòng  một\r\nDòng   hai.\n\nDòng ba") == ["Dòng một", "Dòng hai.", "Dòng ba"]


def test_mau_chi_co_dau_ghep_vao_cau_truoc_va_bo_rong():
    assert tach_cau("Thật sao?! ... Vâng.") == ["Thật sao?! ...", "Vâng."]
    assert tach_cau("   ") == []


def test_gioi_han_so_cau():
    cau = tach_cau(" ".join(f"Câu {i}." for i in range(1, SO_CAU_TOI_DA + 50)))
    assert len(cau) == SO_CAU_TOI_DA
    assert cau[-1].startswith(f"Câu {SO_CAU_TOI_DA}.") and cau[-1].endswith(f"Câu {SO_CAU_TOI_DA + 49}.")


def test_chia_mau_cau_ngan_giu_nguyen():
    assert chia_mau("Câu ngắn, có phẩy.") == ["Câu ngắn, có phẩy."]
    assert chia_mau("") == []


def test_chia_mau_cat_o_phay_khong_cat_giua_tu():
    cau = ", ".join(f"mệnh đề số {i} khá dài để thử" for i in range(1, 30)) + "."
    mau = chia_mau(cau, toi_da=100)
    assert all(len(m) <= 100 for m in mau)
    assert " ".join(mau) == cau
    assert all(m.endswith((",", ".")) for m in mau)


def test_chia_mau_khong_co_phay_cat_o_khoang_trang():
    cau = " ".join(["từ"] * 200)
    mau = chia_mau(cau, toi_da=50)
    assert all(len(m) <= 50 for m in mau) and " ".join(mau) == cau


def test_chia_mau_chu_han_khong_khoang_trang_cat_o_dau_phay_roi_cat_cung():
    cau = "，".join(["下龙湾位于越南东北部广宁省"] * 10) + "。"
    mau = chia_mau(cau, toi_da=40)
    assert all(len(m) <= 40 for m in mau) and "".join(mau) == cau
    assert chia_mau("越" * 95, toi_da=40) == ["越" * 40, "越" * 40, "越" * 15]
