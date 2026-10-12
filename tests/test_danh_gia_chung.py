"""Hàm thuần của bộ đánh giá gợi ý (scripts/danh-gia/danh_gia_chung.py): precision@k, hit@k, đường cơ sở, mô phỏng học sinh ảo có hạt giống. Không mạng."""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "danh-gia"))

import danh_gia_chung as dg

XAC_SUAT = {dg.KIEU_4_PHUONG_AN: 0.25, dg.KIEU_3_PHUONG_AN: 1 / 3, dg.KIEU_DUNG_SAI: 0.5}


def lop_mau() -> list[dg.BaiHoc]:
    """Năm bài, mỗi bài hai di sản; bài mã 1 cũ nhất. han_dong nhỏ là đóng sớm."""
    return [
        dg.BaiHoc(1, 101, ((10, 4), (11, 4)), "EASY", 30),
        dg.BaiHoc(2, 102, ((11, 4), (12, 4)), "MEDIUM", 21),
        dg.BaiHoc(3, 103, ((12, 4), (13, 4)), "HARD", 24),
        dg.BaiHoc(4, 104, ((13, 4), (14, 4)), "EASY", 27),
        dg.BaiHoc(5, 105, ((14, 4), (10, 4)), "MEDIUM", 33),
    ]


# ---- precision và trúng ----

def test_precision_at_k_counts_hits_in_top_k_and_always_divides_by_k():
    assert dg.precision_at_k([5, 6, 7, 8], {5, 7}, 3) == pytest.approx(2 / 3)
    assert dg.precision_at_k([5, 6, 7, 8], {8}, 3) == 0.0  # ngoài ba mục đầu thì không tính
    assert dg.precision_at_k([5], {5}, 3) == pytest.approx(1 / 3)  # danh sách ngắn hơn k bị tính thiệt
    assert dg.precision_at_k([], {1}, 3) == 0.0


def test_precision_at_k_rejects_non_positive_k():
    with pytest.raises(ValueError):
        dg.precision_at_k([1], {1}, 0)


def test_hit_at_k():
    assert dg.hit_at_k([1, 2, 3, 4], {3})
    assert not dg.hit_at_k([1, 2, 3, 4], {4})
    assert not dg.hit_at_k([], {1})


@pytest.mark.parametrize(("tong", "trung", "ky_vong"), [
    (10, 2, 1 - math.comb(8, 3) / math.comb(10, 3)),
    (10, 0, 0.0),
    (10, 8, 1.0),   # chỉ còn 2 mục không trúng, rút 3 mục thì chắc chắn trúng
    (2, 1, 1.0),    # ít hơn k mục: rút hết
    (0, 0, 0.0),
])
def test_random_hit_probability_is_exact(tong, trung, ky_vong):
    assert dg.xac_suat_trung_ngau_nhien(tong, trung) == pytest.approx(ky_vong)


def test_random_hit_probability_matches_simulation():
    rng = random.Random(7)
    kho = list(range(10))
    dem = sum(1 for _ in range(20000) if {0, 1} & set(rng.sample(kho, 3)))
    assert dem / 20000 == pytest.approx(dg.xac_suat_trung_ngau_nhien(10, 2), abs=0.015)


def test_combined_probability_of_independent_events():
    assert dg.hop_xac_suat(0.5, 0.5) == pytest.approx(0.75)
    assert dg.hop_xac_suat() == 0.0


def test_wilson_interval_contains_rate_and_is_ordered():
    thap, cao = dg.khoang_tin_cay_wilson(0.9, 100)
    assert thap < 0.9 < cao <= 1.0
    assert dg.khoang_tin_cay_wilson(0.5, 0) == (0.0, 0.0)


# ---- đồng thuận ----

def test_jaccard_and_kappa():
    assert dg.jaccard([1, 2, 3], [2, 3, 4]) == pytest.approx(2 / 4)
    assert dg.jaccard([], []) == 1.0
    a = [True, True, False, False]
    assert dg.cohen_kappa(a, a) == pytest.approx(1.0)
    assert dg.cohen_kappa(a, [not x for x in a]) == pytest.approx(-1.0)
    assert dg.cohen_kappa([True, True], [True, True]) is None  # không xác định
    with pytest.raises(ValueError):
        dg.cohen_kappa([True], [True, False])


