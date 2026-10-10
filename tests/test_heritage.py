"""Tóm tắt tiếng Việt và dịch di sản sang en, ko, zh-Hans, ja."""
from __future__ import annotations

import copy

import pytest

from app.prompts.glossary import find_terms, missing_terms
from app.text import fold

from .conftest import FakeLlm, ok
from .factories import heritage_text, translate_request, translation_output, viet_words

SUM = "/v1/summarize-heritage"
TR = "/v1/translate-heritage"


def summarize_request(words: int = 400) -> dict:
    return {
        "generationId": 1, "heritageId": 9,
        "source": {**heritage_text(), "content": "## Lịch sử\n\n" + viet_words(words, 14), "timelines": [], "events": [], "media": []},
    }


def summary_output(short: int = 100, detailed: int = 320) -> dict:
    paras = [viet_words(detailed // 3, 12, offset=i) for i in range(3)]
    return {"shortText": viet_words(short, 12), "detailedText": "\n\n".join(paras)}


# ---------------- Tóm tắt ----------------

async def test_summary_valid(make_client):
    llm = FakeLlm(ok(summary_output(), 800, 600))
    r = await make_client(llm).post(SUM, json=summarize_request())
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"shortText", "detailedText", "model", "usage"}
    assert 68 <= len(body["shortText"].split()) <= 138 and 212 <= len(body["detailedText"].split()) <= 460
    assert "\n\n" in body["detailedText"] and "\n" not in body["shortText"]
    assert body["usage"] == {"inputTokens": 800, "outputTokens": 600}
    assert llm.calls[0]["effort"] == "low"


async def test_summary_markdown_is_stripped(make_client):
    out = summary_output()
    out["shortText"] = "**" + out["shortText"] + "**"
    out["detailedText"] = "## Tổng quan\n\n- " + out["detailedText"].replace("\n\n", "\n\n- ")
    r = await make_client(FakeLlm(ok(out))).post(SUM, json=summarize_request())
    assert r.status_code == 200
    body = r.json()
    for key in ("shortText", "detailedText"):
        assert "*" not in body[key] and "#" not in body[key] and "\n- " not in body[key]


@pytest.mark.parametrize("short,detailed", [(30, 320), (100, 100), (100, 700), (300, 320)])
async def test_summary_length_outside_window_retries_then_502(make_client, short, detailed):
    llm = FakeLlm(ok(summary_output(short, detailed)))
    r = await make_client(llm).post(SUM, json=summarize_request())
    assert r.status_code == 502 and len(llm.calls) == 2
    assert "LƯU Ý" in llm.calls[1]["user"]


async def test_summary_of_a_short_source_may_be_shorter(make_client):
    req = summarize_request(words=60)
    r = await make_client(FakeLlm(ok(summary_output(60, 90)))).post(SUM, json=req)
    assert r.status_code == 200, r.text


async def test_summary_must_be_vietnamese(make_client):
    out = {"shortText": "The citadel is old. " * 25, "detailedText": "Long text here. " * 80}
    r = await make_client(FakeLlm(ok(out))).post(SUM, json=summarize_request())
    assert r.status_code == 502
    assert any("tiếng Việt" in d["problem"] for d in r.json()["details"])


async def test_summary_without_source_text_is_422_without_model_call(make_client):
    llm = FakeLlm(ok({}))
    req = summarize_request()
    req["source"]["shortDescription"] = None
    req["source"]["content"] = "  "
    r = await make_client(llm).post(SUM, json=req)
    assert r.status_code == 422 and r.json()["errorCode"] == "missing_source" and llm.calls == []


async def test_summary_retry_recovers(make_client):
    llm = FakeLlm(ok(summary_output(20, 320)), ok(summary_output()))
    r = await make_client(llm).post(SUM, json=summarize_request())
    assert r.status_code == 200 and len(llm.calls) == 2


# ---------------- Dịch ----------------

@pytest.mark.parametrize("target", ["en", "ko", "zh-Hans", "ja"])
async def test_translation_valid_per_language(make_client, target):
    req = translate_request(target)
    llm = FakeLlm(ok(translation_output(target, req), 900, 700))
    r = await make_client(llm).post(TR, json=req)

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"content", "summary", "model", "usage"}
    c = body["content"]
    assert c["timelines"][0]["id"] == 7 and c["events"][0]["id"] == 70 and c["events"][0]["timelineId"] == 7 and c["media"][0]["id"] == 700
    assert c["content"].startswith("##") and body["summary"]["shortText"]
    assert body["usage"] == {"inputTokens": 900, "outputTokens": 700}
    assert len(llm.calls) == 1 and llm.calls[0]["effort"] == "low"


