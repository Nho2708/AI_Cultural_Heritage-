"""Sinh câu hỏi: kiểm đúng quy tắc cấu trúc của từng dạng và cấp, gọi lại một lần, nhận ít câu hơn khi chỉ một phần đạt."""
from __future__ import annotations

import copy

import pytest

from app.validators.questions import count_markers, validate_question

from .conftest import FakeLlm, ok
from .factories import heritage_input, question_item, questions_request

URL = "/v1/generate-questions"
LEVEL_TYPES = {
    1: ["TRUE_FALSE", "IMAGE_CHOICE", "MATCHING", "ORDERING"],
    2: ["SINGLE_CHOICE", "TRUE_FALSE", "ORDERING", "FILL_BLANK"],
    3: ["SINGLE_CHOICE", "MULTI_TRUE_FALSE", "SOURCE_READING"],
}
CASES = [(lv, t) for lv, ts in LEVEL_TYPES.items() for t in ts]


def libs(req: dict) -> dict[int, set[str]]:
    return {h["heritageId"]: {i["url"] for i in h["images"]} for h in req["heritages"]}


def check(item: dict, level: int, req: dict, types: set[str] | None = None):
    return validate_question(item, 0, grade_level=level, allowed_types=types or {item["questionType"]}, libraries=libs(req))


@pytest.mark.parametrize("level,qtype", CASES)
async def test_each_type_valid_at_its_levels(make_client, level, qtype):
    req = questions_request(level, [qtype], count=2)
    llm = FakeLlm(ok({"questions": [question_item(qtype, level, req, 0), question_item(qtype, level, req, 1)]}, 3000, 900))
    r = await make_client(llm).post(URL, json=req)

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"questions", "model", "usage"} and body["usage"] == {"inputTokens": 3000, "outputTokens": 900}
    assert len(body["questions"]) == 2
    for q in body["questions"]:
        assert q["questionType"] == qtype and q["heritageId"] == 1
        assert set(q) == {"heritageId", "questionType", "content", "explanation", "imageUrl", "passage", "passageSource",
                          "answerIsTrue", "options", "pairs", "steps", "blanks", "distractors", "statements"}
    assert len(llm.calls) == 1


def test_schema_is_specific_to_requested_types_and_level():
    from app.prompts import questions as prompts

    sc = prompts.schema(["SINGLE_CHOICE", "ORDERING"], 2)
    variants = sc["properties"]["questions"]["items"]["anyOf"]
    assert [v["properties"]["questionType"]["enum"] for v in variants] == [["SINGLE_CHOICE"], ["ORDERING"]]
    one = prompts.schema(["SINGLE_CHOICE"], 3)["properties"]["questions"]["items"]
    assert "anyOf" not in one and "options" in one["properties"] and "steps" not in one["properties"]
    tf1 = prompts.item_schema("TRUE_FALSE", 1)
    tf2 = prompts.item_schema("TRUE_FALSE", 2)
    assert tf1["properties"]["imageUrl"] == {"type": "string"} and "anyOf" in tf2["properties"]["imageUrl"]
    assert all(v["additionalProperties"] is False for v in variants)


