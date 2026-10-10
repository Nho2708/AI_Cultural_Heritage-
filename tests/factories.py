"""Dữ liệu mẫu và bộ sinh đầu ra mô hình hợp lệ cho các bài kiểm."""
from __future__ import annotations

import itertools
from typing import Any

POOL = [
    "ngày", "xưa", "có", "một", "tòa", "thành", "rất", "đẹp", "nơi", "các", "vua", "ở", "và", "làm", "việc",
    "người", "dân", "đến", "đây", "để", "học", "về", "lịch", "sử", "của", "đất", "nước", "những", "bạn", "nhỏ",
]


def viet_words(n: int, sentence_len: int = 10, offset: int = 0) -> str:
    """Đúng n từ tiếng Việt có dấu, chia thành các câu sentence_len từ."""
    cycle = itertools.cycle(POOL[offset % len(POOL):] + POOL[: offset % len(POOL)])
    sentences: list[str] = []
    done = 0
    while done < n:
        take = min(sentence_len, n - done)
        ws = [next(cycle) for _ in range(take)]
        ws[0] = ws[0].capitalize()
        sentences.append(" ".join(ws) + ".")
        done += take
    return " ".join(sentences)


HERITAGE_CONTENT = (
    "## Lịch sử\n\n"
    "Hoàng thành Thăng Long là quần thể di tích gắn liền với lịch sử kinh đô Thăng Long của nước Đại Việt suốt nhiều thế kỷ. "
    "Nơi đây được xây dựng từ thời nhà Lý, được các triều đại sau tiếp tục tu bổ và mở rộng. "
    "Các nhà khảo cổ đã tìm thấy nhiều lớp văn hóa chồng lên nhau, cho thấy sự phát triển liên tục của trung tâm quyền lực.\n\n"
    "## Giá trị\n\n"
    "Khu di tích được UNESCO ghi danh là Di sản thế giới vì giá trị nổi bật về lịch sử, văn hóa và khảo cổ học. "
    "Mỗi năm có hàng nghìn học sinh đến đây để tìm hiểu về lịch sử dân tộc."
)


def heritage_input(hid: int = 1, *, images: int = 4, events: int = 4, content: str | None = HERITAGE_CONTENT, name: str = "Hoàng thành Thăng Long") -> dict:
    return {
        "heritageId": hid,
        "name": name,
        "shortDescription": "Trung tâm quyền lực của các triều đại Việt Nam trong nhiều thế kỷ.",
        "content": content,
        "timeline": [
            {"eventId": hid * 100 + i, "phase": "Thời Lý", "name": f"Sự kiện {i}", "description": f"Mô tả sự kiện {i}",
             "startYear": 1000 + 10 * i, "dateLabel": str(1000 + 10 * i)}
            for i in range(1, events + 1)
        ],
        "sources": [{"title": "Cục Di sản văn hóa - dsvh.gov.vn (truy cập 10/2026)", "url": "https://dsvh.gov.vn"}],
        "images": [
            {"mediaId": hid * 1000 + i, "url": f"/media/h{hid}-{i}.jpg", "caption": f"Hình số {i} của di sản"}
            for i in range(1, images + 1)
        ],
    }


def compose_request(level: int, length: str = "MEDIUM", **kw: Any) -> dict:
    return {
        "generationId": 11, "lessonId": 5, "gradeLevel": level, "length": length,
        "heritages": [heritage_input(1, **kw)], "currentContent": "",
    }


