"""Kiểm từng câu hỏi theo dạng và cấp, sao đúng quy tắc cấu trúc câu hỏi của backend (QuestionBuilder).

Câu đạt thì trả về đã chuẩn hóa (cắt khoảng trắng, bỏ trường của dạng khác); câu không đạt thì trả danh sách lỗi mô tả,
không chứa nội dung câu để có thể ghi log.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from .. import rules
from ..schemas.common import QuestionType
from ..schemas.questions import Blank, GeneratedQuestion, Option, Pair, Statement
from ..text import clean, collapse, count_words, looks_vietnamese


class _Item(BaseModel):
    model_config = ConfigDict(extra="ignore")
    heritageId: int
    questionType: str
    content: str | None = None
    explanation: str | None = None
    imageUrl: str | None = None
    passage: str | None = None
    passageSource: str | None = None
    answerIsTrue: bool | None = None
    options: list[dict] | None = None
    pairs: list[dict] | None = None
    steps: list[str] | None = None
    blanks: list[dict] | None = None
    distractors: list[str] | None = None
    statements: list[dict] | None = None


def count_markers(content: str) -> int:
    """Số chỗ trống: các cụm từ ba dấu gạch dưới liền nhau trở lên tính là một chỗ."""
    count = 0
    run = 0
    for c in content:
        if c == "_":
            run += 1
            continue
        if run >= 3:
            count += 1
        run = 0
    if run >= 3:
        count += 1
    return count


def signature(q: GeneratedQuestion) -> str:
    """Dấu vân của câu để nhận mỗi câu một lần: dạng, di sản, lời câu, hình, tư liệu và đáp án."""
    return json.dumps(
        [
            q.question_type.value, q.heritage_id, q.content, q.image_url, q.passage,
            [(o.content, o.image_url, o.is_correct) for o in q.options or []],
            [(p.left, p.left_image_url, p.right) for p in q.pairs or []],
            q.steps, q.answer_is_true,
            [b.accepted for b in q.blanks or []],
            [(s.text, s.is_true) for s in q.statements or []],
        ],
        ensure_ascii=False,
    ).lower()


def parse_items(data: Any) -> list[Any] | None:
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        return None
    return data["questions"]


def validate_question(
    raw: Any,
    index: int,
    *,
    grade_level: int,
    allowed_types: set[str],
    libraries: dict[int, set[str]],
) -> tuple[GeneratedQuestion | None, list[str]]:
    label = f"Câu {index + 1}"
    try:
        item = _Item.model_validate(raw)
    except ValidationError:
        return None, [f"{label}: sai lược đồ JSON."]
    qtype = item.questionType
    label = f"Câu {index + 1} ({qtype})"
    errors: list[str] = []

    if qtype not in allowed_types:
        return None, [f"{label}: dạng này không nằm trong các dạng được yêu cầu."]
    if item.heritageId not in libraries:
        return None, [f"{label}: heritageId không có trong danh sách di sản."]
    library = libraries[item.heritageId]

    content = clean(item.content)
    if content is None:
        errors.append(f"{label}: thiếu `content`.")
    elif not rules.CONTENT_MIN <= len(content) <= rules.CONTENT_MAX:
        errors.append(f"{label}: `content` phải dài {rules.CONTENT_MIN} đến {rules.CONTENT_MAX} ký tự.")
    elif not looks_vietnamese(content, min_words=6):
        errors.append(f"{label}: `content` phải viết bằng tiếng Việt có dấu.")

    explanation = clean(item.explanation)
    if explanation is None:
        errors.append(f"{label}: thiếu `explanation` (giải thích đáp án).")
    elif len(explanation) > rules.EXPLANATION_MAX:
        errors.append(f"{label}: `explanation` tối đa {rules.EXPLANATION_MAX} ký tự.")
    elif not looks_vietnamese(explanation, min_words=6):
        errors.append(f"{label}: `explanation` phải viết bằng tiếng Việt có dấu.")

    out: dict[str, Any] = {
        "heritage_id": item.heritageId,
        "question_type": QuestionType(qtype),
        "content": content,
        "explanation": explanation,
    }

    def fail(msg: str) -> None:
        errors.append(f"{label}: {msg}")

    if qtype in ("SINGLE_CHOICE", "SOURCE_READING"):
        out["options"] = _choice_options(item.options, fail)
        if qtype == "SOURCE_READING":
            passage = clean(item.passage)
            if passage is None:
                fail("thiếu `passage` (đoạn tư liệu).")
            elif count_words(passage) > rules.PASSAGE_MAX_WORDS:
                fail(f"`passage` tối đa {rules.PASSAGE_MAX_WORDS} từ.")
            source = clean(item.passageSource)
            if source is None:
                fail("thiếu `passageSource` (nguồn của đoạn tư liệu).")
            elif len(source) > rules.PASSAGE_SOURCE_MAX:
                fail(f"`passageSource` tối đa {rules.PASSAGE_SOURCE_MAX} ký tự.")
            out["passage"], out["passage_source"] = passage, source
    elif qtype == "TRUE_FALSE":
        if item.answerIsTrue is None:
            fail("thiếu `answerIsTrue`.")
        out["answer_is_true"] = item.answerIsTrue
        image = clean(item.imageUrl)
        if image is not None:
            out["image_url"] = _check_image(image, library, "imageUrl", fail)
        elif grade_level == 1:
            fail("câu Đúng/Sai ở cấp 1 phải có `imageUrl` lấy từ ảnh của di sản.")
    elif qtype == "IMAGE_CHOICE":
        out["options"] = _image_choice(item.options, library, fail)
    elif qtype == "MATCHING":
        out["pairs"] = _matching(item.pairs, library, fail)
    elif qtype == "ORDERING":
        out["steps"] = _ordering(item.steps, grade_level == 1, fail)
    elif qtype == "FILL_BLANK":
        blanks, distractors = _fill_blank(content, item.blanks, item.distractors, fail)
        out["blanks"], out["distractors"] = blanks, distractors
    elif qtype == "MULTI_TRUE_FALSE":
        out["statements"] = _statements(item.statements, fail)

    if errors:
        return None, errors
    return GeneratedQuestion(**out), []


# ---- Theo dạng ----

def _choice_options(options: list[dict] | None, fail) -> list[Option] | None:
    if options is None or len(options) != rules.CHOICE_OPTION_COUNT:
        fail(f"`options` phải có đúng {rules.CHOICE_OPTION_COUNT} phương án.")
        return None
    seen: set[str] = set()
    result: list[Option] = []
    ok = True
    for i, o in enumerate(options):
        text = clean(o.get("content"))
        if text is None:
            fail(f"phương án {i + 1} trống.")
            ok = False
        elif len(text) > rules.OPTION_MAX:
            fail(f"phương án {i + 1} tối đa {rules.OPTION_MAX} ký tự.")
            ok = False
        elif collapse(text) in seen:
            fail(f"phương án {i + 1} trùng nội dung với phương án khác.")
            ok = False
        else:
            seen.add(collapse(text))
            result.append(Option(content=text, is_correct=bool(o.get("isCorrect"))))
    if ok and sum(1 for r in result if r.is_correct) != 1:
        fail("phải đánh dấu đúng một phương án đúng (isCorrect=true).")
    return result


def _image_choice(options: list[dict] | None, library: set[str], fail) -> list[Option] | None:
    if options is None or not rules.IMAGE_CHOICE_MIN <= len(options) <= rules.IMAGE_CHOICE_MAX:
        fail(f"`options` phải có {rules.IMAGE_CHOICE_MIN} đến {rules.IMAGE_CHOICE_MAX} thẻ hình.")
        return None
    images: set[str] = set()
    labels: set[str] = set()
    result: list[Option] = []
    ok = True
    for i, o in enumerate(options):
        label = clean(o.get("content"))
        if label is None:
            fail(f"nhãn của thẻ {i + 1} trống.")
            ok = False
        elif not rules.LABEL_MIN <= len(label) <= rules.LABEL_MAX:
            fail(f"nhãn của thẻ {i + 1} phải dài {rules.LABEL_MIN} đến {rules.LABEL_MAX} ký tự.")
            ok = False
        elif collapse(label) in labels:
            fail(f"nhãn của thẻ {i + 1} trùng nhãn thẻ khác.")
            ok = False
        else:
            labels.add(collapse(label))
        url = clean(o.get("imageUrl"))
        if url is None:
            fail(f"thẻ {i + 1} thiếu `imageUrl`.")
            ok = False
        elif _check_image(url, library, f"options[{i}].imageUrl", fail) is None:
            ok = False
        elif url in images:
            fail(f"thẻ {i + 1} dùng lại hình của thẻ khác.")
            ok = False
        else:
            images.add(url)
        if ok:
            result.append(Option(content=label, image_url=url, is_correct=bool(o.get("isCorrect"))))
    if ok and sum(1 for r in result if r.is_correct) != 1:
        fail("phải đánh dấu đúng một thẻ đúng (isCorrect=true).")
    return result


def _matching(pairs: list[dict] | None, library: set[str], fail) -> list[Pair] | None:
    if pairs is None or not rules.MATCHING_MIN <= len(pairs) <= rules.MATCHING_MAX:
        fail(f"`pairs` phải có {rules.MATCHING_MIN} đến {rules.MATCHING_MAX} cặp.")
        return None
    lefts: set[str] = set()
    rights: set[str] = set()
    result: list[Pair] = []
    ok = True
    for i, p in enumerate(pairs):
        left = clean(p.get("left"))
        image = clean(p.get("leftImageUrl"))
        if left is None and image is None:
            fail(f"cặp {i + 1} thiếu vế trái (chữ hoặc hình).")
            ok = False
        else:
            if left is not None and len(left) > rules.MATCH_LEFT_MAX:
                fail(f"vế trái của cặp {i + 1} tối đa {rules.MATCH_LEFT_MAX} ký tự.")
                ok = False
            if image is not None and _check_image(image, library, f"pairs[{i}].leftImageUrl", fail) is None:
                ok = False
            else:
                key = collapse(image or left or "")
                if key in lefts:
                    fail(f"vế trái của cặp {i + 1} trùng vế trái khác.")
                    ok = False
                lefts.add(key)
        right = clean(p.get("right"))
        if right is None:
            fail(f"cặp {i + 1} thiếu vế phải.")
            ok = False
        elif not rules.LABEL_MIN <= len(right) <= rules.LABEL_MAX:
            fail(f"vế phải của cặp {i + 1} phải dài {rules.LABEL_MIN} đến {rules.LABEL_MAX} ký tự.")
            ok = False
        elif collapse(right) in rights:
            fail(f"vế phải của cặp {i + 1} trùng vế phải khác.")
            ok = False
        else:
            rights.add(collapse(right))
        if ok:
            result.append(Pair(left=left, left_image_url=image, right=right))
    return result if ok else None


def _ordering(steps: list[str] | None, level_one: bool, fail) -> list[str] | None:
    maximum = rules.ORDERING_MAX_LEVEL1 if level_one else rules.ORDERING_MAX
    if steps is None or not rules.ORDERING_MIN <= len(steps) <= maximum:
        fail(f"`steps` phải có {rules.ORDERING_MIN} đến {maximum} mục" + (" (cấp 1 tối đa 4 mục)." if level_one else "."))
        return None
    seen: set[str] = set()
    result: list[str] = []
    ok = True
    for i, s in enumerate(steps):
        text = clean(s)
        if text is None:
            fail(f"mục {i + 1} trống.")
            ok = False
        elif len(text) > rules.ORDERING_ITEM_MAX:
            fail(f"mục {i + 1} tối đa {rules.ORDERING_ITEM_MAX} ký tự.")
            ok = False
        elif collapse(text) in seen:
            fail(f"mục {i + 1} trùng nội dung mục khác.")
            ok = False
        else:
            seen.add(collapse(text))
            result.append(text)
    return result if ok else None


def _fill_blank(content: str | None, blanks: list[dict] | None, distractors: list[str] | None, fail):
    markers = count_markers(content) if content else 0
    if not rules.FILL_MIN_BLANKS <= markers <= rules.FILL_MAX_BLANKS:
        fail(f"câu điền từ phải có {rules.FILL_MIN_BLANKS} đến {rules.FILL_MAX_BLANKS} chỗ trống đánh dấu bằng ba dấu gạch dưới liền nhau (___).")
        return None, None
    if blanks is None or len(blanks) != markers:
        fail(f"câu có {markers} chỗ trống nên `blanks` phải có đúng {markers} nhóm đáp án.")
        return None, None
    ok = True
    result: list[Blank] = []
    all_accepted: set[str] = set()
    first: list[str] = []
    for b, blank in enumerate(blanks):
        accepted = blank.get("accepted") or []
        if not rules.ACCEPTED_MIN <= len(accepted) <= rules.ACCEPTED_MAX:
            fail(f"chỗ trống {b + 1} cần {rules.ACCEPTED_MIN} đến {rules.ACCEPTED_MAX} cách viết đúng.")
            ok = False
            continue
        seen: set[str] = set()
        cleaned: list[str] = []
        for a, value in enumerate(accepted):
            text = clean(value)
            if text is None:
                fail(f"đáp án {a + 1} của chỗ trống {b + 1} trống.")
                ok = False
            elif len(text) > rules.ACCEPTED_ITEM_MAX:
                fail(f"đáp án {a + 1} của chỗ trống {b + 1} tối đa {rules.ACCEPTED_ITEM_MAX} ký tự.")
                ok = False
            elif collapse(text) in seen:
                fail(f"đáp án {a + 1} của chỗ trống {b + 1} trùng đáp án khác.")
                ok = False
            else:
                seen.add(collapse(text))
                all_accepted.add(collapse(text))
                cleaned.append(text)
                if a == 0:
                    first.append(text)
        result.append(Blank(accepted=cleaned))
    extra = [clean(d) for d in (distractors or [])]
    kept: list[str] = []
    if ok and extra:
        bank = {collapse(t) for t in first}
        for i, text in enumerate(extra):
            if text is None:
                fail(f"từ gây nhiễu {i + 1} trống.")
                ok = False
            elif len(text) > rules.ACCEPTED_ITEM_MAX:
                fail(f"từ gây nhiễu {i + 1} tối đa {rules.ACCEPTED_ITEM_MAX} ký tự.")
                ok = False
            elif collapse(text) in all_accepted or collapse(text) in bank:
                fail(f"từ gây nhiễu {i + 1} trùng đáp án đúng hoặc từ khác trong kho từ.")
                ok = False
            else:
                bank.add(collapse(text))
                kept.append(text)
        if ok and not rules.WORD_BANK_MIN <= len(bank) <= rules.WORD_BANK_MAX:
            fail(f"kho từ (đáp án đúng đầu tiên + từ gây nhiễu) phải có {rules.WORD_BANK_MIN} đến {rules.WORD_BANK_MAX} từ, hiện có {len(bank)}.")
            ok = False
    if not ok:
        return None, None
    return result, (kept or None)


def _statements(statements: list[dict] | None, fail) -> list[Statement] | None:
    if statements is None or not rules.STATEMENT_MIN_COUNT <= len(statements) <= rules.STATEMENT_MAX_COUNT:
        fail(f"`statements` phải có {rules.STATEMENT_MIN_COUNT} đến {rules.STATEMENT_MAX_COUNT} mệnh đề.")
        return None
    seen: set[str] = set()
    result: list[Statement] = []
    ok = True
    for i, s in enumerate(statements):
        text = clean(s.get("text"))
        if text is None:
            fail(f"mệnh đề {i + 1} trống.")
            ok = False
        elif not rules.STATEMENT_MIN <= len(text) <= rules.STATEMENT_MAX:
            fail(f"mệnh đề {i + 1} phải dài {rules.STATEMENT_MIN} đến {rules.STATEMENT_MAX} ký tự.")
            ok = False
        elif collapse(text) in seen:
            fail(f"mệnh đề {i + 1} trùng nội dung mệnh đề khác.")
            ok = False
        else:
            seen.add(collapse(text))
            result.append(Statement(text=text, is_true=bool(s.get("isTrue"))))
    if ok and (all(r.is_true for r in result) or not any(r.is_true for r in result)):
        fail("không được để mọi mệnh đề cùng Đúng hoặc cùng Sai.")
        ok = False
    return result if ok else None


def _check_image(url: str, library: set[str], field: str, fail) -> str | None:
    if len(url) > rules.URL_MAX:
        fail(f"`{field}` tối đa {rules.URL_MAX} ký tự.")
        return None
    if url not in library:
        fail(f"`{field}` phải là một `url` trong danh sách ảnh của đúng di sản được gắn.")
        return None
    return url