@pytest.mark.parametrize(
    "level,qtype,mutate,fragment",
    [
        (2, "SINGLE_CHOICE", lambda q: q["options"].pop(), "đúng 4"),
        (2, "SINGLE_CHOICE", lambda q: q["options"][1].update(isCorrect=True), "đúng một"),
        (2, "SINGLE_CHOICE", lambda q: q["options"][1].update(content="lý thánh   tông"), "trùng"),
        (2, "SINGLE_CHOICE", lambda q: q.update(explanation=""), "explanation"),
        (2, "SINGLE_CHOICE", lambda q: q.update(content="Ngắn"), "10 đến 1000"),
        (2, "SINGLE_CHOICE", lambda q: q.update(content="What is the capital city of the old Vietnamese empire?"), "tiếng Việt"),
        (1, "TRUE_FALSE", lambda q: q.update(imageUrl=None), "imageUrl"),
        (1, "TRUE_FALSE", lambda q: q.update(imageUrl="/media/khong-co.jpg"), "imageUrl"),
        (2, "TRUE_FALSE", lambda q: q.update(answerIsTrue=None), "answerIsTrue"),
        (1, "IMAGE_CHOICE", lambda q: q["options"][1].update(imageUrl=q["options"][0]["imageUrl"]), "dùng lại hình"),
        (1, "IMAGE_CHOICE", lambda q: q["options"][0].update(imageUrl="/media/ngoai.jpg"), "imageUrl"),
        (1, "IMAGE_CHOICE", lambda q: q["options"][0].update(content="x" * 60), "1 đến 50"),
        (1, "IMAGE_CHOICE", lambda q: q["options"].pop(0) and q["options"].pop(0), "3 đến 4"),
        (1, "MATCHING", lambda q: q["pairs"].pop(), "3 đến 5"),
        (1, "MATCHING", lambda q: q["pairs"][1].update(right="Điện Kính Thiên"), "trùng"),
        (1, "MATCHING", lambda q: q["pairs"][0].update(left=None), "vế trái"),
        (1, "ORDERING", lambda q: q["steps"].extend(["Nhà Nguyễn thay đổi", "Thời nay"]), "3 đến 4"),
        (2, "ORDERING", lambda q: q["steps"].extend(["a b", "c d", "e f"]), "3 đến 6"),
        (2, "ORDERING", lambda q: q["steps"].__setitem__(1, q["steps"][0]), "trùng"),
        (2, "FILL_BLANK", lambda q: q.update(content="Hoàng thành Thăng Long được xây dựng từ thời nhà Lý."), "chỗ trống"),
        (2, "FILL_BLANK", lambda q: q["blanks"].pop(), "đúng 2 nhóm"),
        (2, "FILL_BLANK", lambda q: q.update(distractors=["Lý"]), "trùng"),
        (2, "FILL_BLANK", lambda q: q.update(distractors=["a", "b", "c", "d", "e", "f", "g"]), "kho từ"),
        (3, "MULTI_TRUE_FALSE", lambda q: [s.update(isTrue=True) for s in q["statements"]], "cùng Đúng"),
        (3, "MULTI_TRUE_FALSE", lambda q: q["statements"][0].update(text="Ngắn"), "10 đến 500"),
        (3, "MULTI_TRUE_FALSE", lambda q: q["statements"].pop() and q["statements"].pop(), "3 đến 5"),
        (3, "SOURCE_READING", lambda q: q.update(passage=" ".join(["từ"] * 160)), "150 từ"),
        (3, "SOURCE_READING", lambda q: q.update(passageSource=None), "passageSource"),
        (3, "SOURCE_READING", lambda q: q["options"][0].update(isCorrect=False), "đúng một"),
    ],
)
def test_structure_rules_per_type(level, qtype, mutate, fragment):
    req = questions_request(level, [qtype])
    item = question_item(qtype, level, req, 0)
    assert check(copy.deepcopy(item), level, req)[0] is not None  # bản gốc hợp lệ
    mutate(item)
    question, errors = check(item, level, req)
    assert question is None
    assert any(fragment in e for e in errors), errors


def test_fill_blank_marker_counting_and_long_runs():
    assert count_markers("a ___ b ___ c") == 2
    assert count_markers("a _____ b") == 1
    assert count_markers("a __ b") == 0
    assert count_markers("___") == 1


def test_fill_blank_word_bank_is_optional_and_normalized():
    req = questions_request(2, ["FILL_BLANK"])
    item = question_item("FILL_BLANK", 2, req)
    item["distractors"] = []
    q, _errors = check(item, 2, req)
    assert q is not None and q.distractors is None
    item = question_item("FILL_BLANK", 2, req)
    q, _ = check(item, 2, req)
    assert q.distractors == ["Trần", "Huế"] and q.blanks[1].accepted == ["Hà Nội", "Hanoi"]


def test_wrong_type_unknown_heritage_and_foreign_fields():
    req = questions_request(2, ["SINGLE_CHOICE"])
    item = question_item("TRUE_FALSE", 2, req)
    assert "không nằm trong các dạng" in check(item, 2, req, {"SINGLE_CHOICE"})[1][0]
    item = question_item("SINGLE_CHOICE", 2, req)
    item["heritageId"] = 99
    assert "heritageId" in check(item, 2, req)[1][0]
    item = question_item("SINGLE_CHOICE", 2, req)
    item["steps"] = ["a", "b", "c"]   # trường của dạng khác bị bỏ qua
    q, _ = check(item, 2, req)
    assert q is not None and q.steps is None


def test_image_must_belong_to_the_heritage_it_is_attached_to():
    req = questions_request(1, ["TRUE_FALSE"])
    req["heritages"].append(heritage_input(2))
    item = question_item("TRUE_FALSE", 1, req)
    item["imageUrl"] = "/media/h2-1.jpg"  # ảnh của di sản 2 nhưng câu gắn di sản 1
    q, errors = check(item, 1, req)
    assert q is None and any("đúng di sản" in e for e in errors)
    item["heritageId"] = 2
    assert check(item, 1, req)[0] is not None


async def test_partial_valid_then_retry_asks_only_for_the_missing_count(make_client):
    req = questions_request(2, ["SINGLE_CHOICE"], count=3)
    bad = question_item("SINGLE_CHOICE", 2, req, 1)
    bad["options"].pop()
    first = {"questions": [question_item("SINGLE_CHOICE", 2, req, 0), bad]}
    second = {"questions": [question_item("SINGLE_CHOICE", 2, req, 2), question_item("SINGLE_CHOICE", 2, req, 3)]}
    llm = FakeLlm(ok(first, 500, 200), ok(second, 600, 250))
    r = await make_client(llm).post(URL, json=req)

    assert r.status_code == 200
    assert len(r.json()["questions"]) == 3
    assert "Số câu cần sinh: 3" in llm.calls[0]["user"]
    assert "Số câu cần sinh: 2" in llm.calls[1]["user"]
    assert "cau_da_co_khong_lap_lai" in llm.calls[1]["user"] and "đúng 4" in llm.calls[1]["user"]
    assert r.json()["usage"] == {"inputTokens": 1100, "outputTokens": 450}


