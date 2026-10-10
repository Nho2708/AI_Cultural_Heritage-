"""rank-related: gợi ý content-based bằng TF-IDF + cosine, không gọi mô hình ngôn ngữ."""
from __future__ import annotations

import pytest

from .conftest import FakeLlm, ok

URL = "/v1/rank-related"


def feat(hid, name, type_="TANGIBLE", province=1, region="Bắc", level="NATIONAL", year_from=None, year_to=None, text=None):
    return {"id": hid, "name": name, "type": type_, "provinceId": province, "region": region, "level": level,
            "yearFrom": year_from, "yearTo": year_to, "text": text if text is not None else name}


def request(candidates=None, references=None):
    return {
        "studentId": 7, "level": 2, "targetDifficulty": "MEDIUM",
        "references": references or [{"heritage": feat(1, "Hoàng thành Thăng Long", text="Hoàng thành Thăng Long kinh đô thời Lý Trần Lê tại Hà Nội", year_from=1010, year_to=1800), "weight": 1.0}],
        "candidates": candidates or [
            feat(2, "Văn Miếu Quốc Tử Giám", text="Văn Miếu Quốc Tử Giám trường học thời Lý tại Hà Nội", year_from=1070, year_to=1900),
            feat(3, "Ca trù", type_="INTANGIBLE", province=40, region="Nam", level="PROVINCIAL", text="Nghệ thuật hát ca trù"),
            feat(4, "Vịnh Hạ Long", type_="NATURAL", province=1, region="Bắc", level="UNESCO", text="Cảnh quan biển đảo đá vôi"),
        ],
    }


async def test_ranking_orders_by_similarity_and_leaves_out_unrelated(make_client):
    llm = FakeLlm(ok({}))
    r = await make_client(llm).post(URL, json=request())
    assert r.status_code == 200, r.text
    related = r.json()["related"]
    assert [x["heritageId"] for x in related] == [2, 4]            # Ca trù khác loại, khác tỉnh, khác vùng: không có điểm chung
    assert related[0]["score"] > related[1]["score"] > 0
    assert related[0]["reason"].startswith("Cùng loại, cùng tỉnh") and "với Hoàng thành Thăng Long" in related[0]["reason"]
    assert llm.calls == []                                          # không gọi mô hình ngôn ngữ


async def test_response_shape_is_exactly_what_the_backend_reads(make_client):
    r = await make_client(FakeLlm(ok({}))).post(URL, json=request())
    body = r.json()
    assert list(body) == ["related"]
    assert set(body["related"][0]) == {"heritageId", "score", "reason"}


async def test_text_similarity_adds_to_score(make_client):
    near = feat(2, "Thành nhà Hồ", province=2, region="Trung", level="NONE", type_="INTANGIBLE",
                text="Hoàng thành Thăng Long kinh đô thời Lý Trần Lê tại Hà Nội")
    far = feat(3, "Núi Bà Đen", province=2, region="Trung", level="NONE", type_="INTANGIBLE", text="Ngọn núi cao ở miền Nam")
    r = await make_client(FakeLlm(ok({}))).post(URL, json=request(candidates=[near, far]))
    related = r.json()["related"]
    assert [x["heritageId"] for x in related] == [2]
    assert related[0]["reason"].startswith("Nội dung gần nhau")


async def test_weights_scale_scores_and_best_reference_wins(make_client):
    refs = [
        {"heritage": feat(1, "Hoàng thành Thăng Long", type_="TANGIBLE", province=1), "weight": 1.0},
        {"heritage": feat(5, "Ca trù", type_="INTANGIBLE", province=40, region="Nam", level="PROVINCIAL", text="Ca trù"), "weight": 3.0},
    ]
    cands = [feat(2, "Hát xoan", type_="INTANGIBLE", province=40, region="Nam", level="PROVINCIAL", text="Hát xoan")]
    r = await make_client(FakeLlm(ok({}))).post(URL, json=request(candidates=cands, references=refs))
    related = r.json()["related"][0]
    assert related["heritageId"] == 2 and "với Ca trù" in related["reason"]
    assert related["score"] == pytest.approx(3 * (3 + 2 + 1), abs=0.01)   # cùng loại 3 + cùng tỉnh 2 + cùng cấp xếp hạng 1, nhân 3


