"""Prompt và lược đồ JSON tóm tắt tiếng Việt và dịch di sản sang en, ko, zh-Hans, ja."""
from __future__ import annotations

from ..rules import (
    DETAILED_SUMMARY_MAX, DETAILED_SUMMARY_MIN, SHORT_SUMMARY_MAX, SHORT_SUMMARY_MIN,
)
from ..schemas.heritage import SummarizeRequest, TranslateRequest
from .common import INT, SAFETY, STR, dumps, nullable, obj
from .glossary import find_terms, render_for_prompt

SUMMARIZE_SYSTEM = f"""Bạn là biên tập viên nội dung di sản văn hóa Việt Nam, viết tiếng Việt chuẩn, chính xác, trung lập.
Nhiệm vụ: tóm tắt một di sản từ chính chữ đã có (tên, mô tả ngắn, nội dung, các giai đoạn và sự kiện) thành HAI bản tiếng Việt để khách tham quan đọc và nghe thuyết minh.
{SAFETY}

Yêu cầu:
- `shortText`: bản ngắn để nghe, một đoạn liền khoảng {SHORT_SUMMARY_MIN} đến {SHORT_SUMMARY_MAX} từ, văn nói tự nhiên, mở đầu bằng tên di sản, câu không quá dài, đọc to thành tiếng trôi chảy.
- `detailedText`: bản chi tiết để đọc, khoảng {DETAILED_SUMMARY_MIN} đến {DETAILED_SUMMARY_MAX} từ, 3 đến 5 đoạn cách nhau bằng một dòng trống, nêu vị trí, lịch sử hình thành, đặc điểm nổi bật, giá trị và ý nghĩa nếu tư liệu có. Nếu tư liệu ngắn thì viết ngắn hơn, tuyệt đối không bịa thêm.
- Cả hai là VĂN BẢN THUẦN: không dùng ký hiệu Markdown (không #, *, **, gạch đầu dòng, liên kết), không emoji. Số từ tính bằng cách tách theo khoảng trắng.
- Viết lại bằng lời của bạn, không chép nguyên cả bài; không thêm dữ kiện mới.
"""

TRANSLATE_SYSTEM = f"""Bạn là biên dịch viên chuyên về di sản văn hóa và lịch sử Việt Nam.
Nhiệm vụ: dịch toàn bộ chữ của một di sản sang ngôn ngữ đích được yêu cầu, giữ nguyên nghĩa, không thêm, không bớt, không chú thích của người dịch.
{SAFETY}

Quy tắc:
- Giữ nguyên mọi `id`, `timelineId` (số) trong `timelines`, `events`, `media` như đã gửi; mỗi phần tử gửi vào phải có đúng một phần tử trả về với cùng id.
- Trường nào là null thì trả null. Trường có chữ thì phải dịch, không để nguyên tiếng nguồn (trừ tên riêng theo bảng thuật ngữ).
- `content` có thể là Markdown: giữ nguyên cấu trúc (tiêu đề ##, gạch đầu dòng, chữ đậm, xuống dòng, đoạn) và chỉ dịch phần chữ.
- `summary` (nếu có trong dữ liệu) cũng PHẢI được dịch sang ngôn ngữ đích, cả `shortText` lẫn `detailedText`; tuyệt đối không trả lại nguyên văn tiếng nguồn. Đó là văn bản thuần, không dùng ký hiệu Markdown; giữ ranh giới đoạn (dòng trống) của `detailedText`; `shortText` là một đoạn liền.
- Tên riêng: dùng ĐÚNG bảng thuật ngữ nếu có mục tương ứng. Tên không có trong bảng: tiếng Anh giữ nguyên chính tả tiếng Việt của tên; tiếng Hàn, Trung, Nhật phiên âm theo thông lệ sang chữ của ngôn ngữ đích. Nhất quán trong toàn bộ bản dịch.
- Năm trước Công nguyên (TCN) dịch thành "BCE" (en), "기원전" (ko), "公元前" (zh-Hans), "紀元前" (ja). Giữ nguyên các con số và niên đại.
- Giọng văn: en trung tính, kiểu bách khoa; ko dùng đuôi lịch sự "-습니다"; zh-Hans dùng chữ Hán GIẢN THỂ; ja dùng thể "です・ます". Không dùng ngôn ngữ nào khác ngoài ngôn ngữ đích (trừ tên riêng cần giữ).
"""

_LANG_NAMES = {
    "en": "tiếng Anh (en)",
    "ko": "tiếng Hàn (ko)",
    "zh-Hans": "tiếng Trung giản thể (zh-Hans)",
    "ja": "tiếng Nhật (ja)",
    "vi": "tiếng Việt (vi)",
}


def summarize_schema() -> dict:
    return obj({"shortText": STR, "detailedText": STR})


def summarize_user(req: SummarizeRequest) -> str:
    return "\n".join(["<di_san>", dumps(req.source.model_dump(by_alias=True)), "</di_san>"])


def translate_schema(with_summary: bool) -> dict:
    text = obj(
        {
            "name": STR,
            "shortDescription": nullable(STR),
            "content": nullable(STR),
            "timelines": {"type": "array", "items": obj({"id": INT, "name": STR, "description": nullable(STR)})},
            "events": {"type": "array", "items": obj({"id": INT, "timelineId": INT, "name": STR, "description": nullable(STR)})},
            "media": {"type": "array", "items": obj({"id": INT, "caption": STR})},
        }
    )
    props = {"content": text}
    if with_summary:
        props["summary"] = obj({"shortText": STR, "detailedText": STR})
    return obj(props)


def glossary_terms(req: TranslateRequest):
    """Các mục bảng thuật ngữ có trong tư liệu nguồn (nội dung theo ngôn ngữ nội dung, tóm tắt theo ngôn ngữ tóm tắt)."""
    c = req.content
    parts = [c.name, c.short_description or "", c.content or ""]
    parts += [f"{t.name} {t.description or ''}" for t in c.timelines]
    parts += [f"{e.name} {e.description or ''}" for e in c.events]
    parts += [m.caption for m in c.media]
    sources = [("\n".join(parts), req.content_language.value)]
    if req.summary:
        summary_lang = (req.summary_language or req.content_language).value
        sources.append((req.summary.short_text + "\n" + req.summary.detailed_text, summary_lang))
    return find_terms(sources)


def translate_user(req: TranslateRequest) -> str:
    target = req.target_language.value
    source_lang = req.content_language.value
    terms = glossary_terms(req)
    payload: dict = {"content": req.content.model_dump(by_alias=True)}
    if req.summary:
        payload["summary"] = req.summary.model_dump(by_alias=True)
    lines = [
        "<yeu_cau>",
        f"Dịch từ {_LANG_NAMES[source_lang]} sang {_LANG_NAMES[target]}."
        + (
            f" Dịch cả `summary` (đang viết bằng {_LANG_NAMES[req.summary_language.value if req.summary_language else 'vi']}) "
            f"sang {_LANG_NAMES[target]}: kết quả phải có `summary.shortText` và `summary.detailedText` bằng ngôn ngữ đích."
            if req.summary
            else " Không có `summary`."
        ),
        "</yeu_cau>",
    ]
    if terms:
        lines += ["<bang_thuat_ngu>", render_for_prompt(terms, target), "</bang_thuat_ngu>"]
    lines += ["<di_san>", dumps(payload), "</di_san>"]
    return "\n".join(lines)
