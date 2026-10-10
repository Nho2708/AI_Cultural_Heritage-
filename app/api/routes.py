"""Năm API của dịch vụ AI và kiểm tra sức khỏe."""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..recommender.rank import rank_related
from ..schemas.heritage import SummarizeRequest, SummarizeResponse, TranslateRequest, TranslateResponse
from ..schemas.lesson import ComposeRequest, ComposeResponse
from ..schemas.questions import QuestionsRequest, QuestionsResponse
from ..schemas.recommend import RankRequest, RankResponse
from ..services.heritage import summarize_heritage, translate_heritage
from ..services.lesson import compose_lesson
from ..services.questions import generate_questions

router = APIRouter()


@router.get("/health", tags=["health"])
async def health(request: Request) -> dict:
    settings = request.app.state.settings
    return {"status": "ok", "model": settings.ai_model, "llmConfigured": settings.llm_configured()}


@router.post("/v1/compose-lesson", response_model=ComposeResponse, tags=["ai"])
async def compose_lesson_endpoint(body: ComposeRequest, request: Request) -> ComposeResponse:
    return await compose_lesson(body, request.app.state.llm, request.app.state.settings)


@router.post("/v1/generate-questions", response_model=QuestionsResponse, tags=["ai"])
async def generate_questions_endpoint(body: QuestionsRequest, request: Request) -> QuestionsResponse:
    return await generate_questions(body, request.app.state.llm, request.app.state.settings)


@router.post("/v1/summarize-heritage", response_model=SummarizeResponse, tags=["ai"])
async def summarize_heritage_endpoint(body: SummarizeRequest, request: Request) -> SummarizeResponse:
    return await summarize_heritage(body, request.app.state.llm, request.app.state.settings)


@router.post("/v1/translate-heritage", response_model=TranslateResponse, tags=["ai"])
async def translate_heritage_endpoint(body: TranslateRequest, request: Request) -> TranslateResponse:
    return await translate_heritage(body, request.app.state.llm, request.app.state.settings)


@router.post("/v1/rank-related", response_model=RankResponse, tags=["recommend"])
def rank_related_endpoint(body: RankRequest) -> RankResponse:
    # Hàm đồng bộ: FastAPI chạy trong luồng riêng, không chặn vòng lặp sự kiện khi tính TF-IDF.
    return RankResponse(related=rank_related(body))
