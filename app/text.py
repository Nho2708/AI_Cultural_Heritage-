"""Hàm xử lý chữ dùng chung cho các bộ kiểm đầu ra: đếm từ, bỏ dấu, nhận dạng chữ viết, ký hiệu Markdown."""
from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_MARKDOWN = re.compile(r"(^\s{0,3}#{1,6}\s)|(\*\*)|(__[^_]+__)|(^\s*[-*+]\s+)|(\[[^\]]+\]\([^)]+\))|(^\s*\d+\.\s)|(`)", re.M)

# Chữ chỉ có trong tiếng Việt (không có ở tiếng Anh, Pháp, Bồ...): đ, ơ, ư, ă và các dạng có dấu thanh của â, ê, ô, ă, ơ, ư.
_VIET_ONLY = set(
    "đĐơƠưƯăĂ"
    "ạảấầẩẫậắằẳẵặ"
    "ẹẻẽếềểễệ"
    "ịỉĩ"
    "ọỏốồổỗộớờởỡợ"
    "ụủứừửữự"
    "ỳỷỹỵ"
    "ẠẢẤẦẨẪẬẮẰẲẴẶ"
    "ẸẺẼẾỀỂỄỆ"
    "ỊỈĨ"
    "ỌỎỐỒỔỖỘỚỜỞỠỢ"
    "ỤỦỨỪỬỮỰ"
    "ỲỶỸỴ"
)


def words(text: str | None) -> list[str]:
    return text.split() if text else []


def count_words(text: str | None) -> int:
    """Đếm từ tách theo khoảng trắng, giống cách backend đếm (LessonText.CountWords)."""
    return len(words(text))


def collapse(value: str) -> str:
    """Khóa so sánh trùng của backend: gộp khoảng trắng liên tiếp, không phân biệt hoa thường."""
    return _WS.sub(" ", value.strip()).lower()


def clean(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


def fold(text: str | None) -> str:
    """Bỏ dấu tiếng Việt, đổi đ thành d, chữ thường."""
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").lower()


def has_markdown(text: str | None) -> bool:
    return bool(text and _MARKDOWN.search(text))


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+|\n+", text.strip())
    return [p for p in (p.strip() for p in parts) if p]


# ---- Chữ viết ----

def _is_hangul(c: str) -> bool:
    o = ord(c)
    return 0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F


def _is_kana(c: str) -> bool:
    o = ord(c)
    return 0x3040 <= o <= 0x30FF or 0x31F0 <= o <= 0x31FF or 0xFF66 <= o <= 0xFF9F


def _is_han(c: str) -> bool:
    o = ord(c)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF


def script_profile(text: str | None) -> dict[str, float]:
    """Tỉ lệ từng loại chữ trên các ký tự là chữ cái (hangul, kana, han, latin) và số ký tự chữ cái."""
    counts = {"hangul": 0, "kana": 0, "han": 0, "latin": 0}
    total = 0
    for c in text or "":
        if _is_hangul(c):
            counts["hangul"] += 1
        elif _is_kana(c):
            counts["kana"] += 1
        elif _is_han(c):
            counts["han"] += 1
        elif c.isalpha():
            counts["latin"] += 1
        else:
            continue
        total += 1
    profile: dict[str, float] = {k: (v / total if total else 0.0) for k, v in counts.items()}
    profile["letters"] = float(total)
    return profile


def viet_diacritic_ratio(text: str | None) -> float:
    """Tỉ lệ từ có ký tự chỉ tiếng Việt dùng (đ, ơ, ư, ă, dấu thanh trên â ê ô...)."""
    tokens = words(text)
    if not tokens:
        return 0.0
    hit = sum(1 for t in tokens if any(c in _VIET_ONLY for c in unicodedata.normalize("NFC", t)))
    return hit / len(tokens)


def accented_ratio(text: str | None) -> float:
    """Tỉ lệ từ có ít nhất một chữ cái ngoài ASCII (tiếng Việt thường trên 50%, tiếng Anh dưới 5%)."""
    tokens = words(text)
    if not tokens:
        return 0.0
    hit = sum(1 for t in tokens if any(c.isalpha() and ord(c) > 127 for c in t))
    return hit / len(tokens)


def looks_vietnamese(text: str | None, *, min_words: int = 12) -> bool:
    """Đoạn tiếng Việt: không lẫn chữ Hàn, Trung, Nhật và có dấu ở đủ nhiều từ (đoạn ngắn thì bỏ qua)."""
    if not text:
        return False
    p = script_profile(text)
    if p["hangul"] + p["kana"] + p["han"] > 0.02:
        return False
    if count_words(text) < min_words:
        return True
    return accented_ratio(text) >= 0.3


_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)
_MD_BULLET = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+", re.M)


def strip_markdown(text: str) -> str:
    """Bỏ ký hiệu Markdown còn sót (tiêu đề, chữ đậm, gạch đầu dòng, liên kết, mã) để còn văn bản thuần."""
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BULLET.sub("", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def find_verbatim(quote: str, source: str) -> str | None:
    """Tìm đoạn nguyên văn trong source khớp với quote, bỏ qua khác biệt về khoảng trắng và xuống dòng.

    Trả về đoạn lấy đúng từ source (chắc chắn là chuỗi con của source) hoặc None.
    """
    quote = quote.strip()
    if not quote:
        return None
    if quote in source:
        return quote
    tokens = quote.split()
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(t) for t in tokens)
    match = re.search(pattern, source)
    return match.group(0) if match else None