def lesson_output(level: int, req: dict, *, words: int | None = None) -> dict:
    h = req["heritages"][0]
    media = [i["mediaId"] for i in h["images"]]
    events = h["timeline"]
    targets = {1: {"SHORT": 150, "MEDIUM": 200, "DETAILED": 250}, 2: {"SHORT": 300, "MEDIUM": 400, "DETAILED": 500},
               3: {"SHORT": 600, "MEDIUM": 750, "DETAILED": 900}}[level]
    default_words = targets[req.get("length", "MEDIUM")]
    if level == 1:
        n = words or default_words
        story = viet_words(n, sentence_len=9)
        sentences = [x if x.endswith(".") else x + "." for x in story.split(". ")]
        k, m = divmod(len(sentences), 6)
        steps, pos = [], 0
        for i in range(6):
            take = k + (1 if i < m else 0)
            text = " ".join(sentences[pos:pos + take])
            pos += take
            steps.append({"kind": "STORY", "title": f"Bước {i + 1}", "text": text, "mediaId": media[i % len(media)], "year": None, "eventId": None})
        steps.append({"kind": "IMAGE", "title": None, "text": "Hãy nhìn kỹ hình này nhé.", "mediaId": media[0], "year": None, "eventId": None})
        return {"content": story, "keyPoints": ["Thành rất đẹp.", "Vua làm việc ở đây.", "Em cần giữ gìn di sản."], "steps": steps}
    if level == 2:
        n = words or default_words
        steps = [
            {"kind": "MILESTONE", "title": f"Mốc {i}", "text": f"Sự kiện thứ {i} diễn ra vào năm này.", "mediaId": None,
             "year": e["startYear"], "eventId": e["eventId"]}
            for i, e in enumerate(events[:3], start=1)
        ]
        steps.append({"kind": "IMAGE", "title": None, "text": "Hình ảnh của di sản.", "mediaId": media[0], "year": None, "eventId": None})
        return {"content": viet_words(n, sentence_len=18), "keyPoints": ["Ý một của bài.", "Ý hai của bài.", "Ý ba của bài."], "steps": steps}
    n = words or default_words
    quote = " ".join(h["content"].split()[10:40])
    steps = [
        {"kind": "REFLECTION", "title": None, "text": "Theo em, vì sao di sản này được UNESCO ghi danh như vậy?", "mediaId": None, "year": None, "eventId": None},
    ]
    return {
        "content": viet_words(n, sentence_len=20),
        "keyPoints": ["Ý một của bài.", "Ý hai của bài.", "Ý ba của bài."],
        "steps": steps,
        "sourceQuotes": [{"heritageId": h["heritageId"], "quote": quote, "source": h["sources"][0]["title"]}],
    }


# ---- Câu hỏi ----

def _opts(correct: int = 0) -> list[dict]:
    texts = ["Lý Thánh Tông", "Lê Thánh Tông", "Trần Nhân Tông", "Gia Long"]
    return [{"content": t, "isCorrect": i == correct} for i, t in enumerate(texts)]


def question_item(qtype: str, level: int, req: dict, variant: int = 0) -> dict:
    h = req["heritages"][0]
    urls = [i["url"] for i in h["images"]]
    base = {
        "heritageId": h["heritageId"], "questionType": qtype,
        "content": f"Câu hỏi số {variant} về di sản này là gì nhỉ?",
        "explanation": "Vì tư liệu của di sản đã nêu rõ điều này trong phần lịch sử.",
    }
    if qtype == "SINGLE_CHOICE":
        return {**base, "options": _opts(variant % 4)}
    if qtype == "TRUE_FALSE":
        return {**base, "answerIsTrue": variant % 2 == 0, "imageUrl": urls[variant % len(urls)] if level == 1 else None}
    if qtype == "IMAGE_CHOICE":
        labels = ["Cổng thành", "Điện kính thiên", "Hồ nước", "Bia đá"]
        return {**base, "options": [{"content": labels[i], "imageUrl": urls[i], "isCorrect": i == variant % 3} for i in range(4)]}
    if qtype == "MATCHING":
        return {**base, "pairs": [
            {"left": "Nơi vua làm việc", "leftImageUrl": None, "right": "Điện Kính Thiên"},
            {"left": None, "leftImageUrl": urls[0], "right": "Cổng thành"},
            {"left": "Nơi lưu giữ bia", "leftImageUrl": None, "right": "Nhà bia"},
        ]}
    if qtype == "ORDERING":
        steps = ["Nhà Lý xây dựng kinh thành", "Nhà Trần tu bổ", "Nhà Lê mở rộng"] + (["Nhà Nguyễn thay đổi"] if level == 2 else [])
        return {**base, "steps": steps}
    if qtype == "FILL_BLANK":
        return {**base, "content": f"Hoàng thành Thăng Long được xây dựng từ thời nhà ___ và nằm ở ___ ngày nay{variant}.",
                "blanks": [{"accepted": ["Lý"]}, {"accepted": ["Hà Nội", "Hanoi"]}], "distractors": ["Trần", "Huế"]}
    if qtype == "MULTI_TRUE_FALSE":
        return {**base, "content": f"Đọc đoạn dẫn {variant} về Hoàng thành Thăng Long và đánh giá các nhận định.",
                "statements": [
                    {"text": "Hoàng thành gắn với kinh đô Thăng Long.", "isTrue": True},
                    {"text": "Hoàng thành được xây dựng vào thế kỷ hai mươi.", "isTrue": False},
                    {"text": "Khu di tích được UNESCO ghi danh.", "isTrue": True},
                ]}
    return {**base, "passage": "Hoàng thành Thăng Long là quần thể di tích gắn liền với lịch sử kinh đô Thăng Long của nước Đại Việt.",
            "passageSource": "Cục Di sản văn hóa", "options": _opts(variant % 4)}


