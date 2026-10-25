"""Sáu API của dịch vụ AI (năm API mô hình/gợi ý và giọng đọc) và kiểm tra sức khỏe."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..errors import InvalidInput, ServiceError
from ..giong_doc.dong_co import GiongDocKhongSan, KhongCoChuDoc
from ..recommender.rank import rank_related
from ..schemas.heritage import SummarizeRequest, SummarizeResponse, TranslateRequest, TranslateResponse
from ..schemas.lesson import ComposeRequest, ComposeResponse
from ..schemas.questions import QuestionsRequest, QuestionsResponse
from ..schemas.recommend import RankRequest, RankResponse
from ..schemas.tts import TtsRequest
from ..services.heritage import summarize_heritage, translate_heritage
from ..services.lesson import compose_lesson
from ..services.questions import generate_questions

router = APIRouter()


@router.get("/health", tags=["health"])
async def health(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "status": "ok", "provider": settings.ai_provider, "model": settings.model_name(), "llmConfigured": settings.llm_configured(),
        # Trạng thái giọng đọc: off | loading | ready | error. Luôn trả 200 kể cả khi mô hình giọng đang nạp.
        "tts": request.app.state.giong_doc.trang_thai,
    }


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


@router.post("/v1/tts", tags=["tts"], response_class=Response, responses={200: {"content": {"audio/mpeg": {}}}})
def tts_endpoint(body: TtsRequest, request: Request) -> Response:
    """Chữ tiếng Việt -> MP3 mono. Hàm đồng bộ: FastAPI chạy trong luồng riêng nên việc sinh âm thanh không chặn vòng lặp sự kiện."""
    try:
        ket_qua = request.app.state.giong_doc.tong_hop(body.text, body.voice)
    except GiongDocKhongSan as e:
        raise ServiceError(503, e.ma, e.thong_bao, headers={"Retry-After": str(e.goi_lai_sau)}) from e
    except KhongCoChuDoc as e:
        raise InvalidInput("no_speakable_text", "Chữ không có nội dung để đọc thành tiếng.") from e
    return Response(
        content=ket_qua.mp3,
        media_type="audio/mpeg",
        headers={"X-Duration-Ms": str(ket_qua.thoi_luong_ms), "X-Voice": ket_qua.giong},
    )
