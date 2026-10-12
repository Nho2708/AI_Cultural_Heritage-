"""Đếm token vào của từng API bằng messages.count_tokens (không tính tiền, không sinh chữ).

Dùng để kiểm lược đồ JSON và tham số có được nhà cung cấp chấp nhận không, và ước chi phí phần token vào.
    .venv\\Scripts\\python scripts\\dem-token.py
Mỗi lần đếm là một lời gọi tới nhà cung cấp nên cũng ghi vào sổ đếm --ledger (xem thu-that.py).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]

import anthropic
import du_lieu_mau as mau

from app.config import load_settings
from app.prompts import heritage as heritage_prompts
from app.prompts import lesson as lesson_prompts
from app.prompts import questions as question_prompts
from app.schemas.heritage import SummarizeRequest, TranslateRequest
from app.schemas.lesson import ComposeRequest
from app.schemas.questions import QuestionsRequest
from app.services.questions import feasible_types

PRICE_IN = 0.10 / 1_000_000
LEVEL_TYPES = {
    1: ["TRUE_FALSE", "IMAGE_CHOICE", "MATCHING", "ORDERING"],
    2: ["SINGLE_CHOICE", "TRUE_FALSE", "ORDERING", "FILL_BLANK"],
    3: ["SINGLE_CHOICE", "MULTI_TRUE_FALSE", "SOURCE_READING"],
}


def cases():
    for level in (1, 2, 3):
        req = ComposeRequest.model_validate({"gradeLevel": level, "length": "MEDIUM", "heritages": [mau.di_san()]})
        yield f"compose-lesson cấp {level}", lesson_prompts.system_prompt(level), lesson_prompts.user_prompt(req), lesson_prompts.schema(level)
    for level in (1, 2, 3):
        req = QuestionsRequest.model_validate({"gradeLevel": level, "count": 6, "difficulty": "MEDIUM", "types": LEVEL_TYPES[level], "heritages": [mau.di_san()]})
        feasible = feasible_types(req, LEVEL_TYPES[level])
        yield (f"generate-questions cấp {level}", question_prompts.system_prompt(),
               question_prompts.user_prompt(req, req.heritages, feasible, 6, []), question_prompts.schema(list(feasible), level))
    sreq = SummarizeRequest.model_validate({"source": mau.van_ban_di_san()})
    yield "summarize-heritage", heritage_prompts.SUMMARIZE_SYSTEM, heritage_prompts.summarize_user(sreq), heritage_prompts.summarize_schema()
    summary = {"shortText": "Hoàng thành Thăng Long. " * 20, "detailedText": "Hoàng thành Thăng Long. " * 60}
    for lang in ("en", "ko", "zh-Hans", "ja"):
        treq = TranslateRequest.model_validate({"targetLanguage": lang, "contentLanguage": "vi", "content": mau.van_ban_di_san(),
                                                "summaryLanguage": "vi", "summary": summary})
        yield f"translate-heritage {lang}", heritage_prompts.TRANSLATE_SYSTEM, heritage_prompts.translate_user(treq), heritage_prompts.translate_schema(True)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-calls", type=int, default=60)
    parser.add_argument("--ledger", default=str(ROOT / ".thu-that-ledger.json"))
    args = parser.parse_args()
    settings = load_settings()
    if settings.anthropic_api_key is None or not settings.llm_configured():
        print("Chưa có ANTHROPIC_API_KEY.")
        return 2
    ledger_path = Path(args.ledger)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {"calls": 0, "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "costUsd": 0.0}
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value(), max_retries=0)
    failed = 0
    for name, system, user, schema in cases():
        if ledger["calls"] >= args.max_calls:
            print("Đủ hạn mức lời gọi, dừng.")
            break
        ledger["calls"] += 1
        ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
        try:
            r = await client.messages.count_tokens(
                model=settings.ai_model,
                system=[{"type": "text", "text": system}],
                messages=[{"role": "user", "content": user}],
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
            )
            print(f"{name:<32} DAT   token vào={r.input_tokens:>6}  (~${r.input_tokens * PRICE_IN:.5f})")
        except anthropic.APIStatusError as exc:
            failed += 1
            print(f"{name:<32} LỖI {exc.status_code}: {str(getattr(exc, 'message', ''))[:200]}")
        except anthropic.APIConnectionError as exc:
            failed += 1
            print(f"{name:<32} LỖI mạng: {type(exc).__name__}")
    print(f"Sổ đếm: {ledger['calls']} lời gọi.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