def questions_request(level: int, types: list[str], count: int = 3, difficulty: str = "MEDIUM", **kw: Any) -> dict:
    return {
        "generationId": 21, "lessonId": 5, "gradeLevel": level, "count": count, "difficulty": difficulty,
        "types": types, "heritages": [heritage_input(1, **kw)],
    }


# ---- Dịch ----

def heritage_text() -> dict:
    return {
        "name": "Hoàng thành Thăng Long",
        "shortDescription": "Trung tâm quyền lực của các triều đại Việt Nam.",
        "content": "## Lịch sử\n\n" + viet_words(60, 12),
        "timelines": [{"id": 7, "name": "Thời Lý", "description": "Giai đoạn đầu."}],
        "events": [{"id": 70, "timelineId": 7, "name": "Dời đô về Thăng Long", "description": "Năm 1010."}],
        "media": [{"id": 700, "caption": "Cổng thành"}],
    }


TARGET_TEXT = {
    "en": {
        "name": "Imperial Citadel of Thang Long", "short": "The power center of Vietnamese dynasties for many centuries.",
        "content": "## History\n\nThe citadel was built under the Ly dynasty in Hanoi and expanded by later dynasties over many centuries of continuous development.",
        "tl": "Ly dynasty period", "tld": "The early period.", "ev": "Capital moved to Thang Long", "evd": "In 1010.", "cap": "City gate",
        "s_short": "The Imperial Citadel of Thang Long in Hanoi was the political center of Vietnam for many centuries.",
        "s_det": "The Imperial Citadel of Thang Long was built under the Ly dynasty.\n\nIt was expanded by later dynasties.",
    },
    "ko": {
        "name": "탕롱 황성", "short": "여러 세기 동안 베트남 왕조의 권력 중심지였습니다.",
        "content": "## 역사\n\n이 황성은 리 왕조 시대에 하노이에 세워졌으며 이후 여러 왕조가 계속해서 확장했습니다. 오랜 세월 동안 발전을 이어 왔습니다.",
        "tl": "리 왕조 시대", "tld": "초기 시기입니다.", "ev": "탕롱으로 천도", "evd": "1010년입니다.", "cap": "성문",
        "s_short": "하노이의 탕롱 황성은 여러 세기 동안 베트남의 정치 중심지였습니다.",
        "s_det": "탕롱 황성은 리 왕조 시대에 세워졌습니다.\n\n이후 여러 왕조가 확장했습니다.",
    },
    "zh-Hans": {
        "name": "升龙皇城", "short": "数个世纪以来一直是越南各朝代的权力中心。",
        "content": "## 历史\n\n这座皇城建于李朝时期，位于河内，后来的各个朝代不断对其进行扩建，在漫长的岁月中持续发展。",
        "tl": "李朝时期", "tld": "早期阶段。", "ev": "迁都升龙", "evd": "公元1010年。", "cap": "城门",
        "s_short": "河内的升龙皇城数个世纪以来一直是越南的政治中心。",
        "s_det": "升龙皇城建于李朝时期。\n\n后来的各个朝代对其进行了扩建。",
    },
    "ja": {
        "name": "タンロン皇城", "short": "何世紀にもわたってベトナム諸王朝の権力の中心でした。",
        "content": "## 歴史\n\nこの皇城は李朝の時代にハノイに建てられ、その後の王朝によって拡張され、長い年月にわたって発展を続けてきました。",
        "tl": "李朝の時代", "tld": "初期の時代です。", "ev": "タンロンへの遷都", "evd": "1010年です。", "cap": "城門",
        "s_short": "ハノイのタンロン皇城は何世紀にもわたってベトナムの政治の中心でした。",
        "s_det": "タンロン皇城は李朝の時代に建てられました。\n\n後の王朝によって拡張されました。",
    },
}


def translate_request(target: str, *, with_summary: bool = True, content_language: str = "vi") -> dict:
    req: dict = {
        "generationId": 31, "heritageId": 9, "targetLanguage": target, "contentLanguage": content_language,
        "content": heritage_text(), "summaryLanguage": None, "summary": None,
    }
    if with_summary:
        req["summaryLanguage"] = "vi"
        req["summary"] = {"shortText": viet_words(20, 10), "detailedText": viet_words(40, 10)}
    return req


def translation_output(target: str, req: dict) -> dict:
    t = TARGET_TEXT[target]
    out: dict = {
        "content": {
            "name": t["name"], "shortDescription": t["short"], "content": t["content"],
            "timelines": [{"id": 7, "name": t["tl"], "description": t["tld"]}],
            "events": [{"id": 70, "timelineId": 7, "name": t["ev"], "description": t["evd"]}],
            "media": [{"id": 700, "caption": t["cap"]}],
        }
    }
    if req.get("summary"):
        out["summary"] = {"shortText": t["s_short"], "detailedText": t["s_det"]}
    return out
