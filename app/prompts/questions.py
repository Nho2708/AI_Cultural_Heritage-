"""Prompt và lược đồ JSON sinh câu hỏi 8 dạng theo cấp (tiếng Việt)."""
from __future__ import annotations

from ..rules import QUESTION_NAMES
from ..schemas.common import HeritageInput
from ..schemas.questions import QuestionsRequest
from .common import BOOL, INT, SAFETY, STR, dumps, heritage_payload, nullable, obj

SYSTEM = f"""Bạn là giáo viên biên soạn câu hỏi kiểm tra về di sản văn hóa Việt Nam cho trường học, viết tiếng Việt chuẩn, chính xác.
Nhiệm vụ: sinh câu hỏi từ tư liệu di sản được cung cấp, đúng dạng, đúng cấp học và độ khó được yêu cầu. Giáo viên sẽ duyệt từng câu trước khi dùng.
{SAFETY}

Quy tắc chung cho mọi dạng:
- Mỗi câu gắn đúng một di sản bằng `heritageId` (lấy từ danh sách di sản) và chỉ hỏi dữ kiện có trong tư liệu của di sản đó. Phân bổ đều các dạng được yêu cầu và các di sản.
- `content` dài 10 đến 1000 ký tự. `explanation` là lời giải thích vì sao đáp án đúng, dựa trên tư liệu, tối đa 2000 ký tự, không để trống.
- Câu hỏi rõ ràng, một ý, không đánh đố bằng chi tiết vụn vặt, không hai câu trong một câu. Các phương án nhiễu hợp lý, cùng loại với đáp án đúng, không phương án nào cũng đúng.
- Không viết lại cùng một câu hai lần; các câu cùng dạng phải hỏi các ý khác nhau.
- Ảnh: mọi giá trị `imageUrl`, `leftImageUrl` PHẢI sao chép NGUYÊN VĂN một trường `url` trong danh sách `images` của CHÍNH di sản mà câu gắn vào. Không tạo đường dẫn mới. Mỗi thẻ hình dùng một ảnh khác nhau.
- Văn bản thuần, không Markdown.

Mức khó: EASY là nhớ lại dữ kiện nêu thẳng trong tư liệu; MEDIUM là hiểu và so sánh; HARD là suy luận, phân tích nguyên nhân - kết quả, phương án nhiễu rất gần đáp án.
Văn phong theo cấp: cấp 1 (lớp 1 đến 5) câu ngắn, từ ngữ gần gũi, thân thiện; cấp 2 (lớp 6 đến 9) rõ ràng, thuật ngữ cơ bản; cấp 3 (lớp 10 đến 12) học thuật, cần phân tích.

Tám dạng câu và cấu trúc đáp án (chỉ dùng dạng được yêu cầu):
1. SINGLE_CHOICE (cấp 2, 3): `options` ĐÚNG 4 phương án (mỗi phương án tối đa 1000 ký tự, không trùng nhau), ĐÚNG MỘT phương án có isCorrect=true.
   Ví dụ: {{"heritageId":1,"questionType":"SINGLE_CHOICE","content":"Văn Miếu Hà Nội được xây dựng vào thời vua nào?","explanation":"Văn Miếu được xây năm 1070 dưới thời vua Lý Thánh Tông.","options":[{{"content":"Lý Thánh Tông","isCorrect":true}},{{"content":"Lê Thánh Tông","isCorrect":false}},{{"content":"Trần Nhân Tông","isCorrect":false}},{{"content":"Gia Long","isCorrect":false}}]}}
2. TRUE_FALSE (cấp 1, 2): một nhận định để chọn Đúng hoặc Sai, `answerIsTrue`. Ở cấp 1 BẮT BUỘC có `imageUrl` (ảnh minh họa); ở cấp 2 `imageUrl` có thể null. Đáp án đúng và sai nên xen kẽ.
   Ví dụ: {{"heritageId":1,"questionType":"TRUE_FALSE","content":"Văn Miếu là nơi thờ Khổng Tử và là trường học đầu tiên của nước ta.","explanation":"Văn Miếu thờ Khổng Tử và Quốc Tử Giám là trường đại học đầu tiên.","answerIsTrue":true,"imageUrl":null}}
3. IMAGE_CHOICE (chỉ cấp 1): `content` là câu hỏi chọn hình; `options` 3 đến 4 thẻ, mỗi thẻ có `imageUrl` khác nhau và `content` là nhãn ngắn 1 đến 50 ký tự (không trùng), ĐÚNG MỘT thẻ isCorrect=true.
4. MATCHING (chỉ cấp 1): `content` là lời yêu cầu ghép; `pairs` 3 đến 5 cặp {{left hoặc leftImageUrl, right}}: vế trái là chữ (`left`) hoặc hình (`leftImageUrl`, để `left` null), vế phải `right` là tên 1 đến 50 ký tự. Các vế trái không trùng, các vế phải không trùng.
5. ORDERING (cấp 1, 2): `content` là yêu cầu sắp xếp; `steps` 3 đến 6 mục (cấp 1 chỉ tối đa 4 mục), mỗi mục tối đa 200 ký tự, LIỆT KÊ THEO THỨ TỰ ĐÚNG, không trùng nhau (ứng dụng sẽ tự xáo trộn). Dùng cho sự kiện theo thời gian hoặc các bước của câu chuyện.
6. FILL_BLANK (chỉ cấp 2): `content` là câu có 1 đến 3 chỗ trống, mỗi chỗ trống đánh dấu bằng đúng ba dấu gạch dưới liền nhau ___ ; `blanks` có đúng số nhóm bằng số chỗ trống theo thứ tự, mỗi nhóm `accepted` gồm 1 đến 5 cách viết đúng (mỗi cách tối đa 100 ký tự, không trùng). `distractors` là từ gây nhiễu cho kho từ: nếu dùng thì tổng số từ trong kho (cách viết đúng đầu tiên của mỗi chỗ trống + từ gây nhiễu) phải từ 3 đến 8 từ và không trùng đáp án đúng; nếu không dùng kho từ thì để mảng rỗng.
7. MULTI_TRUE_FALSE (chỉ cấp 3): `content` là đoạn dẫn ngắn; `statements` 3 đến 5 mệnh đề {{text (10 đến 500 ký tự), isTrue}}, không để mọi mệnh đề cùng đúng hoặc cùng sai.
8. SOURCE_READING (chỉ cấp 3): `passage` là đoạn tư liệu trích từ tư liệu di sản (tối đa 150 từ, ưu tiên nguyên văn), `passageSource` là nguồn (tiêu đề một nguồn trong `sources` của di sản, hoặc "Tư liệu về <tên di sản> trên nền tảng DSVHVN" nếu không có nguồn); `content` là câu hỏi con về đoạn tư liệu; `options` ĐÚNG 4 phương án, ĐÚNG MỘT phương án isCorrect=true.
"""

