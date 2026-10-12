"""Dựng câu hỏi mẫu cho bộ đánh giá (scripts/danh-gia/cau_hoi_mau.py): đúng quy tắc cấu trúc của backend ở từng cấp, và dựng câu trả lời đúng/sai theo đề. Không mạng."""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "danh-gia"))

import danh_gia_chung as dg
from cau_hoi_mau import SO_CAU_MOI_DI_SAN, DiSan, NhanHienThi, dap_an_gui_len, tao_cau_hoi_cho_di_san

TINH = tuple(f"Tỉnh số {i}" for i in range(1, 12))
NHAN = NhanHienThi(
    loai={"TANGIBLE": "Di sản vật thể", "INTANGIBLE": "Di sản phi vật thể", "NATURAL": "Di sản thiên nhiên", "DOCUMENTARY": "Di sản tư liệu", "MIXED": "Di sản hỗn hợp"},
    cap={"UNESCO": "UNESCO", "NATIONAL_SPECIAL": "Quốc gia đặc biệt", "NATIONAL": "Quốc gia", "PROVINCIAL": "Cấp tỉnh", "NONE": "Chưa xếp hạng"},
    tinh=TINH,
)


def anh(n: int) -> tuple[tuple[str, str], ...]:
    return tuple((f"https://anh.example/{i}.jpg", f"Hình số {i} của di sản, chú thích đủ dài để thử cắt nhãn cho vừa năm mươi ký tự") for i in range(n))


def tat_ca(so_anh: int = 4) -> list[DiSan]:
    ra = []
    for i in range(1, 9):
        ra.append(DiSan(i, f"Di sản thứ {i}", i, TINH[i - 1], "Bắc" if i < 4 else ("Trung" if i < 7 else "Nam"),
                        ["TANGIBLE", "INTANGIBLE", "NATURAL", "DOCUMENTARY", "MIXED"][i % 5], ["UNESCO", "NATIONAL_SPECIAL"][i % 2], 2000 + i, anh(so_anh)))
    return ra


@pytest.mark.parametrize("cap", [1, 2, 3])
@pytest.mark.parametrize("lan", [0, 1])
def test_each_heritage_gets_four_valid_questions_of_the_levels_types(cap, lan):
    ds = tat_ca()
    for d in ds:
        cau = tao_cau_hoi_cho_di_san(cap, d, ds, NHAN, lan, "MEDIUM", random.Random(d.id * 10 + lan))
        assert len(cau) == SO_CAU_MOI_DI_SAN
        loai = [c.loai for c in cau]
        if cap == 1:
            assert loai == ["IMAGE_CHOICE", "TRUE_FALSE", "IMAGE_CHOICE", "TRUE_FALSE"]
        elif cap == 2:
            assert loai == ["SINGLE_CHOICE", "TRUE_FALSE", "SINGLE_CHOICE", "TRUE_FALSE"]
        else:
            assert loai == ["SINGLE_CHOICE", "MULTI_TRUE_FALSE", "SINGLE_CHOICE", "MULTI_TRUE_FALSE"]
        for c in cau:
            p = c.payload
            assert c.di_san_id == d.id == p["heritageId"]
            assert 10 <= len(p["content"]) <= 1000 if "content" in p else True
            assert p["levelMin"] == p["levelMax"] == cap
            assert p["difficultyLevel"] == "MEDIUM" and p["explanation"]


@pytest.mark.parametrize("cap", [2, 3])
def test_single_choice_has_four_distinct_options_with_exactly_one_correct(cap):
    ds = tat_ca()
    for d in ds:
        for lan in (0, 1):
            for c in tao_cau_hoi_cho_di_san(cap, d, ds, NHAN, lan, "EASY", random.Random(d.id + lan)):
                if c.loai != "SINGLE_CHOICE":
                    continue
                opt = c.payload["options"]
                assert len(opt) == 4 and len({o["content"] for o in opt}) == 4
                assert sum(o["isCorrect"] for o in opt) == 1
                assert c.kieu == dg.KIEU_4_PHUONG_AN
                assert c.dap_an["dung"] != c.dap_an["sai"]


def test_the_two_appearances_of_a_heritage_use_different_question_templates():
    ds = tat_ca()
    d = ds[0]
    dau = {c.payload["content"] for c in tao_cau_hoi_cho_di_san(2, d, ds, NHAN, 0, "EASY", random.Random(1))}
    sau = {c.payload["content"] for c in tao_cau_hoi_cho_di_san(2, d, ds, NHAN, 1, "EASY", random.Random(1))}
    assert not dau & sau


def test_level_one_image_choice_uses_distinct_cards_with_short_unique_labels():
    ds = tat_ca(so_anh=4)
    for c in tao_cau_hoi_cho_di_san(1, ds[0], ds, NHAN, 0, "EASY", random.Random(3)):
        if c.loai == "IMAGE_CHOICE":
            the = c.payload["options"]
            assert len(the) == 4 and len({t["imageUrl"] for t in the}) == 4
            assert len({t["content"] for t in the}) == 4 and all(len(t["content"]) <= 50 for t in the)
            assert sum(t["isCorrect"] for t in the) == 1
            assert c.kieu == dg.KIEU_4_PHUONG_AN
        else:
            assert c.payload["imageUrl"]  # đúng/sai ở cấp 1 bắt buộc có hình
            assert c.kieu == dg.KIEU_DUNG_SAI