# ---- mô phỏng ----

def test_answer_rule_uses_weak_probability_or_noise_rate():
    assert dg.tra_loi_dung(dg.KIEU_4_PHUONG_AN, True, 0.24, 0.1, XAC_SUAT)
    assert not dg.tra_loi_dung(dg.KIEU_4_PHUONG_AN, True, 0.25, 0.1, XAC_SUAT)
    assert not dg.tra_loi_dung(dg.KIEU_DUNG_SAI, False, 0.09, 0.1, XAC_SUAT)  # u dưới tỉ lệ nhầm thì sai
    assert dg.tra_loi_dung(dg.KIEU_DUNG_SAI, False, 0.1, 0.1, XAC_SUAT)


def test_simulated_rates_match_declared_parameters():
    rng = random.Random(11)
    n = 20000
    for kieu, p in XAC_SUAT.items():
        dung = sum(dg.tra_loi_dung(kieu, True, rng.random(), 0.1, XAC_SUAT) for _ in range(n)) / n
        assert dung == pytest.approx(p, abs=0.012)
    for nham in (0.10, 0.15, 0.20):
        dung = sum(dg.tra_loi_dung(dg.KIEU_4_PHUONG_AN, False, rng.random(), nham, XAC_SUAT) for _ in range(n)) / n
        assert dung == pytest.approx(1 - nham, abs=0.012)


def test_same_seed_gives_same_student_and_different_seed_differs():
    lop = lop_mau()
    a = dg.tao_hoc_sinh(0, "trung_binh", lop, "hat/1", 0.85)
    b = dg.tao_hoc_sinh(0, "trung_binh", lop, "hat/1", 0.85)
    c = dg.tao_hoc_sinh(0, "trung_binh", lop, "hat/2", 0.85)
    assert a == b
    assert a.boc_tham != c.boc_tham


def test_student_is_the_same_across_classes_with_different_ids():
    """Ba lớp nhiễu có nội dung giống nhau nhưng mã khác: cùng em phải chọn cùng vị trí bài, cùng di sản yếu, cùng số ngẫu nhiên."""
    lop_a = lop_mau()
    lop_b = [dg.BaiHoc(b.id + 1000, b.quiz_id + 1000, b.so_cau_di_san, b.do_kho, b.han_dong) for b in lop_mau()]
    a = dg.tao_hoc_sinh(3, "yeu", lop_a, "hat/x", 0.85)
    b = dg.tao_hoc_sinh(3, "yeu", lop_b, "hat/x", 0.85)
    assert [i + 1000 for i in a.bai_da_lam] == list(b.bai_da_lam)
    assert a.di_san_yeu == b.di_san_yeu
    assert a.boc_tham == b.boc_tham


@pytest.mark.parametrize("nhom", ["yeu", "trung_binh", "vung"])
def test_weak_heritages_follow_group_and_come_from_seen_ones(nhom):
    lop = lop_mau()
    theo_id = {b.id: b for b in lop}
    for chi_so in range(40):
        hs = dg.tao_hoc_sinh(chi_so, nhom, lop, f"hat/{chi_so}", 0.85)
        assert len(hs.bai_da_lam) == 2 and len(set(hs.bai_da_lam)) == 2
        gap = {h for i in hs.bai_da_lam for h in theo_id[i].di_san}
        assert hs.di_san_yeu <= gap
        if nhom == "yeu":
            assert len(hs.di_san_yeu) == max(1, math.ceil(0.85 * len(gap)))
        elif nhom == "trung_binh":
            assert len(hs.di_san_yeu) == 1
        else:
            assert not hs.di_san_yeu
        assert [len(u) for u in hs.boc_tham] == [theo_id[i].so_cau for i in hs.bai_da_lam]