async def test_fewer_than_requested_after_retry_is_returned_as_partial(make_client):
    req = questions_request(2, ["SINGLE_CHOICE"], count=3)
    bad = question_item("SINGLE_CHOICE", 2, req, 1)
    bad["options"].pop()
    llm = FakeLlm(ok({"questions": [question_item("SINGLE_CHOICE", 2, req, 0), bad]}))
    r = await make_client(llm).post(URL, json=req)
    assert r.status_code == 200 and len(r.json()["questions"]) == 1
    assert len(llm.calls) == 2


async def test_no_valid_question_after_retry_is_502(make_client):
    req = questions_request(2, ["SINGLE_CHOICE"], count=2)
    bad = question_item("SINGLE_CHOICE", 2, req, 1)
    bad["options"].pop()
    llm = FakeLlm(ok({"questions": [bad]}))
    r = await make_client(llm).post(URL, json=req)
    assert r.status_code == 502 and r.json()["errorCode"] == "invalid_model_output" and len(llm.calls) == 2


async def test_duplicates_are_not_counted_twice_and_extras_are_trimmed(make_client):
    req = questions_request(2, ["SINGLE_CHOICE"], count=2)
    a = question_item("SINGLE_CHOICE", 2, req, 0)
    items = [a, copy.deepcopy(a), question_item("SINGLE_CHOICE", 2, req, 1), question_item("SINGLE_CHOICE", 2, req, 2)]
    llm = FakeLlm(ok({"questions": items}))
    r = await make_client(llm).post(URL, json=req)
    assert r.status_code == 200 and len(r.json()["questions"]) == 2
    assert len(llm.calls) == 1


async def test_type_not_allowed_at_level_is_422_without_model_call(make_client):
    llm = FakeLlm(ok({}))
    r = await make_client(llm).post(URL, json=questions_request(1, ["SINGLE_CHOICE", "TRUE_FALSE"]))
    assert r.status_code == 422 and r.json()["errorCode"] == "type_not_allowed_at_level"
    r = await make_client(llm).post(URL, json=questions_request(3, ["FILL_BLANK"]))
    assert r.status_code == 422
    assert llm.calls == []


async def test_insufficient_material_is_422_and_infeasible_types_are_left_out(make_client):
    llm = FakeLlm(ok({}))
    # cấp 1 chỉ có dạng cần ảnh nhưng di sản không có ảnh
    r = await make_client(llm).post(URL, json=questions_request(1, ["IMAGE_CHOICE", "TRUE_FALSE"], images=0))
    assert r.status_code == 422 and r.json()["errorCode"] == "insufficient_material" and llm.calls == []

    req = questions_request(1, ["IMAGE_CHOICE", "TRUE_FALSE"], images=2)   # đủ cho Đúng/Sai, chưa đủ 3 ảnh để chọn hình
    llm = FakeLlm(ok({"questions": [question_item("TRUE_FALSE", 1, req, 0)]}))
    r = await make_client(llm).post(URL, json={**req, "count": 1})
    assert r.status_code == 200
    variants = llm.calls[0]["schema"]["properties"]["questions"]["items"]
    assert variants["properties"]["questionType"]["enum"] == ["TRUE_FALSE"]
    assert "IMAGE_CHOICE" not in llm.calls[0]["user"]


@pytest.mark.parametrize("count,ok_status", [(0, 422), (21, 422), (1, 200), (20, 200)])
async def test_count_bounds(make_client, count, ok_status):
    req = questions_request(2, ["SINGLE_CHOICE"], count=1)
    req["count"] = count
    llm = FakeLlm(ok({"questions": [question_item("SINGLE_CHOICE", 2, req, i) for i in range(max(count, 1))]}))
    r = await make_client(llm).post(URL, json=req)
    assert r.status_code == ok_status


async def test_effort_tokens_and_prompt_content(make_client):
    req = questions_request(2, ["SINGLE_CHOICE"], count=10, difficulty="HARD")
    llm = FakeLlm(ok({"questions": [question_item("SINGLE_CHOICE", 2, req, i) for i in range(10)]}))
    await make_client(llm).post(URL, json=req)
    call = llm.calls[0]
    assert call["effort"] == "medium" and 5000 < call["max_tokens"] <= 16000
    assert "Độ khó: HARD" in call["user"] and "Cấp học của lớp: 2" in call["user"]
    assert "/media/h1-1.jpg" in call["user"]            # ảnh gửi kèm đường dẫn để mô hình chọn
    for t in ("SINGLE_CHOICE", "IMAGE_CHOICE", "SOURCE_READING"):
        assert t in call["system"]                      # system prompt đủ tám dạng, có ví dụ