_TIPS = {
    "SINGLE_CHOICE": obj({
        "options": {"type": "array", "items": obj({"content": STR, "isCorrect": BOOL})},
    }),
    "TRUE_FALSE": obj({"answerIsTrue": BOOL, "imageUrl": nullable(STR)}),
    "IMAGE_CHOICE": obj({
        "options": {"type": "array", "items": obj({"content": STR, "imageUrl": STR, "isCorrect": BOOL})},
    }),
    "MATCHING": obj({
        "pairs": {"type": "array", "items": obj({"left": nullable(STR), "leftImageUrl": nullable(STR), "right": STR})},
    }),
    "ORDERING": obj({"steps": {"type": "array", "items": STR}}),
    "FILL_BLANK": obj({
        "blanks": {"type": "array", "items": obj({"accepted": {"type": "array", "items": STR}})},
        "distractors": {"type": "array", "items": STR},
    }),
    "MULTI_TRUE_FALSE": obj({
        "statements": {"type": "array", "items": obj({"text": STR, "isTrue": BOOL})},
    }),
    "SOURCE_READING": obj({
        "passage": STR,
        "passageSource": STR,
        "options": {"type": "array", "items": obj({"content": STR, "isCorrect": BOOL})},
    }),
}


def item_schema(question_type: str, grade_level: int) -> dict:
    extra = dict(_TIPS[question_type]["properties"])
    if question_type == "TRUE_FALSE" and grade_level == 1:
        extra["imageUrl"] = STR  # cấp 1 bắt buộc có hình
    props = {
        "heritageId": INT,
        "questionType": {"type": "string", "enum": [question_type]},
        "content": STR,
        "explanation": STR,
        **extra,
    }
    return obj(props)


def schema(types: list[str], grade_level: int) -> dict:
    items = [item_schema(t, grade_level) for t in types]
    item = items[0] if len(items) == 1 else {"anyOf": items}
    return obj({"questions": {"type": "array", "items": item}})


def system_prompt() -> str:
    return SYSTEM


def user_prompt(
    req: QuestionsRequest,
    heritages: list[HeritageInput],
    feasible: dict[str, list[int]],
    need: int,
    accepted_contents: list[str],
) -> str:
    types_text = "\n".join(
        f"- {t} ({QUESTION_NAMES[t]}): dùng với di sản có heritageId thuộc {ids}" for t, ids in feasible.items()
    )
    parts = [
        "<yeu_cau>",
        f"Cấp học của lớp: {req.grade_level}. Độ khó: {req.difficulty.value}. Số câu cần sinh: {need}.",
        "Các dạng câu được dùng (chỉ dùng các dạng này, chia đều):",
        types_text,
        "</yeu_cau>",
    ]
    if accepted_contents:
        parts += ["<cau_da_co_khong_lap_lai>", *[f"- {c[:200]}" for c in accepted_contents], "</cau_da_co_khong_lap_lai>"]
    parts += ["<di_san>", dumps(heritage_payload(heritages, with_image_urls=True)), "</di_san>"]
    return "\n".join(parts)