def test_student_without_attempts_has_nothing():
    hs = dg.tao_hoc_sinh(0, "chua_lam", lop_mau(), "hat", 0.85)
    assert hs.bai_da_lam == () and not hs.di_san_yeu and hs.boc_tham == ()


def test_unknown_group_is_rejected():
    with pytest.raises(ValueError):
        dg.tao_hoc_sinh(0, "la", lop_mau(), "hat", 0.85)


def test_group_split_has_exact_total_and_is_seeded():
    ty_le = {"yeu": 0.2, "trung_binh": 0.55, "vung": 0.25}
    a = dg.chia_nhom(60, ty_le, random.Random(5))
    b = dg.chia_nhom(60, ty_le, random.Random(5))
    assert a == b and len(a) == 60
    assert (a.count("yeu"), a.count("trung_binh"), a.count("vung")) == (12, 33, 15)
    assert len(dg.chia_nhom(7, ty_le, random.Random(1))) == 7


def test_answers_for_a_whole_quiz_follow_the_weak_set_and_noise():
    hs = dg.HocSinhAo(0, "trung_binh", (1,), frozenset({10}), ((0.0, 0.9, 0.0, 0.9, 0.05, 0.05, 0.5, 0.5),))
    cau = [(10, dg.KIEU_4_PHUONG_AN), (10, dg.KIEU_4_PHUONG_AN), (10, dg.KIEU_DUNG_SAI), (10, dg.KIEU_DUNG_SAI),
           (11, dg.KIEU_4_PHUONG_AN), (11, dg.KIEU_4_PHUONG_AN), (11, dg.KIEU_DUNG_SAI), (11, dg.KIEU_DUNG_SAI)]
    ket_qua = dg.tra_loi_ca_bai(hs, 0, cau, 0.10, XAC_SUAT)
    # di sản 10 (yếu): u < xác suất đoán; di sản 11 (vững): sai khi u < 0,10
    assert ket_qua == [True, False, True, False, False, False, True, True]
    with pytest.raises(ValueError):
        dg.tra_loi_ca_bai(hs, 0, cau[:3], 0.1, XAC_SUAT)


def test_expected_accuracy_and_ability_zone():
    hs = dg.HocSinhAo(0, "trung_binh", (1,), frozenset({10}), ())
    cau = {1: [(10, dg.KIEU_DUNG_SAI), (11, dg.KIEU_4_PHUONG_AN), (11, dg.KIEU_4_PHUONG_AN), (11, dg.KIEU_4_PHUONG_AN)]}
    assert dg.ky_vong_ti_le_dung(hs, cau, 0.20, XAC_SUAT) == pytest.approx((0.5 + 3 * 0.8) / 4)
    assert dg.ky_vong_ti_le_dung(dg.HocSinhAo(1, "chua_lam", (), frozenset(), ()), cau, 0.2, XAC_SUAT) is None
    assert dg.vung_nang_luc(0.49) == "yeu"
    assert dg.vung_nang_luc(0.5) == "trung_binh"
    assert dg.vung_nang_luc(0.8) == "vung"
    assert dg.vung_nang_luc(0.8 - 1e-12) == "vung"  # sai số số học ở đúng ngưỡng 80% (mức nhiễu 20%)
    assert dg.vung_nang_luc(None) == "chua_lam"


# ---- đường cơ sở ----

def test_baseline_unattempted_quizzes_by_close_date():
    ds = dg.quiz_chua_lam_theo_han_dong(lop_mau(), [2])
    assert [b.id for b in ds] == [3, 4, 1]  # bài 2 (hạn 21) đã làm; còn lại theo hạn 24, 27, 30


def test_baseline_newest_quizzes_skip_attempted_and_newest_lessons_do_not():
    assert [b.id for b in dg.quiz_moi_nhat(lop_mau(), [5])] == [4, 3, 2]
    assert [b.id for b in dg.bai_hoc_moi_nhat(lop_mau())] == [5, 4, 3]