async def test_era_overlap_region_and_level_factors(make_client):
    ref = [{"heritage": feat(1, "A", type_="MIXED", province=1, region="Bắc", level="NATIONAL", year_from=100, year_to=200, text="a"), "weight": 1.0}]
    cands = [
        feat(2, "B", type_="NATURAL", province=9, region="Bắc", level="NATIONAL", year_from=150, year_to=300, text="b"),   # vùng + cấp + thời kỳ
        feat(3, "C", type_="NATURAL", province=9, region="Nam", level="NONE", year_from=500, year_to=600, text="c"),      # không gì chung
        feat(4, "D", type_="NATURAL", province=9, region="Nam", level="NONE", year_from=200, year_to=None, text="d"),     # chỉ thời kỳ (chạm đầu mút)
    ]
    r = await make_client(FakeLlm(ok({}))).post(URL, json=request(candidates=cands, references=ref))
    related = {x["heritageId"]: x for x in r.json()["related"]}
    assert set(related) == {2, 4}
    assert related[2]["score"] == pytest.approx(3.0) and related[4]["score"] == pytest.approx(1.0)
    assert related[2]["reason"] == "Cùng vùng, cùng cấp xếp hạng với A"
    assert related[4]["reason"] == "Cùng thời kỳ với A"


async def test_candidates_that_are_references_are_skipped_and_ties_break_by_id(make_client):
    cands = [feat(1, "Hoàng thành Thăng Long"), feat(9, "X"), feat(8, "Y")]
    r = await make_client(FakeLlm(ok({}))).post(URL, json=request(candidates=cands))
    assert [x["heritageId"] for x in r.json()["related"]] == [8, 9]


@pytest.mark.parametrize("body", [{"references": [], "candidates": [{"id": 1}]}, {"references": [{"heritage": {"id": 1}, "weight": 1}], "candidates": []}, {}])
async def test_empty_inputs_give_empty_result(make_client, body):
    r = await make_client(FakeLlm(ok({}))).post(URL, json=body)
    assert r.status_code == 200 and r.json() == {"related": []}


async def test_texts_without_vocabulary_do_not_crash(make_client):
    refs = [{"heritage": feat(1, "A", text="và của"), "weight": 1.0}]
    cands = [feat(2, "B", text="là có")]
    r = await make_client(FakeLlm(ok({}))).post(URL, json=request(candidates=cands, references=refs))
    assert r.status_code == 200 and r.json()["related"][0]["heritageId"] == 2   # vẫn cùng loại, tỉnh...


async def test_missing_optional_fields_and_zero_weight(make_client):
    body = {"references": [{"heritage": {"id": 1, "name": "A"}, "weight": 0}, {"heritage": {"id": 2}}],
            "candidates": [{"id": 3, "name": "B"}, {"id": 4, "type": "TANGIBLE"}]}
    r = await make_client(FakeLlm(ok({}))).post(URL, json=body)
    assert r.status_code == 200 and r.json() == {"related": []}


async def test_large_candidate_list_is_fast(make_client):
    import time

    cands = [feat(i, f"Di sản {i}", province=i % 63, text=f"di sản số {i} tại tỉnh {i % 63} thời kỳ lịch sử") for i in range(2, 2002)]
    started = time.perf_counter()
    r = await make_client(FakeLlm(ok({}))).post(URL, json=request(candidates=cands))
    assert r.status_code == 200 and len(r.json()["related"]) >= 1
    assert time.perf_counter() - started < 2.0   # backend chờ tối đa 2 giây


async def test_too_many_candidates_is_422(make_client):
    body = request(candidates=[feat(i, "x") for i in range(2, 5100)])
    r = await make_client(FakeLlm(ok({}))).post(URL, json=body)
    assert r.status_code == 422
