"""Gọi thật có giới hạn: mỗi API dùng mô hình chạy với dữ liệu mẫu, in số token và chi phí ước tính.

Chạy (khóa lấy từ .env hoặc %APPDATA%\\DSVHVN\\ai-service.env, không in ra):
    .venv\\Scripts\\python scripts\\thu-that.py
    .venv\\Scripts\\python scripts\\thu-that.py --only compose,translate --levels 2 --languages en,ko --max-calls 20

Sổ đếm lời gọi (--ledger) cộng dồn qua các lần chạy; quá --max-calls thì dừng, để không vượt hạn mức lời gọi thật của đợt thử.
Nhà cung cấp theo AI_PROVIDER. Giá Haiku 5.5 (prompt tối đa 100 nghìn token): 0,10 USD / 1 triệu token vào, 0,50 USD / 1 triệu token ra;
đọc từ bộ nhớ đệm 0,1 lần giá vào, ghi bộ nhớ đệm 1,25 lần giá vào. Gemini dùng hạn mức miễn phí nên chi phí ghi 0 (vẫn in số token).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]

import du_lieu_mau as mau

from app.config import load_settings
from app.errors import ServiceError
from app.llm.client import Llm, LlmResult, TokenUsage
from app.llm.factory import build_llm
from app.logging_setup import setup_logging
from app.schemas.heritage import SummarizeRequest, TranslateRequest
from app.schemas.lesson import ComposeRequest
from app.schemas.questions import QuestionsRequest
from app.services.heritage import summarize_heritage, translate_heritage
from app.services.lesson import compose_lesson
from app.services.questions import generate_questions

PRICE_IN, PRICE_OUT = 0.10 / 1_000_000, 0.50 / 1_000_000
LEVEL_TYPES = {
    1: ["TRUE_FALSE", "IMAGE_CHOICE", "MATCHING", "ORDERING"],
    2: ["SINGLE_CHOICE", "TRUE_FALSE", "ORDERING", "FILL_BLANK"],
    3: ["SINGLE_CHOICE", "MULTI_TRUE_FALSE", "SOURCE_READING"],
}


def cost_of(u: TokenUsage) -> float:
    return u.input_tokens * PRICE_IN + u.cache_read_tokens * PRICE_IN * 0.1 + u.cache_write_tokens * PRICE_IN * 1.25 + u.output_tokens * PRICE_OUT


class Ledger:
    def __init__(self, path: Path, max_calls: int):
        self.path, self.max_calls = path, max_calls
        self.data = {"calls": 0, "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "costUsd": 0.0}
        if path.exists():
            self.data.update(json.loads(path.read_text(encoding="utf-8")))

    def check(self) -> None:
        if self.data["calls"] >= self.max_calls:
            raise SystemExit(f"Đã đủ {self.data['calls']} lời gọi thật (giới hạn {self.max_calls}); dừng.")

    def add(self, u: TokenUsage) -> None:
        self.data["calls"] += 1
        self.data["input"] += u.input_tokens
        self.data["output"] += u.output_tokens
        self.data["cacheRead"] += u.cache_read_tokens
        self.data["cacheWrite"] += u.cache_write_tokens
        self.data["costUsd"] = round(self.data["costUsd"] + cost_of(u), 6)
        self.path.write_text(json.dumps(self.data), encoding="utf-8")


class CountingLlm:
    """Bọc bộ gọi mô hình: đếm lời gọi thật, cộng token, chặn khi hết hạn mức."""

    def __init__(self, inner: Llm, ledger: Ledger):
        self.inner, self.ledger = inner, ledger
        self.model = inner.model
        self.usage = TokenUsage()
        self.calls = 0

    async def complete_json(self, **kwargs) -> LlmResult:
        self.ledger.check()
        try:
            result = await self.inner.complete_json(**kwargs)
        except ServiceError:
            self.ledger.add(TokenUsage())  # lời gọi lỗi vẫn tính vào hạn mức
            self.calls += 1
            raise
        self.calls += 1
        self.usage.add(result.usage)
        self.ledger.add(result.usage)
        return result


def words(text: str | None) -> int:
    return len((text or "").split())


async def run_case(name: str, llm: CountingLlm, make_call, describe) -> dict:
    llm.usage, llm.calls = TokenUsage(), 0
    started = time.perf_counter()
    status, detail, payload = "DAT", "", None
    try:
        response = await make_call()
        payload = response.model_dump(by_alias=True)
        detail = describe(response)
    except ServiceError as exc:
        status, detail = f"LOI {exc.status} {exc.code}", "; ".join(d.get("problem", "") for d in exc.details)[:300]
    elapsed = time.perf_counter() - started
    u = llm.usage
    print(
        f"{name:<34} {status:<26} lời gọi={llm.calls} vào={u.input_tokens + u.cache_read_tokens + u.cache_write_tokens:>6} "
        f"ra={u.output_tokens:>6} ${cost_of(u):.5f} {elapsed:5.1f}s  {detail}"
    )
    return {"name": name, "status": status, "calls": llm.calls, "input": u.input_tokens + u.cache_read_tokens + u.cache_write_tokens,
            "output": u.output_tokens, "costUsd": cost_of(u), "seconds": round(elapsed, 1), "detail": detail, "payload": payload}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", default="compose,questions,summarize,translate")
    parser.add_argument("--levels", default="1,2,3")
    parser.add_argument("--languages", default="en,ko,zh-Hans,ja")
    parser.add_argument("--max-calls", type=int, default=60)
    parser.add_argument("--ledger", default=None, help="Sổ đếm lời gọi; mặc định riêng cho từng nhà cung cấp.")
    parser.add_argument("--out", default=None, help="Ghi kết quả đầy đủ ra tệp JSON này (để đọc thử chất lượng; không commit).")
    args = parser.parse_args()

    setup_logging("WARNING")  # chỉ lỗi; log không có khóa hay nội dung
    settings = load_settings()
    if not settings.llm_configured():
        missing = "GEMINI_API_KEY" if settings.ai_provider == "gemini" else "ANTHROPIC_API_KEY"
        print(f"Chưa có {missing} trong .env hoặc %APPDATA%\\DSVHVN\\ai-service.env.")
        return 2
    if settings.ai_provider == "gemini":
        global PRICE_IN, PRICE_OUT
        PRICE_IN = PRICE_OUT = 0.0  # hạn mức miễn phí của Google AI Studio
    ledger = Ledger(Path(args.ledger or ROOT / f".thu-that-ledger-{settings.ai_provider}.json"), args.max_calls)
    llm = CountingLlm(build_llm(settings), ledger)
    only = set(args.only.split(","))
    levels = [int(x) for x in args.levels.split(",")]
    languages = args.languages.split(",")
    print(f"Mô hình: {settings.ai_provider}/{settings.model_name()}. Đã dùng trước đó: {ledger.data['calls']} lời gọi, ${ledger.data['costUsd']:.4f}.\n")

    results: list[dict] = []

    if "compose" in only:
        for level in levels:
            req = ComposeRequest.model_validate({
                "generationId": 1, "lessonId": 1, "gradeLevel": level, "length": "MEDIUM",
                "heritages": [mau.di_san()], "currentContent": "",
            })

            def describe(r, level=level):
                kinds: dict[str, int] = {}
                for s in r.steps:
                    kinds[s.kind.value] = kinds.get(s.kind.value, 0) + 1
                return f"{words(r.content)} từ; ý chính={len(r.key_points)}; phần={kinds}; trích={len(r.source_quotes)}"

            results.append(await run_case(f"compose-lesson cấp {level}", llm, lambda req=req: compose_lesson(req, llm, settings), describe))

    if "questions" in only:
        for level in levels:
            req = QuestionsRequest.model_validate({
                "generationId": 1, "lessonId": 1, "gradeLevel": level, "count": 6, "difficulty": "MEDIUM",
                "types": LEVEL_TYPES[level], "heritages": [mau.di_san()],
            })

            def describe(r, req=req):
                kinds: dict[str, int] = {}
                for q in r.questions:
                    kinds[q.question_type.value] = kinds.get(q.question_type.value, 0) + 1
                return f"{len(r.questions)}/{req.count} câu {kinds}"

            results.append(await run_case(f"generate-questions cấp {level}", llm, lambda req=req: generate_questions(req, llm, settings), describe))

    summary = None
    if "summarize" in only or "translate" in only:
        sreq = SummarizeRequest.model_validate({"generationId": 1, "heritageId": 1, "source": mau.van_ban_di_san()})
        if "summarize" in only:
            case = await run_case(
                "summarize-heritage", llm, lambda: summarize_heritage(sreq, llm, settings),
                lambda r: f"ngắn {words(r.short_text)} từ; chi tiết {words(r.detailed_text)} từ",
            )
            results.append(case)
            if case["payload"]:
                summary = {"shortText": case["payload"]["shortText"], "detailedText": case["payload"]["detailedText"]}

    if "translate" in only:
        for lang in languages:
            body = {
                "generationId": 1, "heritageId": 1, "targetLanguage": lang, "contentLanguage": "vi",
                "content": mau.van_ban_di_san(),
                "summaryLanguage": "vi" if summary else None, "summary": summary,
            }
            req = TranslateRequest.model_validate(body)
            results.append(await run_case(
                f"translate-heritage {lang}", llm, lambda req=req: translate_heritage(req, llm, settings),
                lambda r: f"tên={r.content.name!r}; nội dung {len(r.content.content or '')} ký tự; tóm tắt={'có' if r.summary else 'không'}",
            ))

    total_calls = sum(r["calls"] for r in results)
    total_in = sum(r["input"] for r in results)
    total_out = sum(r["output"] for r in results)
    total_cost = sum(r["costUsd"] for r in results)
    print(f"\nTổng lần này: {total_calls} lời gọi thật, {total_in} token vào, {total_out} token ra, ước tính ${total_cost:.4f}.")
    print(f"Cộng dồn sổ đếm: {ledger.data['calls']} lời gọi, ${ledger.data['costUsd']:.4f} (giới hạn {args.max_calls} lời gọi).")
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(r["status"] == "DAT" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