def test_baseline_most_questions_breaks_ties_by_smaller_id():
    lop = [dg.BaiHoc(1, 101, ((20, 6), (21, 2)), "EASY", 1), dg.BaiHoc(2, 102, ((21, 6), (22, 2), (23, 2)), "EASY", 2)]
    assert dg.di_san_nhieu_cau_nhat(lop, [1, 2]) == [21, 20, 22]  # 21 có 8 câu, 20 có 6, rồi 22 và 23 cùng 2 câu: mã nhỏ trước
    assert dg.di_san_nhieu_cau_nhat(lop, []) == []
    assert dg.di_san_cua_quiz_da_lam(lop, [2]) == [21, 22, 23]


def test_lessons_of_goi_y_put_review_first_dedupe_and_cap_at_three():
    g = dg.GoiY(quiz_ids=(), bai_on_lai_ids=(4, 2), bai_moi_ids=(2, 5, 1), di_san_nen_on_ids=())
    assert g.bai_hoc_ids() == (4, 2, 5)


# ---- trúng di sản yếu so với đường cơ sở ----

def lop_tam_bai(han_bai_2: int = 21) -> list[dg.BaiHoc]:
    """Tám bài: năm bài của lop_mau (hạn đóng bài 2 đổi được) cộng ba bài mới nhất về các di sản khác."""
    cu = [dg.BaiHoc(b.id, b.quiz_id, b.so_cau_di_san, b.do_kho, han_bai_2 if b.id == 2 else b.han_dong) for b in lop_mau()]
    return [*cu, dg.BaiHoc(6, 106, ((15, 4), (16, 4)), "EASY", 40), dg.BaiHoc(7, 107, ((16, 4), (17, 4)), "EASY", 41),
            dg.BaiHoc(8, 108, ((17, 4), (18, 4)), "EASY", 42)]


def test_hit_evaluation_service_hits_where_all_baselines_miss():
    lop = lop_tam_bai(han_bai_2=99)
    # Em đã làm bài 1 và 5 (di sản 10, 11, 14), di sản yếu là 11. Chưa làm: 2, 3, 4, 6, 7, 8; chỉ bài 2 chứa 11.
    hs = dg.HocSinhAo(0, "trung_binh", (1, 5), frozenset({11}), ())
    goi_y = dg.GoiY(quiz_ids=(102, 103, 104), bai_on_lai_ids=(1,), bai_moi_ids=(2, 3), di_san_nen_on_ids=(11,))
    kq = dg.danh_gia_hit_hoc_sinh(hs, lop, goi_y)
    assert kq["dich_vu"] == {"quiz": True, "bai_hoc": True, "chung": True}
    # Theo hạn đóng: 3 (24), 4 (27), 6 (40), bài 2 đóng muộn nhất nên trượt; bài mới nhất: 8, 7, 6 đều không có di sản 11.
    assert kq["quiz_chua_lam_theo_han"] == {"quiz": False, "bai_hoc": False, "chung": False}
    assert kq["bai_moi_nhat"] == {"quiz": False, "bai_hoc": False, "chung": False}
    # Ngẫu nhiên: 6 quiz chưa làm có 1 quiz trúng; 8 bài học có 2 bài trúng (bài 1 và 2).
    p_quiz = 1 - math.comb(5, 3) / math.comb(6, 3)
    p_bai = 1 - math.comb(6, 3) / math.comb(8, 3)
    assert kq["bai_ngau_nhien"]["quiz"] == pytest.approx(p_quiz)
    assert kq["bai_ngau_nhien"]["bai_hoc"] == pytest.approx(p_bai)
    assert kq["bai_ngau_nhien"]["chung"] == pytest.approx(1 - (1 - p_quiz) * (1 - p_bai))


def test_baselines_can_hit_when_the_weak_heritage_is_in_the_newest_or_earliest_closing_quiz():
    lop = lop_tam_bai(han_bai_2=21)
    hs = dg.HocSinhAo(0, "trung_binh", (1, 5), frozenset({11}), ())
    goi_y = dg.GoiY(quiz_ids=(), bai_on_lai_ids=(), bai_moi_ids=(), di_san_nen_on_ids=())
    kq = dg.danh_gia_hit_hoc_sinh(hs, lop, goi_y)
    assert kq["quiz_chua_lam_theo_han"]["quiz"] is True  # bài 2 đóng sớm nhất (21)
    assert kq["dich_vu"] == {"quiz": False, "bai_hoc": False, "chung": False}  # gợi ý rỗng thì không trúng