def test_three_images_make_three_card_questions_and_two_images_fall_back_to_true_false():
    ba = tat_ca(so_anh=3)
    cau = tao_cau_hoi_cho_di_san(1, ba[0], ba, NHAN, 0, "EASY", random.Random(3))
    assert [c.kieu for c in cau if c.loai == "IMAGE_CHOICE"] == [dg.KIEU_3_PHUONG_AN, dg.KIEU_3_PHUONG_AN]
    hai = tat_ca(so_anh=2)
    cau = tao_cau_hoi_cho_di_san(1, hai[0], hai, NHAN, 0, "EASY", random.Random(3))
    assert [c.loai for c in cau] == ["TRUE_FALSE"] * 4 and all(c.payload["imageUrl"] for c in cau)


def test_level_one_without_images_is_rejected():
    ds = tat_ca(so_anh=0)
    with pytest.raises(ValueError):
        tao_cau_hoi_cho_di_san(1, ds[0], ds, NHAN, 0, "EASY", random.Random(1))
    with pytest.raises(ValueError):
        tao_cau_hoi_cho_di_san(4, ds[0], ds, NHAN, 0, "EASY", random.Random(1))


def test_level_three_statements_are_mixed_and_within_length_limits():
    ds = tat_ca()
    for d in ds:
        for c in tao_cau_hoi_cho_di_san(3, d, ds, NHAN, 1, "HARD", random.Random(d.id)):
            if c.loai == "MULTI_TRUE_FALSE":
                menh_de = c.payload["statements"]
                assert len(menh_de) == 3
                assert 0 < sum(m["isTrue"] for m in menh_de) < 3  # không để mọi mệnh đề cùng đúng hoặc cùng sai
                assert all(10 <= len(m["text"]) <= 500 for m in menh_de)
                assert c.kieu == dg.KIEU_DUNG_SAI


def test_heritage_without_year_still_gets_four_questions():
    ds = tat_ca()
    khong_nam = DiSan(99, "Di sản chưa rõ năm", 1, TINH[0], "Bắc", "TANGIBLE", "UNESCO", None, anh(4))
    for cap in (1, 2, 3):
        for lan in (0, 1):
            assert len(tao_cau_hoi_cho_di_san(cap, khong_nam, [*ds, khong_nam], NHAN, lan, "EASY", random.Random(5))) == 4


def test_same_seed_gives_same_questions():
    ds = tat_ca()
    a = tao_cau_hoi_cho_di_san(2, ds[2], ds, NHAN, 0, "EASY", random.Random(9))
    b = tao_cau_hoi_cho_di_san(2, ds[2], ds, NHAN, 0, "EASY", random.Random(9))
    assert [c.payload for c in a] == [c.payload for c in b]


# ---- dựng câu trả lời theo đề em thấy ----

def test_answer_builder_picks_the_right_or_a_wrong_position_in_the_shown_order():
    ds = tat_ca()
    for cap in (1, 2, 3):
        for c in tao_cau_hoi_cho_di_san(cap, ds[1], ds, NHAN, 0, "EASY", random.Random(cap)):
            if c.loai == "SINGLE_CHOICE" or c.loai == "IMAGE_CHOICE":
                hien = {"options": [{"content": o["content"]} for o in reversed(c.payload["options"])]}  # em thấy thứ tự đảo
                dung = dap_an_gui_len(c, hien, True)["selectedIndex"]
                sai = dap_an_gui_len(c, hien, False)["selectedIndex"]
                assert hien["options"][dung]["content"] == c.dap_an["dung"]
                assert hien["options"][sai]["content"] != c.dap_an["dung"]
            elif c.loai == "TRUE_FALSE":
                hien = {"options": [{"content": "Đúng"}, {"content": "Sai"}]}
                dung = dap_an_gui_len(c, hien, True)["selectedIndex"]
                sai = dap_an_gui_len(c, hien, False)["selectedIndex"]
                assert (hien["options"][dung]["content"] == "Đúng") == c.payload["answerIsTrue"]
                assert dung != sai
            else:
                hien = {"statements": [{"text": s["text"]} for s in reversed(c.payload["statements"])]}
                dung = dap_an_gui_len(c, hien, True)["statements"]
                sai = dap_an_gui_len(c, hien, False)["statements"]
                chuan = [s["isTrue"] for s in reversed(c.payload["statements"])]
                assert dung == chuan and sai == [not x for x in chuan]


def test_answer_builder_rejects_unknown_type():
    ds = tat_ca()
    c = tao_cau_hoi_cho_di_san(2, ds[0], ds, NHAN, 0, "EASY", random.Random(1))[0]
    c.loai = "ORDERING"
    with pytest.raises(ValueError):
        dap_an_gui_len(c, {}, True)
