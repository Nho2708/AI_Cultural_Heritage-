"""Prompt và lược đồ JSON soạn nội dung bài học theo cấp (tiếng Việt)."""
from __future__ import annotations

from ..rules import LEVEL_FRAMES, target_sentences, target_words
from ..schemas.lesson import ComposeRequest
from .common import INT, SAFETY, STR, dumps, heritage_payload, nullable, obj

_COMMON = f"""Bạn là biên soạn viên bài học về di sản văn hóa Việt Nam cho trường học, viết tiếng Việt chuẩn, chính xác, trung lập.
Nhiệm vụ: soạn BẢN NHÁP nội dung bài học từ tư liệu di sản được cung cấp, đúng khung của cấp học của lớp. Giáo viên sẽ duyệt và sửa trước khi dùng.
{SAFETY}

Quy tắc chung:
- Viết văn bản thuần: không dùng ký hiệu Markdown (không #, **, gạch đầu dòng, liên kết). Các đoạn cách nhau bằng một dòng trống.
- Ý chính (keyPoints): 3 đến 7 ý, mỗi ý một câu hoàn chỉnh, tối đa 300 ký tự, không trùng nhau, rút từ nội dung bài.
- Khi có nhiều di sản, kết nối chúng thành một bài mạch lạc, không viết rời từng di sản.
- Số từ tính bằng cách tách theo khoảng trắng (mỗi tiếng tiếng Việt là một từ). Hãy đếm cẩn thận để nằm đúng khoảng được yêu cầu.
- Nội dung hiện có của bài (nếu có) chỉ để tham khảo; viết lại cho đúng cấp.
"""

_LEVEL1 = """
CẤP 1 (học sinh lớp 1 đến 5) - bài là một CÂU CHUYỆN kể:
- `content`: toàn bộ câu chuyện kể liền, ngôi kể thân thiện, câu đơn giản (khoảng 15 từ trở xuống, trung bình không quá 15 từ mỗi câu), từ ngữ gần gũi, giải thích ngắn gọn từ khó, không thuật ngữ, không số liệu dày đặc.
- `steps`: chia CHÍNH câu chuyện đó thành 3 đến 6 bước kind=STORY, mỗi bước 2 đến 4 câu, TỐI ĐA 50 từ, đặt `text` là lời kể của bước. Mỗi bước gắn một ảnh: `mediaId` lấy từ danh sách ảnh của di sản (nếu danh sách ảnh có ảnh thì BẮT BUỘC chọn; ít ảnh thì dùng lại ảnh). Nếu di sản không có ảnh nào thì mediaId = null. Ghép các bước lại phải xấp xỉ bằng `content`.
- Thêm 0 đến 3 phần kind=IMAGE: `mediaId` từ danh sách ảnh, `text` là một câu ngắn (tối đa 20 từ) mô tả hình để trẻ quan sát.
- Mọi trường không dùng để null: STORY không có year/eventId; IMAGE không có year/eventId.
"""

_LEVEL2 = """
CẤP 2 (học sinh lớp 6 đến 9) - bài ĐỌC có giải thích:
- `content`: bài đọc mạch lạc có mở bài, thân bài, kết bài; giải thích nguyên nhân, diễn biến, ý nghĩa; có thể dùng thuật ngữ cơ bản kèm giải nghĩa; giọng giảng giải rõ ràng.
- `steps`: kind=MILESTONE từ 3 đến 8 mốc (ít nhất 1 mốc nếu tư liệu có niên đại; tư liệu không đủ 3 mốc thì chỉ nêu số mốc có thật) theo dòng thời gian của di sản (sắp xếp tăng dần theo năm): `year` là số nguyên (năm trước Công nguyên là số âm, ví dụ 179 TCN là -179), `title` là tên ngắn của mốc, `text` là 1 đến 2 câu mô tả mốc. Nếu mốc tương ứng một sự kiện trong dòng thời gian được cho thì đặt `eventId` của sự kiện đó (và `year` = startYear của sự kiện), nếu không thì eventId = null. Chỉ nêu mốc có trong tư liệu.
- Thêm 1 đến 2 phần kind=IMAGE (nếu di sản có ảnh): `mediaId` từ danh sách ảnh, `text` là chú thích 1 câu dựa trên chú thích ảnh. Không có ảnh thì không thêm phần IMAGE.
"""

_LEVEL3 = """
CẤP 3 (học sinh lớp 10 đến 12) - bài PHÂN TÍCH:
- `content`: bài phân tích bối cảnh lịch sử, giá trị và ý nghĩa của di sản, giọng học thuật, có lập luận, nối các sự kiện, đối chiếu nguyên nhân - hệ quả; không lan man, không kết luận ngoài tư liệu.
- `sourceQuotes`: 1 đến 3 đoạn trích tư liệu gốc. `quote` PHẢI là chuỗi con NGUYÊN VĂN, liền mạch trong `content` của đúng di sản có `heritageId` (sao chép từng chữ, đúng dấu câu, không sửa, không bỏ chữ, không ghép hai đoạn, không viết lại), dài 8 đến 150 từ. `source` là tiêu đề của một nguồn trong danh sách `sources` của di sản đó; nếu di sản không có nguồn thì ghi "Tư liệu về <tên di sản> trên nền tảng DSVHVN".
- `steps`: kind=REFLECTION từ 1 đến 5 câu hỏi gợi suy nghĩ mở (`text` là câu hỏi, kết thúc bằng dấu hỏi, yêu cầu phân tích hoặc đánh giá, không có đáp án đơn giản); tùy chọn 0 đến 8 phần kind=MILESTONE (year là số nguyên, năm TCN là số âm; title; text; eventId như cấp 2).
"""

_LEVEL_TEXT = {1: _LEVEL1, 2: _LEVEL2, 3: _LEVEL3}


def system_prompt(level: int) -> str:
    return _COMMON + _LEVEL_TEXT[level]


def schema(level: int) -> dict:
    frame = LEVEL_FRAMES[level]
    step = obj(
        {
            "kind": {"type": "string", "enum": list(frame.kinds)},
            "title": nullable(STR),
            "text": nullable(STR),
            "mediaId": nullable(INT),
            "year": nullable(INT),
            "eventId": nullable(INT),
        }
    )
    props: dict = {
        "content": STR,
        "keyPoints": {"type": "array", "items": STR},
        "steps": {"type": "array", "items": step},
    }
    if level == 3:
        props["sourceQuotes"] = {
            "type": "array",
            "items": obj({"heritageId": INT, "quote": STR, "source": STR}),
        }
    return obj(props)


def user_prompt(req: ComposeRequest) -> str:
    frame = LEVEL_FRAMES[req.grade_level]
    target = target_words(frame, req.length.value)
    sentences = target_sentences(frame, req.length.value)
    parts = [
        "<yeu_cau>",
        (
            f"Cấp học: {frame.name}. Độ dài `content` mục tiêu khoảng {target} từ (khoảng {sentences} câu), "
            f"bắt buộc nằm trong {frame.min_words} đến {frame.max_words} từ. Viết đủ dài: thiếu từ thì thêm chi tiết có trong tư liệu, không bịa."
        ),
        "</yeu_cau>",
    ]
    if req.current_content.strip():
        parts += ["<noi_dung_hien_co>", req.current_content.strip()[:4000], "</noi_dung_hien_co>"]
    parts += ["<di_san>", dumps(heritage_payload(req.heritages, with_image_urls=False)), "</di_san>"]
    return "\n".join(parts)
