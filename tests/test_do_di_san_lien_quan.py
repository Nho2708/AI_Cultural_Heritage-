"""Đo di sản liên quan (scripts/danh-gia/do-di-san-lien-quan.py): hai cách xếp, đọc và kiểm tệp nhãn, precision@3 và đồng thuận. Không mạng."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

THU_MUC = Path(__file__).resolve().parent.parent / "scripts" / "danh-gia"
sys.path.insert(0, str(THU_MUC))
_spec = importlib.util.spec_from_file_location("do_di_san_lien_quan", THU_MUC / "do-di-san-lien-quan.py")
dm = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(dm)  # type: ignore[union-attr]


def chi_tiet(ma, ten, loai, tinh_id, vung, cap="UNESCO", pha=None, mo_ta=""):
    return {"id": ma, "name": ten, "heritageType": loai, "provinceId": tinh_id, "province": {"region": vung}, "recognitionLevel": cap,
            "timeline": pha or [], "shortDescription": mo_ta}


DI_SAN = [
    chi_tiet(1, "Thành cổ Alpha", "TANGIBLE", 1, "Bắc", pha=[{"startYear": 1000, "endYear": 1500}], mo_ta="Kinh đô cổ ven sông Hồng"),
    chi_tiet(2, "Văn miếu Beta", "TANGIBLE", 1, "Bắc", pha=[{"startYear": 1070, "endYear": 1800}], mo_ta="Trường học cổ của kinh đô"),
    chi_tiet(3, "Hát ví Gamma", "INTANGIBLE", 40, "Trung", mo_ta="Nghệ thuật hát dân gian miền Trung"),
    chi_tiet(4, "Hát giặm Delta", "INTANGIBLE", 40, "Trung", mo_ta="Nghệ thuật hát dân gian miền Trung"),
    chi_tiet(5, "Vịnh Epsilon", "NATURAL", 22, "Bắc", mo_ta="Cảnh quan biển đảo đá vôi"),
]


def test_features_use_timeline_range_and_name_plus_description():
    f = dm.dung_dac_trung(DI_SAN[0])
    assert (f.year_from, f.year_to) == (1000, 1500)
    assert f.type == "TANGIBLE" and f.province_id == 1 and f.region == "Bắc" and f.level == "UNESCO"
    assert f.text == "Thành cổ Alpha Kinh đô cổ ven sông Hồng"
    assert dm.dung_dac_trung(DI_SAN[2]).year_from is None


def test_ranking_orders_by_shared_attributes_and_ignores_itself():
    dt = [dm.dung_dac_trung(d) for d in DI_SAN]
    xep = dm.xep_hang(dt, "thuoc_tinh_va_tfidf")
    assert xep[1][0] == 2  # cùng loại, cùng tỉnh, cùng vùng, cùng cấp, giao khoảng năm
    assert xep[3][0] == 4  # cùng loại, tỉnh, vùng và mô tả giống hệt
    assert all(m not in xep[m] for m in xep)


def test_attributes_only_turns_text_similarity_off():
    dt = [dm.dung_dac_trung(d) for d in DI_SAN]
    chi_tt = dm.xep_hang(dt, "chi_thuoc_tinh")
    day_du = dm.xep_hang(dt, "thuoc_tinh_va_tfidf")
    # Hát ví và hát giặm giống nhau cả thuộc tính lẫn chữ; ở cách đầy đủ điểm cao hơn nhờ chữ nên vẫn đứng đầu, ở cách chỉ thuộc tính vẫn đứng đầu vì thuộc tính.
    assert chi_tt[3][0] == 4 and day_du[3][0] == 4
    # Cách chỉ thuộc tính không so_lan_goi TF-IDF: kiểm bằng cách thay hàm và đếm số lần so_lan_goi.
    so_lan_goi = []
    original = dm.rank._text_similarities
    dm.rank._text_similarities = lambda *a, **k: so_lan_goi.append(1) or original(*a, **k)
    try:
        dm.xep_hang(dt, "chi_thuoc_tinh")
        assert so_lan_goi == []
        dm.xep_hang(dt, "thuoc_tinh_va_tfidf")
        assert len(so_lan_goi) == len(dt)
    finally:
        dm.rank._text_similarities = original


def nhan_mau(ghi_de=None):
    ghi_de = ghi_de or {}
    muc = [{"id": d["id"], "slug": f"d{d['id']}", "ten": d["name"], "nhanNguoi1": [], "nhanNguoi2": [], "thongNhat": []} for d in DI_SAN]
    for m in muc:
        m.update(ghi_de.get(m["id"], {}))
    return {"nguoiGan1": "A", "nguoiGan2": "B", "diSan": muc}


def test_label_state_detection():
    assert dm.tinh_trang_nhan(None) == "khong_co_tep"
    assert dm.tinh_trang_nhan(nhan_mau()) == "trong"
    assert dm.tinh_trang_nhan(nhan_mau({1: {"nhanNguoi1": [2, 3, 4]}})) == "chua_thong_nhat"
    assert dm.tinh_trang_nhan(nhan_mau({1: {"thongNhat": [2, 3, 4]}})) == "thong_nhat_mot_phan"
    day_du = {m: {"thongNhat": [x for x in (1, 2, 3, 4, 5) if x != m][:3]} for m in (1, 2, 3, 4, 5)}
    assert dm.tinh_trang_nhan(nhan_mau(day_du)) == "co_thong_nhat"


def test_precision_against_agreed_list_and_each_labeller():
    dt = [dm.dung_dac_trung(d) for d in DI_SAN]
    xep = dm.xep_hang(dt, "thuoc_tinh_va_tfidf")
    theo_di_san = {m: {"chi_thuoc_tinh": dm.xep_hang(dt, "chi_thuoc_tinh")[m], "thuoc_tinh_va_tfidf": xep[m]} for m in xep}
    # Chỉ gán nhãn cho di sản 1 (nhãn thống nhất = chính ba mục đầu của cách đầy đủ => precision 1) và di sản 3 (ba mục đầu là 4, 1, 2; nhãn 4, 5, 1 trúng hai).
    nhan = nhan_mau({1: {"thongNhat": xep[1][:3], "nhanNguoi1": xep[1][:3], "nhanNguoi2": [5, 4, 3]},
                       3: {"thongNhat": [4, 5, 1]}})
    kq = dm.do_precision(theo_di_san, nhan)["thuoc_tinh_va_tfidf"]
    assert kq["thong_nhat"]["so_di_san"] == 2
    assert kq["thong_nhat"]["precision_at_3"] == pytest.approx((1.0 + 2 / 3) / 2)
    assert kq["nguoi_1"]["so_di_san"] == 1 and kq["nguoi_1"]["precision_at_3"] == pytest.approx(1.0)
    assert kq["nguoi_2"]["so_di_san"] == 1


def test_agreement_between_two_labellers():
    nhan = nhan_mau({1: {"nhanNguoi1": [2, 3, 4], "nhanNguoi2": [2, 3, 4]}, 2: {"nhanNguoi1": [1, 3, 4], "nhanNguoi2": [1, 3, 5]}})
    dt = dm.do_dong_thuan(nhan)
    assert dt["so_di_san_ca_hai_da_gan"] == 2
    assert dt["jaccard_trung_binh"] == pytest.approx((1.0 + 2 / 4) / 2)
    assert dt["kappa_cohen"] is not None and 0 < dt["kappa_cohen"] < 1
    assert dm.do_dong_thuan(nhan_mau()) == {"so_di_san_ca_hai_da_gan": 0}


def test_label_file_validation(tmp_path):
    ma = {d["id"] for d in DI_SAN}
    tep = tmp_path / "nhan.json"
    assert dm.doc_nhan(tmp_path / "khong-co.json", ma) is None
    tep.write_text(json.dumps(nhan_mau({1: {"nhanNguoi1": [2, 3, 4]}})), encoding="utf-8")
    assert dm.doc_nhan(tep, ma)["diSan"][0]["nhanNguoi1"] == [2, 3, 4]
    for xau in ({1: {"nhanNguoi1": [1, 2, 3]}}, {1: {"nhanNguoi1": [2, 2, 3]}}, {1: {"nhanNguoi1": [2, 99, 3]}}, {1: {"nhanNguoi1": [2, 3]}}):
        tep.write_text(json.dumps(nhan_mau(xau)), encoding="utf-8")
        with pytest.raises(SystemExit) as loi:
            dm.doc_nhan(tep, ma)
        assert loi.value.code == 2


def test_template_lists_every_heritage_with_empty_labels():
    mau = dm.tao_mau([{"id": 7, "slug": "bay", "name": "Di sản bảy"}])
    assert mau["diSan"] == [{"id": 7, "slug": "bay", "ten": "Di sản bảy", "nhanNguoi1": [], "nhanNguoi2": [], "thongNhat": []}]
    assert mau["huongDan"] and mau["nguoiGan1"] == "" and mau["nguoiGan2"] == ""


def test_report_without_labels_says_it_cannot_measure_and_still_lists_top_three():
    dt = [dm.dung_dac_trung(d) for d in DI_SAN]
    theo = {m: {c: dm.xep_hang(dt, c)[m] for c, _ in dm.CACH_XEP} for m in (d["id"] for d in DI_SAN)}
    bao_cao = dm.viet_bao_cao({d["id"]: d["name"] for d in DI_SAN}, theo, "trong", None, None, ("", ""))
    assert "Không có số precision@3" in bao_cao
    assert "Thành cổ Alpha (1)" in bao_cao and "Chỉ thuộc tính" in bao_cao