async def test_translation_without_summary_has_null_summary_and_smaller_schema(make_client):
    req = translate_request("en", with_summary=False)
    llm = FakeLlm(ok(translation_output("en", req)))
    r = await make_client(llm).post(TR, json=req)
    assert r.status_code == 200 and r.json()["summary"] is None
    assert "summary" not in llm.calls[0]["schema"]["properties"]


async def test_english_source_to_korean_uses_english_glossary_forms(make_client):
    req = translate_request("ko", content_language="en")
    req["content"]["name"] = "Imperial Citadel of Thang Long"
    req["content"]["content"] = "## History\n\nThe citadel in Hanoi was built by the Ly dynasty."
    req["content"]["shortDescription"] = "The power centre."
    llm = FakeLlm(ok(translation_output("ko", req)))
    r = await make_client(llm).post(TR, json=req)
    assert r.status_code == 200, r.text
    assert "bang_thuat_ngu" in llm.calls[0]["user"] and "탕롱 황성" in llm.calls[0]["user"]
    assert "하노이" in llm.calls[0]["user"]


@pytest.mark.parametrize(
    "target,mutate,fragment",
    [
        ("ko", lambda o: o["content"].update(content="## Lịch sử\n\nThành được xây dựng vào thời nhà Lý ở Hà Nội và được mở rộng liên tục."), "tiếng Hàn"),
        ("zh-Hans", lambda o: o["content"].update(name="Hoàng thành Thăng Long"), "tiếng Trung"),
        ("zh-Hans", lambda o: o["content"].update(content="## 歷史\n\n這座皇城建於李朝時期，位於河內，後來的各個朝代不斷對其進行擴建，在漫長的歲月中持續發展。"), "phồn thể"),
        ("ja", lambda o: o["content"].update(content="## 历史\n\n这座皇城建于李朝时期，位于河内，后来的各个朝代不断对其进行扩建，在漫长的岁月中持续发展，非常有名气。"), "tiếng Nhật"),
        ("en", lambda o: o["content"].update(content="## Lịch sử\n\nThành được xây dựng vào thời nhà Lý ở Hà Nội và được mở rộng liên tục qua các triều đại sau đó nữa."), "tiếng Anh"),
        ("en", lambda o: o["content"]["events"].clear(), "events"),
        ("en", lambda o: o["content"]["media"][0].update(id=999), "media"),
        ("en", lambda o: o["content"]["timelines"][0].update(name=""), "tên"),
        ("en", lambda o: o["content"].update(content="History"), "độ dài"),
        ("en", lambda o: o["content"].update(content=o["content"]["content"].replace("## History", "History")), "tiêu đề Markdown"),
        ("en", lambda o: o.pop("summary"), "summary"),
        ("en", lambda o: o["summary"].update(detailedText=""), "summary"),
    ],
)
async def test_translation_rules_retry_then_502(make_client, target, mutate, fragment):
    req = translate_request(target)
    out = translation_output(target, req)
    mutate(out)
    llm = FakeLlm(ok(out))
    r = await make_client(llm).post(TR, json=req)
    assert r.status_code == 502, r.text
    assert len(llm.calls) == 2
    assert any(fragment in d["problem"] for d in r.json()["details"]), r.json()["details"]


async def test_glossary_violation_triggers_retry(make_client):
    req = translate_request("en", with_summary=False)
    bad = translation_output("en", req)
    bad["content"]["name"] = "Citadel of Hanoi"
    bad["content"]["events"][0]["name"] = "Capital moved"
    bad["content"]["content"] = "## History\n\nThe old citadel was built under the Ly dynasty and expanded by later dynasties over many centuries."
    llm = FakeLlm(ok(bad), ok(translation_output("en", req)))
    r = await make_client(llm).post(TR, json=req)
    assert r.status_code == 200 and len(llm.calls) == 2
    assert "thuật ngữ" in llm.calls[1]["user"] and "Thang Long" in llm.calls[1]["user"]


async def test_translation_retry_recovers_and_sums_usage(make_client):
    req = translate_request("ja")
    bad = translation_output("ja", req)
    bad["content"]["name"] = "Hoàng thành Thăng Long"
    llm = FakeLlm(ok(bad, 900, 100), ok(translation_output("ja", req), 950, 700))
    r = await make_client(llm).post(TR, json=req)
    assert r.status_code == 200
    assert r.json()["usage"] == {"inputTokens": 1850, "outputTokens": 800}
    assert "tiếng Nhật" in llm.calls[1]["user"]


