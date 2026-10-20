"""Bộ chuẩn hóa văn bản tiếng Việt của công cụ tạo thuyết minh (tools/thuyet-minh/chuan_hoa_vi.py): số, ngày, thế kỷ La Mã,
đơn vị, viết tắt, chữ cái đơn, dấu câu. Không cần gói nào ngoài thư viện chuẩn."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

THU_MUC_CONG_CU = Path(__file__).resolve().parent.parent / "tools" / "thuyet-minh"
sys.path.insert(0, str(THU_MUC_CONG_CU))

from chuan_hoa_vi import chuan_hoa, chuan_hoa_doan, chuoi_so_thanh_chu, la_ma_thanh_so, so_thanh_chu


# ---------------------------------------------------------------- đọc số
@pytest.mark.parametrize("so, chu", [
    (0, "không"),
    (5, "năm"),
    (10, "mười"),
    (11, "mười một"),
    (14, "mười bốn"),
    (15, "mười lăm"),
    (21, "hai mươi mốt"),
    (24, "hai mươi tư"),
    (25, "hai mươi lăm"),
    (47, "bốn mươi bảy"),
    (82, "tám mươi hai"),
    (105, "một trăm linh năm"),
    (110, "một trăm mười"),
    (949, "chín trăm bốn mươi chín"),
    (1000, "một nghìn"),
    (1272, "một nghìn hai trăm bảy mươi hai"),
    (1484, "một nghìn bốn trăm tám mươi tư"),
    (1653, "một nghìn sáu trăm năm mươi ba"),
    (1805, "một nghìn tám trăm linh năm"),
    (1903, "một nghìn chín trăm linh ba"),
    (2009, "hai nghìn không trăm linh chín"),
    (2012, "hai nghìn không trăm mười hai"),
    (2025, "hai nghìn không trăm hai mươi lăm"),
    (1000005, "một triệu không trăm linh năm"),
    (2500000, "hai triệu năm trăm nghìn"),
])
def test_so_thanh_chu(so, chu):
    assert so_thanh_chu(so) == chu


def test_so_kieu_viet_nam_dau_cham_ngan_dau_phay_thap_phan():
    assert chuoi_so_thanh_chu("5.717,878") == "năm nghìn bảy trăm mười bảy phẩy tám bảy tám"
    assert chuoi_so_thanh_chu("525,748") == "năm trăm hai mươi lăm phẩy bảy bốn tám"
    assert chuoi_so_thanh_chu("1.250.000") == "một triệu hai trăm năm mươi nghìn"


def test_la_ma():
    assert la_ma_thanh_so("XIII") == 13
    assert la_ma_thanh_so("XIX") == 19
    assert la_ma_thanh_so("XX") == 20


# ---------------------------------------------------------------- markdown
def test_bo_markdown_tieu_de_dam_dau_muc_chu_thich():
    vb = "## Giới thiệu\n\n**Văn Miếu** được dựng năm 1070[1].\n\n- Bia đá\n- Khuê Văn Các\n\n1. Mục một"
    ket = chuan_hoa(vb)
    assert "#" not in ket and "*" not in ket and "[1]" not in ket
    assert ket.startswith("Giới thiệu.")
    assert "Văn Miếu được dựng năm một nghìn không trăm bảy mươi." in ket
    assert "Bia đá. Khuê Văn Các." in ket
    assert "Mục một." in ket


def test_ngat_doan_thanh_het_cau_va_gop_khoang_trang():
    vb = "Câu một\n\n\nCâu   hai\nvẫn đoạn hai"
    assert chuan_hoa(vb) == "Câu một.\n\nCâu hai vẫn đoạn hai."


# ---------------------------------------------------------------- ngày tháng
def test_ngay_thang_nam():
    assert chuan_hoa_doan("xếp hạng ngày 10/5/2012") == "Xếp hạng ngày mười tháng năm năm hai nghìn không trăm mười hai."
    assert chuan_hoa_doan("Ngày 12/7/2025, tại kỳ họp") == "Ngày mười hai tháng bảy năm hai nghìn không trăm hai mươi lăm, tại kỳ họp."
    assert chuan_hoa_doan("Ngày 12/8/2009, Thủ tướng") == "Ngày mười hai tháng tám năm hai nghìn không trăm linh chín, Thủ tướng."
    assert chuan_hoa_doan("từ 01/7/2025") == "Từ ngày một tháng bảy năm hai nghìn không trăm hai mươi lăm."
    assert chuan_hoa_doan("tháng 4/2010") == "Tháng tư năm hai nghìn không trăm mười."


def test_khoang_nam():
    assert chuan_hoa_doan("Năm 1903–1904, các học giả Pháp") == \
        "Từ năm một nghìn chín trăm linh ba đến năm một nghìn chín trăm linh bốn, các học giả Pháp."
    assert chuan_hoa_doan("giai đoạn 1428-1788") == \
        "Giai đoạn từ năm một nghìn bốn trăm hai mươi tám đến năm một nghìn bảy trăm tám mươi tám."
    assert chuan_hoa_doan("từ năm 1903–1904") == \
        "Từ năm một nghìn chín trăm linh ba đến năm một nghìn chín trăm linh bốn."
    assert chuan_hoa_doan("kéo dài 4–6 tháng") == "Kéo dài bốn đến sáu tháng."


# ---------------------------------------------------------------- thế kỷ La Mã
def test_the_ky_la_ma_va_khoang():
    assert chuan_hoa_doan("cuối thế kỷ XX") == "Cuối thế kỷ hai mươi."
    assert chuan_hoa_doan("vào thế kỷ XIII") == "Vào thế kỷ mười ba."
    assert chuan_hoa_doan("khoảng thế kỷ XV–XVI và thịnh đạt nhất trong thế kỷ XVII–XVIII") == \
        "Khoảng thế kỷ mười lăm đến mười sáu và thịnh đạt nhất trong thế kỷ mười bảy đến mười tám."
    assert chuan_hoa_doan("tháp (thế kỷ VII–VIII)") == "Tháp, thế kỷ bảy đến tám."
    assert chuan_hoa_doan("thế kỉ XIX") == "Thế kỉ mười chín."


# ---------------------------------------------------------------- đơn vị
def test_don_vi():
    assert chuan_hoa_doan("vùng lõi rộng 525,748 ha và vùng đệm rộng 5.717,878 ha") == \
        "Vùng lõi rộng năm trăm hai mươi lăm phẩy bảy bốn tám héc-ta và vùng đệm rộng năm nghìn bảy trăm mười bảy phẩy tám bảy tám héc-ta."
    assert chuan_hoa_doan("cách Hà Nội 120 km") == "Cách Hà Nội một trăm hai mươi ki-lô-mét."
    assert chuan_hoa_doan("rộng 2 km², cao 5 m, tăng 15%") == \
        "Rộng hai ki-lô-mét vuông, cao năm mét, tăng mười lăm phần trăm."
    assert chuan_hoa_doan("diện tích 300 m2") == "Diện tích ba trăm mét vuông."


# ---------------------------------------------------------------- viết tắt, số hiệu
def test_viet_tat():
    assert chuan_hoa_doan("Theo UNESCO, vùng lõi") == "Theo U-nét-xcô, vùng lõi."
    assert chuan_hoa_doan("TP. Hà Nội và UBND tỉnh") == "Thành phố Hà Nội và ủy ban nhân dân tỉnh."
    assert chuan_hoa_doan("TP.HCM") == "Thành phố Hồ Chí Minh."


def test_so_hieu_van_ban():
    assert chuan_hoa_doan("(Quyết định 1272/QĐ-TTg)") == \
        "Quyết định số một nghìn hai trăm bảy mươi hai của Thủ tướng Chính phủ."
    assert chuan_hoa_doan("Quyết định số 548/QĐ-TTg") == \
        "Quyết định số năm trăm bốn mươi tám của Thủ tướng Chính phủ."
    assert chuan_hoa_doan("Nghị định 166/NĐ-CP") == "Nghị định số một trăm sáu mươi sáu của Chính phủ."
    assert chuan_hoa_doan("(hồ sơ số 949)") == "Hồ sơ số chín trăm bốn mươi chín."


# ---------------------------------------------------------------- chữ cái, mã
def test_chu_cai_dau_ten_nuoc_ngoai():
    assert chuan_hoa_doan("trong đó có H. Parmentier, tiến hành") == \
        "Trong đó có hát Pác-măng-chi-ê, tiến hành."
    assert chuan_hoa_doan("P. Stern") == "Pê Xtéc-nơ."
    assert chuan_hoa_doan("ở H. Thanh Trì") == "Ở huyện Thanh Trì."


def test_ma_thap_va_danh_sach_chu_cai():
    assert chuan_hoa_doan("ở tháp E5; ở tháp C7") == "Ở tháp e năm. Ở tháp xê bảy."
    assert chuan_hoa_doan("nhóm tháp A1") == "Nhóm tháp a một."
    assert chuan_hoa_doan("theo chữ cái A, A', B, C, D, E, F, G, H và các tháp lẻ K, L, M, N – cách gọi vẫn dùng") == \
        "Theo chữ cái a, a phẩy, bê, xê, dê, e, ép, giê, hát và các tháp lẻ ca, e-lờ, em-mờ, en-nờ, cách gọi vẫn dùng."


def test_chu_cai_don_trong_ten_viet_khong_doi():
    assert chuan_hoa_doan("xã Y Tý và huyện U Minh") == "Xã Y Tý và huyện U Minh."


# ---------------------------------------------------------------- thứ tự
def test_thu_tu():
    assert chuan_hoa_doan("di sản thế giới thứ 9 của Việt Nam") == "Di sản thế giới thứ chín của Việt Nam."
    assert chuan_hoa_doan("kỳ họp lần thứ 47") == "Kỳ họp lần thứ bốn mươi bảy."
    assert chuan_hoa_doan("thứ 1, thứ 4") == "Thứ nhất, thứ tư."


# ---------------------------------------------------------------- dấu câu
def test_gach_ngang_giua_ten_la_ngat_khong_phai_den():
    assert chuan_hoa_doan("bia đá thời Lê – Mạc, Khuê Văn Các") == "Bia đá thời Lê, Mạc, Khuê Văn Các."
    assert chuan_hoa_doan("Yên Tử – Vĩnh Nghiêm – Côn Sơn, Kiếp Bạc") == "Yên Tử, Vĩnh Nghiêm, Côn Sơn, Kiếp Bạc."
    assert "đến" not in chuan_hoa_doan("sau Vịnh Hạ Long – Quần đảo Cát Bà")


def test_ngoac_va_ngoac_kep_thanh_ngat():
    assert chuan_hoa_doan("ở Paris (Pháp), quần thể") == "Ở Pa-ri, Pháp, quần thể."
    assert chuan_hoa_doan('xếp hạng "Di tích kiến trúc nghệ thuật Khu đền tháp Mỹ Sơn" là di tích') == \
        "Xếp hạng, Di tích kiến trúc nghệ thuật Khu đền tháp Mỹ Sơn, là di tích."
    assert chuan_hoa_doan("ba địa phương: Quảng Ninh, Bắc Ninh") == "Ba địa phương, Quảng Ninh, Bắc Ninh."


def test_bo_ngoac_tieng_anh():
    assert chuan_hoa_doan("Khu đền tháp Mỹ Sơn (My Son Sanctuary) vào Danh sách") == \
        "Khu đền tháp Mỹ Sơn vào Danh sách."
    assert chuan_hoa_doan("Mỹ Sơn (My Son Sanctuary)", bo_ngoac_anh=False) == "Mỹ Sơn, My Son Sanctuary."


def test_so_dem_thuong():
    assert chuan_hoa_doan("có 82 bia tiến sĩ") == "Có tám mươi hai bia tiến sĩ."
    assert chuan_hoa_doan("dựng 10 tấm bia") == "Dựng mười tấm bia."
    assert chuan_hoa_doan("gồm 12 địa điểm") == "Gồm mười hai địa điểm."


def test_khong_con_chu_so_hay_ky_hieu_trong_cac_doan_mau():
    tep = THU_MUC_CONG_CU / "mau" / "vi-du.json"
    for muc in json.loads(tep.read_text(encoding="utf-8"))["items"]:
        if muc["language"] != "vi":
            continue
        ket = chuan_hoa(muc["shortText"])
        assert not any(c.isdigit() for c in ket), muc["slug"]
        for xau in ("UNESCO", "/", "(", ")", '"', "–", " km", "XIII", "IV", "H.", "TP."):
            assert xau not in ket, (muc["slug"], xau)
        assert ket[-1] in ".!?"
