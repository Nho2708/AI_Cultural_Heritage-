"""Prompt và lược đồ JSON viết lại một phần của bài học (tiếng Việt)."""
from __future__ import annotations

from .. import rules
from ..schemas.lesson import RewriteSectionRequest
from .common import (
    SAFETY_WITH_TEACHER_NOTE,
    STR,
    TEACHER_NOTE_RULES,
    dumps,
    heritage_payload,
    nullable,
    obj,
    teacher_note_block,
)

_COMMON = f"""Bạn là biên soạn viên bài học về di sản văn hóa Việt Nam cho trường học, viết tiếng Việt chuẩn, chính xác, trung lập.
Nhiệm vụ: VIẾT LẠI MỘT PHẦN của bài học (khối <phan_can_viet_lai>), giữ ý của bản cũ, đúng khung của cấp học. Giáo viên sẽ so sánh với bản cũ rồi mới chọn dùng.
{SAFETY_WITH_TEACHER_NOTE}

Quy tắc chung:
- Giữ nguyên các ý và dữ kiện của bản cũ, trừ khi giáo viên yêu cầu khác. Có thể diễn đạt lại, sắp xếp lại, rút gọn hoặc làm sinh động theo yêu cầu.
- Chỉ dùng dữ kiện có trong bản cũ, nội dung bài (<noi_dung_bai>) và tư liệu di sản (<di_san>). Không thêm năm, số liệu, tên người, địa danh mới.
- Viết văn bản thuần tiếng Việt có dấu: không dùng ký hiệu Markdown (không #, **, gạch đầu dòng, liên kết), không dùng dấu ngoặc kép bao cả đoạn.
- Số từ tính bằng cách tách theo khoảng trắng (mỗi tiếng tiếng Việt là một từ). Đếm cẩn thận để không vượt giới hạn.
- Chỉ viết lại phần được giao, không viết thêm phần khác, không nhắc đến việc viết lại.
- Chỉ trả `text` (và `title` nếu phần có tiêu đề: giữ nguyên tiêu đề cũ khi không cần đổi, nếu phần không có tiêu đề thì `title` là null).
{TEACHER_NOTE_RULES}"""

_KIND_TEXT = {
    "STORY": """
PHẦN CẦN VIẾT LẠI: bước của câu chuyện kể (cấp 1, học sinh lớp 1 đến 5).
- `text`: 2 đến 4 câu, TỐI ĐA 50 từ, câu đơn giản, trung bình không quá 15 từ mỗi câu, ngôi kể thân thiện, từ ngữ gần gũi, không thuật ngữ, không số liệu dày đặc.
""",
    "IMAGE": """
PHẦN CẦN VIẾT LẠI: chú thích của một hình.
- `text`: ĐÚNG MỘT câu mô tả hình; cấp 1 tối đa 20 từ, câu ngắn cho trẻ quan sát; cấp 2 và 3 tối đa 40 từ.
""",
    "READING": """
PHẦN CẦN VIẾT LẠI: bài đọc có giải thích (cấp 2 hoặc 3).
- `text`: từ 20 đến 400 từ, mạch lạc, giải thích rõ nguyên nhân, diễn biến, ý nghĩa; có thể chia đoạn, các đoạn cách nhau bằng một dòng trống. Cấp 2 giọng giảng giải rõ ràng; cấp 3 giọng học thuật, có lập luận.
""",
    "MILESTONE": """
PHẦN CẦN VIẾT LẠI: mô tả một mốc thời gian.
- `text`: 1 đến 2 câu, TỐI ĐA 60 từ. KHÔNG ĐỔI NĂM của mốc: chỉ nhắc năm của mốc này (nếu cần), không nêu năm khác và không bịa năm.
- `title`: tên ngắn của mốc (giữ hoặc làm gọn tên cũ).
""",
    "REFLECTION": """
PHẦN CẦN VIẾT LẠI: câu hỏi gợi suy nghĩ (cấp 3).
- `text`: ĐÚNG MỘT câu hỏi mở, kết thúc bằng dấu hỏi (?), TỐI ĐA 60 từ, yêu cầu phân tích hoặc đánh giá, không có đáp án đơn giản.
""",
}


def system_prompt(kind: str) -> str:
    return _COMMON + _KIND_TEXT[kind]


def schema() -> dict:
    return obj({"text": STR, "title": nullable(STR)})


def user_prompt(req: RewriteSectionRequest) -> str:
    limit = rules.section_limit(req.kind.value, req.grade_level)
    section = {
        "kind": req.kind.value,
        "gradeLevel": req.grade_level,
        "currentText": req.current_text,
        "title": req.title,
        "year": req.year if req.kind.value == "MILESTONE" else None,
    }
    parts = [
        "<yeu_cau>",
        f"Viết lại {limit.name} của cấp {req.grade_level}, đúng giới hạn số câu và số từ đã nêu.",
        "</yeu_cau>",
    ]
    parts += teacher_note_block(req.teacher_note)
    parts += ["<phan_can_viet_lai>", dumps(section), "</phan_can_viet_lai>"]
    if req.lesson_content.strip():
        parts += ["<noi_dung_bai>", req.lesson_content.strip()[: rules.REWRITE_LESSON_CONTENT_MAX], "</noi_dung_bai>"]
    parts += ["<di_san>", dumps(heritage_payload(req.heritages, with_image_urls=False)), "</di_san>"]
    return "\n".join(parts)