def test_review_part_service_and_baselines():
    lop = lop_tam_bai()
    hs = dg.HocSinhAo(0, "trung_binh", (1, 3), frozenset({13}), ())  # đã gặp 10, 11, 12, 13, mỗi di sản 4 câu: hòa hết
    goi_y = dg.GoiY(quiz_ids=(), bai_on_lai_ids=(), bai_moi_ids=(), di_san_nen_on_ids=(13, 11))
    kq = dg.danh_gia_hit_hoc_sinh(hs, lop, goi_y)
    assert kq["nen_on"]["dich_vu"] is True
    assert kq["nen_on"]["nhieu_cau_nhat"] is False  # hòa hết nên mã nhỏ trước: 10, 11, 12
    assert kq["nen_on"]["di_san_ngau_nhien"] == pytest.approx(dg.xac_suat_trung_ngau_nhien(4, 1))


# ---- độ khó khớp ----

def test_acceptable_difficulty_by_zone_and_by_level_default():
    assert dg.muc_kho_chap_nhan("yeu", 2) == {"EASY", "MEDIUM"}
    assert dg.muc_kho_chap_nhan("vung", 3) == {"HARD"}
    assert dg.muc_kho_chap_nhan("chua_lam", 1) == {"EASY"}
    assert dg.muc_kho_chap_nhan("chua_lam", 2) == {"MEDIUM"}
    assert dg.muc_kho_chap_nhan("chua_lam", 3) == {"MEDIUM"}


def test_difficulty_match_service_vs_newest_vs_random_expectation():
    lop = lop_mau()  # độ khó theo mã bài: E, M, H, E, M
    hs = dg.HocSinhAo(0, "chua_lam", (), frozenset(), ())
    goi_y = dg.GoiY(quiz_ids=(101, 104, 102), bai_on_lai_ids=(), bai_moi_ids=(1, 4, 2), di_san_nen_on_ids=())
    kq = dg.do_kho_khop_hoc_sinh(hs, 1, lop, goi_y, "chua_lam")  # cấp 1: mức mặc định Dễ
    assert kq["quiz_dich_vu"] == (2.0, 3)    # 101 và 104 là Dễ
    assert kq["bai_hoc_dich_vu"] == (2.0, 3)
    assert kq["bai_moi_dich_vu"] == (2.0, 3)
    assert kq["quiz_moi_nhat"] == (1.0, 3)   # ba quiz mới nhất: 5 (M), 4 (E), 3 (H)
    assert kq["bai_hoc_moi_nhat"] == (1.0, 3)
    assert kq["quiz_ngau_nhien"] == (pytest.approx(2 / 5 * 3), 3)
    assert dg.gop_ty_le([(2.0, 3), (1.0, 3)]) == (pytest.approx(0.5), 6)
    assert dg.gop_ty_le([]) == (0.0, 0)


# ---- đúng lớp ----

def test_class_membership_detects_items_of_other_classes():
    lop = lop_mau()
    sach = dg.GoiY(quiz_ids=(101, 102), bai_on_lai_ids=(1,), bai_moi_ids=(2,), di_san_nen_on_ids=())
    assert dg.thuoc_lop(sach, lop) == (4, 4)
    lan = dg.GoiY(quiz_ids=(101, 999), bai_on_lai_ids=(888,), bai_moi_ids=(2,), di_san_nen_on_ids=())
    assert dg.thuoc_lop(lan, lop) == (2, 4)


def test_summary_counter():
    t = dg.TongHop(so_em=4)
    t.cong("a", 1)
    t.cong("a", 2)
    assert t.ty_le("a") == pytest.approx(0.75)
    assert dg.TongHop().ty_le("a") == 0.0
