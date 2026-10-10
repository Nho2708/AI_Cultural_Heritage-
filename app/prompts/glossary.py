"""Bảng thuật ngữ tên riêng dùng khi dịch di sản (tên địa danh, di sản, triều đại).

Mỗi mục có nhiều cách viết chấp nhận được cho từng ngôn ngữ đích; cách đầu tiên là cách ưu tiên đưa vào prompt.
Chỉ các mục xuất hiện trong tư liệu mới được đưa vào prompt và được kiểm lại trong bản dịch.
Tiếng Anh viết tên Việt không dấu theo thông lệ (Hanoi, Hue, Thang Long); so sánh tiếng Anh bỏ qua dấu và hoa thường.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ..text import fold


@dataclass(frozen=True)
class Term:
    vi: tuple[str, ...]
    en: tuple[str, ...]
    ko: tuple[str, ...]
    zh: tuple[str, ...]  # tiếng Trung giản thể
    ja: tuple[str, ...]


def T(vi, en, ko, zh, ja) -> Term:  # noqa: N802 - viết tắt cho bảng dữ liệu
    def tup(x):
        return (x,) if isinstance(x, str) else tuple(x)

    return Term(tup(vi), tup(en), tup(ko), tup(zh), tup(ja))


GLOSSARY: tuple[Term, ...] = (
    T("Việt Nam", "Vietnam", "베트남", "越南", "ベトナム"),
    T("Đại Việt", "Dai Viet", "다이비엣", "大越", "大越"),
    T("Đông Dương", "Indochina", "인도차이나", "印度支那", "インドシナ"),
    T("Hà Nội", "Hanoi", "하노이", "河内", "ハノイ"),
    T("Thăng Long", "Thang Long", "탕롱", "升龙", "タンロン"),
    T("Hoàng thành Thăng Long", "Imperial Citadel of Thang Long", "탕롱 황성", "升龙皇城", "タンロン皇城"),
    T(["Thành phố Hồ Chí Minh", "TP. Hồ Chí Minh"], "Ho Chi Minh City", "호찌민시", "胡志明市", "ホーチミン市"),
    T("Hồ Chí Minh", "Ho Chi Minh", "호찌민", "胡志明", ["ホー・チ・ミン", "ホーチミン"]),
    T("Sài Gòn", "Saigon", "사이공", "西贡", "サイゴン"),
    T("Huế", "Hue", "후에", "顺化", "フエ"),
    T("Cố đô Huế", "Hue Ancient Capital", "후에 고도", "顺化古都", "フエの古都"),
    T("Đà Nẵng", "Da Nang", "다낭", "岘港", "ダナン"),
    T("Hội An", "Hoi An", "호이안", "会安", "ホイアン"),
    T("Mỹ Sơn", "My Son", "미선", "美山", "ミーソン"),
    T("Hạ Long", "Ha Long", "하롱", "下龙", "ハロン"),
    T("Phong Nha", "Phong Nha", "퐁냐", "峰牙", "フォンニャ"),
    T("Ninh Bình", "Ninh Binh", "닌빈", "宁平", "ニンビン"),
    T("Hoa Lư", "Hoa Lu", "호아르", "华闾", "ホアルー"),
    T("Quảng Nam", "Quang Nam", "꽝남", "广南", "クアンナム"),
    T("Quảng Ninh", "Quang Ninh", "꽝닌", "广宁", "クアンニン"),
    T("Quảng Bình", "Quang Binh", "꽝빈", "广平", "クアンビン"),
    T("Thanh Hóa", "Thanh Hoa", "타인호아", "清化", "タインホア"),
    T("Nghệ An", "Nghe An", "응에안", "乂安", "ゲアン"),
    T("Bắc Ninh", "Bac Ninh", "박닌", "北宁", "バクニン"),
    T("Phú Thọ", "Phu Tho", "푸토", "富寿", "フート"),
    T("Hải Phòng", "Hai Phong", "하이퐁", "海防", "ハイフォン"),
    T("Cần Thơ", "Can Tho", "껀터", "芹苴", "カントー"),
    T("Nha Trang", "Nha Trang", "나트랑", "芽庄", "ニャチャン"),
    T("Đà Lạt", "Da Lat", "달랏", "大叻", "ダラット"),
    T("Sa Pa", "Sa Pa", "사파", "沙巴", "サパ"),
    T("Điện Biên Phủ", "Dien Bien Phu", "디엔비엔푸", "奠边府", "ディエンビエンフー"),
    T("Tây Nguyên", "Central Highlands", "중부 고원", "西原", "中部高原"),
    T(["Chăm Pa", "Champa"], "Champa", "참파", "占婆", "チャンパ"),
    T("Văn Miếu", "Temple of Literature", "문묘", "文庙", ["文廟", "孔子廟"]),
    T("Quốc Tử Giám", "Imperial Academy", "국자감", "国子监", "国子監"),
    T("Chùa Một Cột", "One Pillar Pagoda", "일주사", "独柱寺", "一柱寺"),
    T("Hồ Hoàn Kiếm", "Hoan Kiem Lake", "호안끼엠", "还剑湖", "ホアンキエム"),
    T("Địa đạo Củ Chi", "Cu Chi Tunnels", "구찌", "古芝", "クチ"),
    T("Dinh Độc Lập", "Independence Palace", "독립궁", "独立宫", ["独立宮殿", "統一会堂"]),
    T("Lăng Chủ tịch Hồ Chí Minh", "Ho Chi Minh Mausoleum", "호찌민 묘", "胡志明陵", ["ホーチミン廟", "ホー・チ・ミン廟"]),
    T("Hùng Vương", "Hung Kings", ["훙 왕", "훙왕"], "雄王", ["雄王", "フン王"]),
    T("Văn hóa Đông Sơn", "Dong Son culture", "동썬", "东山文化", "ドンソン"),
    T("Nhà Lý", "Ly dynasty", "리 왕조", "李朝", "李朝"),
    T("Nhà Trần", "Tran dynasty", "쩐 왕조", "陈朝", "陳朝"),
    T("Nhà Lê", "Le dynasty", "레 왕조", "黎朝", "黎朝"),
    T("Nhà Hồ", "Ho dynasty", "호 왕조", "胡朝", "胡朝"),
    T("Nhà Nguyễn", "Nguyen dynasty", "응우옌 왕조", "阮朝", "阮朝"),
    T("Nhà Tây Sơn", "Tay Son dynasty", "떠이선", "西山", "西山朝"),
    T("Ca trù", "Ca tru", "까쭈", "歌筹", "カチュー"),
    T("Quan họ", "Quan ho", "꽌호", "官贺", "クアンホー"),
    T("Cục Di sản văn hóa", "Department of Cultural Heritage", "문화유산국", "文化遗产局", "文化遺産局"),
)

_LANG_INDEX = {"en": 1, "ko": 2, "zh-Hans": 3, "ja": 4}


def _forms(term: Term, lang: str) -> tuple[str, ...]:
    return {"vi": term.vi, "en": term.en, "ko": term.ko, "zh-Hans": term.zh, "ja": term.ja}[lang]


def find_terms(sources: list[tuple[str, str]]) -> list[Term]:
    """Các mục bảng thuật ngữ xuất hiện trong tư liệu nguồn.

    sources là danh sách (chữ, mã ngôn ngữ của chữ đó): chữ tiếng Việt khớp tên Việt, chữ tiếng Anh khớp tên Anh.
    """
    found: list[Term] = []
    prepared = [(unicodedata.normalize("NFC", text), fold(text), lang) for text, lang in sources]
    for term in GLOSSARY:
        for raw, folded, lang in prepared:
            if any(_occurs(k, raw, folded, lang) for k in _forms(term, lang)):
                found.append(term)
                break
    return found


def _occurs(key: str, raw: str, folded: str, lang: str) -> bool:
    """Tên Việt khớp đúng dấu và hoa thường (tránh nhầm "triều đại Việt Nam" với "Đại Việt"); riêng "Nhà ..." cho phép viết thường chữ đầu.
    Tên Anh khớp không phân biệt hoa thường và dấu."""
    if lang == "vi":
        key = unicodedata.normalize("NFC", key)
        head = "[" + key[0] + key[0].lower() + "]" if key.startswith("Nhà") else re.escape(key[0])
        pattern = r"(?<!\w)" + head + re.escape(key[1:]) + r"(?!\w)"
        return re.search(pattern, raw) is not None
    return re.search(r"(?<![a-z0-9])" + re.escape(fold(key)) + r"(?![a-z0-9])", folded) is not None


def render_for_prompt(terms: list[Term], target_language: str) -> str:
    lines = []
    for t in terms:
        src = " / ".join(dict.fromkeys([t.vi[0], t.en[0]]))
        dst = " / ".join(_forms(t, target_language))
        lines.append(f"- {src} => {dst}")
    return "\n".join(lines)


def missing_terms(terms: list[Term], target_language: str, translated_text: str) -> list[str]:
    """Các mục bảng thuật ngữ mà bản dịch chưa dùng cách viết nào được chấp nhận (trả về tên nguồn để báo lỗi)."""
    out_fold = fold(translated_text)
    out_lower = translated_text.lower()
    missing: list[str] = []
    for t in terms:
        forms = _forms(t, target_language)
        if target_language == "en":
            ok = any(fold(f) in out_fold for f in forms)
        else:
            ok = any(f.lower() in out_lower for f in forms)
        if not ok:
            missing.append(t.en[0])
    return missing
