"""Quy tắc nghiệp vụ mà backend dùng để kiểm kết quả AI (sao đúng số của backend để dịch vụ tự kiểm trước khi trả)."""
from __future__ import annotations

from dataclasses import dataclass

# ---- Bài học theo cấp (khung nội dung) ----


@dataclass(frozen=True)
class LevelFrame:
    level: int
    name: str
    min_words: int
    max_words: int
    targets: dict[str, int]  # SHORT, MEDIUM, DETAILED
    kinds: tuple[str, ...]  # loại phần AI được trả


LEVEL_FRAMES: dict[int, LevelFrame] = {
    1: LevelFrame(1, "Cấp 1 (lớp 1 đến 5)", 150, 250, {"SHORT": 150, "MEDIUM": 200, "DETAILED": 250}, ("STORY", "IMAGE")),
    2: LevelFrame(2, "Cấp 2 (lớp 6 đến 9)", 300, 500, {"SHORT": 300, "MEDIUM": 400, "DETAILED": 500}, ("IMAGE", "MILESTONE")),
    3: LevelFrame(3, "Cấp 3 (lớp 10 đến 12)", 600, 900, {"SHORT": 600, "MEDIUM": 750, "DETAILED": 900}, ("MILESTONE", "REFLECTION")),
}

# Dung sai khi kiểm số từ (đếm theo khoảng trắng): ngoài khoảng của cấp quá 8% thì gọi lại.
WORD_TOLERANCE = 0.08

# Độ dài câu trung bình dùng để đổi số từ mục tiêu ra số câu khi nhắc mô hình (mô hình theo số câu sát hơn theo số từ).
SENTENCE_WORDS = {1: 12, 2: 18, 3: 22}


def target_words(frame: LevelFrame, length: str) -> int:
    """Số từ mục tiêu báo cho mô hình: lùi vào trong khung ít nhất 10% so với hai đầu.

    Mô hình hay viết lệch khoảng 10% quanh mục tiêu (bản nhẹ còn ngắn hơn nhiều), nên mục tiêu "ngắn" bằng đúng mức tối thiểu
    của cấp (vd 150 từ ở cấp 1) thường cho bài dưới mức đó; backend cảnh báo giáo viên khi ngoài khung.
    """
    target = frame.targets[length]
    return max(int(frame.min_words * 1.1), min(target, int(frame.max_words * 0.95)))


def target_sentences(frame: LevelFrame, length: str) -> int:
    return max(3, round(target_words(frame, length) / SENTENCE_WORDS[frame.level]))

LEVEL1_MIN_STEPS, LEVEL1_MAX_STEPS = 3, 6
LEVEL1_STEP_MAX_WORDS = 50
LEVEL1_MAX_IMAGES = 3
LEVEL1_MAX_AVG_SENTENCE_WORDS = 18
LEVEL2_MIN_MILESTONES, LEVEL2_MAX_MILESTONES = 3, 8
LEVEL2_MAX_IMAGES = 2
LEVEL3_MAX_MILESTONES = 8
LEVEL3_MIN_REFLECTIONS, LEVEL3_MAX_REFLECTIONS = 1, 5
LEVEL3_MAX_QUOTES = 3
LEVEL3_QUOTE_MAX_WORDS = 150
LEVEL3_QUOTE_MIN_WORDS = 8

MIN_KEY_POINTS, MAX_KEY_POINTS = 3, 7
KEY_POINT_MAX_CHARS = 300
MIN_YEAR = -100_000
SOURCE_MAX_CHARS = 500

# ---- Câu hỏi ----

CONTENT_MIN, CONTENT_MAX = 10, 1000
EXPLANATION_MAX = 2000
URL_MAX = 500
OPTION_MAX = 1000
LABEL_MIN, LABEL_MAX = 1, 50
IMAGE_CHOICE_MIN, IMAGE_CHOICE_MAX = 3, 4
MATCHING_MIN, MATCHING_MAX = 3, 5
MATCH_LEFT_MAX = 1000
ORDERING_MIN, ORDERING_MAX, ORDERING_MAX_LEVEL1 = 3, 6, 4
ORDERING_ITEM_MAX = 200
BLANK_MARKER = "___"
FILL_MIN_BLANKS, FILL_MAX_BLANKS = 1, 3
ACCEPTED_MIN, ACCEPTED_MAX, ACCEPTED_ITEM_MAX = 1, 5, 100
WORD_BANK_MIN, WORD_BANK_MAX = 3, 8
STATEMENT_MIN_COUNT, STATEMENT_MAX_COUNT = 3, 5
STATEMENT_MIN, STATEMENT_MAX = 10, 500
PASSAGE_MAX_WORDS = 150
PASSAGE_SOURCE_MAX = 500
CHOICE_OPTION_COUNT = 4

# Cấp học dùng được của từng dạng câu (khoảng liền nhau).
QUESTION_LEVELS: dict[str, tuple[int, int]] = {
    "SINGLE_CHOICE": (2, 3),
    "TRUE_FALSE": (1, 2),
    "IMAGE_CHOICE": (1, 1),
    "MATCHING": (1, 1),
    "ORDERING": (1, 2),
    "FILL_BLANK": (2, 2),
    "MULTI_TRUE_FALSE": (3, 3),
    "SOURCE_READING": (3, 3),
}

QUESTION_NAMES = {
    "SINGLE_CHOICE": "Một đáp án đúng",
    "TRUE_FALSE": "Đúng/Sai",
    "IMAGE_CHOICE": "Chọn hình đúng",
    "MATCHING": "Ghép cặp hình - tên",
    "ORDERING": "Sắp xếp",
    "FILL_BLANK": "Điền từ",
    "MULTI_TRUE_FALSE": "Nhiều mệnh đề Đúng/Sai",
    "SOURCE_READING": "Đọc tư liệu rồi trả lời",
}


def question_allowed_at(question_type: str, level: int) -> bool:
    lo, hi = QUESTION_LEVELS[question_type]
    return lo <= level <= hi


# ---- Tóm tắt và dịch di sản ----

SHORT_SUMMARY_MIN, SHORT_SUMMARY_MAX = 80, 120
DETAILED_SUMMARY_MIN, DETAILED_SUMMARY_MAX = 250, 400
SUMMARY_TOLERANCE = 0.15
NAME_MAX = 255
SHORT_DESCRIPTION_MAX = 1000
CAPTION_MAX = 500
SUMMARY_SHORT_MAX_CHARS = 2000