async def test_null_fields_stay_null_and_markdown_in_summary_is_stripped(make_client):
    req = translate_request("en")
    req["content"]["shortDescription"] = None
    req["content"]["timelines"][0]["description"] = None
    out = translation_output("en", req)
    out["content"]["shortDescription"] = "Nên bị bỏ"
    out["content"]["timelines"][0]["description"] = "Nên bị bỏ"
    out["summary"]["detailedText"] = "**" + out["summary"]["detailedText"] + "**"
    r = await make_client(FakeLlm(ok(out))).post(TR, json=req)
    assert r.status_code == 200
    c = r.json()["content"]
    assert c["shortDescription"] is None and c["timelines"][0]["description"] is None
    assert "*" not in r.json()["summary"]["detailedText"]


async def test_unknown_ids_cannot_slip_in_and_event_timeline_id_comes_from_source(make_client):
    req = translate_request("en")
    out = translation_output("en", req)
    out["content"]["events"][0]["timelineId"] = 12345
    r = await make_client(FakeLlm(ok(out))).post(TR, json=req)
    assert r.status_code == 200 and r.json()["content"]["events"][0]["timelineId"] == 7


@pytest.mark.parametrize("target,content_lang,summary_lang", [("en", "en", None), ("vi", "vi", None), ("ko", "vi", "ko")])
async def test_invalid_language_combinations(make_client, target, content_lang, summary_lang):
    req = translate_request("en" if target == "vi" else target, content_language=content_lang)
    req["targetLanguage"] = target
    if summary_lang:
        req["summaryLanguage"] = summary_lang
    llm = FakeLlm(ok({}))
    r = await make_client(llm).post(TR, json=req)
    assert r.status_code == 422 and llm.calls == []


async def test_translation_prompt_contains_matching_glossary_only(make_client):
    req = translate_request("zh-Hans")
    req["content"]["content"] += "\n\nVua ở Huế và Hội An thời nhà Nguyễn."
    out = translation_output("zh-Hans", req)
    out["content"]["content"] += "\n\n君王在顺化和会安，阮朝时期。"
    llm = FakeLlm(ok(out))
    r = await make_client(llm).post(TR, json=req)
    assert r.status_code == 200, r.text
    user = llm.calls[0]["user"]
    for expected in ("顺化", "会安", "阮朝", "升龙皇城"):
        assert expected in user
    assert "Đà Nẵng" not in user and "岘港" not in user


# ---------------- Bảng thuật ngữ ----------------

def test_glossary_matches_whole_words_only_and_ignores_diacritics():
    assert [t.en[0] for t in find_terms([("Chuyến thuê xe ở Hà Nội", "vi")])] == ["Hanoi"]   # "thuê" không phải "Huế"
    assert [t.en[0] for t in find_terms([("Cố đô Huế rất đẹp", "vi")])] == ["Hue", "Hue Ancient Capital"]
    assert [t.en[0] for t in find_terms([("The city of Hue", "en")])] == ["Hue"]
    assert find_terms([("Các triều đại Việt Nam", "vi")]) and [t.en[0] for t in find_terms([("Các triều đại Việt Nam", "vi")])] == ["Vietnam"]
    assert [t.en[0] for t in find_terms([("thời nhà Lý", "vi")])] == ["Ly dynasty"]


def test_glossary_missing_terms_per_language():
    terms = find_terms([("Hoàng thành Thăng Long ở Hà Nội", "vi")])
    assert missing_terms(terms, "en", "The Imperial Citadel of Thăng Long in Hanoi") == []
    assert set(missing_terms(terms, "en", "The old citadel")) == {"Hanoi", "Thang Long", "Imperial Citadel of Thang Long"}
    assert missing_terms(terms, "ko", "하노이의 탕롱 황성") == []
    assert missing_terms(terms, "zh-Hans", "河内的升龙皇城") == []
    assert missing_terms(terms, "ja", "ハノイのタンロン皇城") == []


def test_fold_helper():
    assert fold("Đà Nẵng – Hội An") == "da nang – hoi an"


async def test_request_not_mutated(make_client):
    req = translate_request("en")
    snapshot = copy.deepcopy(req)
    await make_client(FakeLlm(ok(translation_output("en", req)))).post(TR, json=req)
    assert req == snapshot
