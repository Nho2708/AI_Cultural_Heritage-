"""Mô hình giả dùng để chạy nối backend phải luôn sinh đầu ra qua được bộ kiểm của từng API."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import du_lieu_mau as mau
from mo_hinh_gia import MoHinhGia

LEVEL_TYPES = {
    1: ["TRUE_FALSE", "IMAGE_CHOICE", "MATCHING", "ORDERING"],
    2: ["SINGLE_CHOICE", "TRUE_FALSE", "ORDERING", "FILL_BLANK"],
    3: ["SINGLE_CHOICE", "MULTI_TRUE_FALSE", "SOURCE_READING"],
}


@pytest.mark.parametrize("level", [1, 2, 3])
@pytest.mark.parametrize("length", ["SHORT", "MEDIUM", "DETAILED"])
async def test_compose(make_client, level, length):
    llm = MoHinhGia()
    r = await make_client(llm).post("/v1/compose-lesson", json={"gradeLevel": level, "length": length, "heritages": [mau.di_san()]})
    assert r.status_code == 200, r.text
    assert llm.calls == 1


@pytest.mark.parametrize("level", [1, 2, 3])
async def test_questions(make_client, level):
    llm = MoHinhGia()
    body = {"gradeLevel": level, "count": 8, "difficulty": "EASY", "types": LEVEL_TYPES[level], "heritages": [mau.di_san()]}
    r = await make_client(llm).post("/v1/generate-questions", json=body)
    assert r.status_code == 200, r.text
    assert len(r.json()["questions"]) == 8 and llm.calls == 1


async def test_summary_and_translations(make_client):
    llm = MoHinhGia()
    client = make_client(llm)
    s = await client.post("/v1/summarize-heritage", json={"source": mau.van_ban_di_san()})
    assert s.status_code == 200, s.text
    summary = {"shortText": s.json()["shortText"], "detailedText": s.json()["detailedText"]}
    for lang in ("en", "ko", "zh-Hans", "ja"):
        r = await client.post("/v1/translate-heritage", json={
            "targetLanguage": lang, "contentLanguage": "vi", "content": mau.van_ban_di_san(), "summaryLanguage": "vi", "summary": summary,
        })
        assert r.status_code == 200, (lang, r.text)
    assert llm.calls == 5
