"""Mô hình giả để chạy dịch vụ AI nối với backend khi không gọi được Claude (hết số dư, không mạng, kiểm hợp đồng).

Đọc yêu cầu trong prompt rồi dựng ĐẦU RA HỢP LỆ theo lược đồ: không phải chất lượng của mô hình thật, chỉ để kiểm đường đi
backend -> dịch vụ AI -> backend (hợp đồng JSON, mã lỗi, lược đồ từng cấp). Không dùng mạng, không dùng khóa nào.
"""
from __future__ import annotations

import itertools
import json
import re
from typing import Any, ClassVar

from app.llm.client import LlmResult, TokenUsage

MODEL = "mo-hinh-gia"


def _di_san(user: str) -> Any:
    m = re.search(r"<di_san>\n(.*?)\n</di_san>", user, re.DOTALL)
    return json.loads(m.group(1)) if m else None


def _tokens(text: str) -> list[str]:
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = text.replace("*", "")
    return [t for t in text.split() if t]


def _sentences(tokens: list[str], n_words: int, per_sentence: int) -> str:
    out: list[str] = []
    cyc = itertools.cycle(tokens or ["di", "sản", "văn", "hóa"])
    done = 0
    while done < n_words:
        take = min(per_sentence, n_words - done)
        ws = [next(cyc) for _ in range(take)]
        ws[0] = ws[0][:1].upper() + ws[0][1:]
        out.append(" ".join(ws).rstrip(".,;:") + ".")
        done += take
    return " ".join(out)


class MoHinhGia:
    model = MODEL

    def __init__(self) -> None:
        self.calls = 0

    async def complete_json(self, *, api: str, system: str, user: str, schema: dict, effort: str, max_tokens: int, timeout: float) -> LlmResult:
        self.calls += 1
        data = {
            "compose-lesson": self._compose,
            "generate-questions": self._questions,
            "summarize-heritage": self._summarize,
            "translate-heritage": self._translate,
        }[api](user)
        used = TokenUsage(input_tokens=len(user) // 3, output_tokens=len(json.dumps(data, ensure_ascii=False)) // 3)
        return LlmResult(data, used, MODEL)

    # ---- Soạn bài ----
    def _compose(self, user: str) -> dict:
        level = int(re.search(r"Cấp học: Cấp (\d)", user).group(1))
        target = int(re.search(r"mục tiêu khoảng (\d+) từ", user).group(1))
        heritages = _di_san(user)
        h = heritages[0]
        tokens = _tokens(h["content"] or h["shortDescription"] or h["name"])
        media = [i["mediaId"] for i in h["images"]]
        events = h["timeline"]
        base = {"keyPoints": [f"{h['name']} là một di sản của Việt Nam.", "Di sản có lịch sử lâu đời.", "Em cần giữ gìn di sản."]}
        if level == 1:
            story = _sentences(tokens, target, 9)
            sentences = [s if s.endswith(".") else s + "." for s in story.split(". ")]
            k, m = divmod(len(sentences), 6)
            steps, pos = [], 0
            for i in range(6):
                take = k + (1 if i < m else 0)
                steps.append({"kind": "STORY", "title": f"Bước {i + 1}", "text": " ".join(sentences[pos:pos + take]),
                              "mediaId": media[i % len(media)] if media else None, "year": None, "eventId": None})
                pos += take
            if media:
                steps.append({"kind": "IMAGE", "title": None, "text": "Em hãy quan sát hình này.", "mediaId": media[0], "year": None, "eventId": None})
            return {"content": story, "steps": steps, **base}
        if level == 2:
            ms = []
            fallback_years = [1010, 1428, 1802]
            for i in range(3):
                e = events[i] if i < len(events) else None
                ms.append({"kind": "MILESTONE", "title": f"Mốc {i + 1}", "text": e["name"] if e else f"Sự kiện quan trọng của di sản vào năm {fallback_years[i]}.",
                           "year": e["startYear"] if e else fallback_years[i], "eventId": e["eventId"] if e else None, "mediaId": None})
            if media:
                ms.append({"kind": "IMAGE", "title": None, "text": "Hình ảnh của di sản.", "mediaId": media[0], "year": None, "eventId": None})
            return {"content": _sentences(tokens, target, 17), "steps": ms, **base}
        quotes = []
        content = h["content"] or ""
        words = content.split()
        if len(words) >= 10:
            quote = " ".join(words[: min(40, len(words))])
            source = h["sources"][0]["title"] if h["sources"] else f"Tư liệu về {h['name']} trên nền tảng DSVHVN"
            quotes.append({"heritageId": h["heritageId"], "quote": quote, "source": source})
        return {
            "content": _sentences(tokens, target, 20),
            "steps": [{"kind": "REFLECTION", "title": None, "text": "Theo em, vì sao di sản này cần được gìn giữ cho các thế hệ sau?",
                       "mediaId": None, "year": None, "eventId": None}],
            "sourceQuotes": quotes, **base,
        }

    # ---- Sinh câu ----
    def _questions(self, user: str) -> dict:
        level = int(re.search(r"Cấp học của lớp: (\d)", user).group(1))
        need = int(re.search(r"Số câu cần sinh: (\d+)", user).group(1))
        feasible: dict[str, list[int]] = {}
        for t, ids in re.findall(r"^- (\w+) \(.*?\): dùng với di sản có heritageId thuộc \[(.*?)\]", user, re.MULTILINE):
            feasible[t] = [int(x) for x in ids.split(",") if x.strip()]
        by_id = {h["heritageId"]: h for h in _di_san(user)}
        types = list(feasible)
        out = []
        for i in range(need):
            t = types[i % len(types)]
            h = by_id[feasible[t][i % len(feasible[t])]]
            out.append(self._question(t, level, h, i))
        return {"questions": out}

    @staticmethod
    def _question(t: str, level: int, h: dict, i: int) -> dict:
        urls = [x["url"] for x in h["images"]]
        name = h["name"]
        desc = (h["shortDescription"] or name)[:120]
        expl = f"Theo tư liệu, {desc}"
        base = {"heritageId": h["heritageId"], "questionType": t, "explanation": expl}
        if t == "SINGLE_CHOICE":
            return {**base, "content": f"Câu {i + 1}: điều nào sau đây nói đúng về {name}?", "options": [
                {"content": desc, "isCorrect": True},
                {"content": f"{name} là một công trình hiện đại xây dựng gần đây.", "isCorrect": False},
                {"content": f"{name} không có giá trị lịch sử nào.", "isCorrect": False},
                {"content": f"{name} nằm ngoài lãnh thổ Việt Nam.", "isCorrect": False}]}
        if t == "TRUE_FALSE":
            return {**base, "content": f"Câu {i + 1}: {name} là di sản văn hóa của Việt Nam.", "answerIsTrue": True,
                    "imageUrl": urls[i % len(urls)] if level == 1 else None}
        if t == "IMAGE_CHOICE":
            caps = [x["caption"] or f"Hình {k + 1}" for k, x in enumerate(h["images"])]
            return {**base, "content": f"Câu {i + 1}: em hãy chọn hình có tên '{caps[0][:40]}'.", "options": [
                {"content": caps[k][:50], "imageUrl": urls[k], "isCorrect": k == 0} for k in range(min(3, len(urls)))]}
        if t == "MATCHING":
            return {**base, "content": f"Câu {i + 1}: em hãy ghép mỗi hình với tên của hình đó.", "pairs": [
                {"left": None, "leftImageUrl": urls[k], "right": (h["images"][k]["caption"] or f"Hình {k + 1}")[:50]} for k in range(3)]}
        if t == "ORDERING":
            ev = sorted(h["timeline"], key=lambda e: e["startYear"])
            if len({e["startYear"] for e in ev}) >= 3:
                steps = [f"{e['dateLabel']}: {e['name']}"[:200] for e in ev[: (4 if level == 1 else 5)]]
            else:
                steps = ["Xây dựng ban đầu", "Mở rộng qua các triều đại", "Được bảo tồn và nghiên cứu"]
            return {**base, "content": f"Câu {i + 1}: em hãy sắp xếp các sự kiện của {name} theo thứ tự thời gian.", "steps": steps}
        if t == "FILL_BLANK":
            first = name.split()[0]
            return {**base, "content": f"Câu {i + 1}: di sản ___ là một di sản văn hóa của Việt Nam.", "blanks": [{"accepted": [name]}],
                    "distractors": ["Chùa Hương", "Vịnh Hạ Long"] if first not in ("Chùa", "Vịnh") else ["Phố cổ Hội An", "Cố đô Huế"]}
        if t == "MULTI_TRUE_FALSE":
            return {**base, "content": f"Câu {i + 1}: đọc đoạn dẫn về {name} và đánh giá các nhận định sau.", "statements": [
                {"text": f"{name} là một di sản văn hóa của Việt Nam.", "isTrue": True},
                {"text": f"{name} được xây dựng trong thế kỷ hai mươi mốt.", "isTrue": False},
                {"text": f"{name} có giá trị lịch sử và văn hóa.", "isTrue": True}]}
        content = h["content"] or h["shortDescription"] or name
        return {**base, "content": f"Câu {i + 1}: theo đoạn tư liệu, nhận định nào đúng về {name}?",
                "passage": " ".join(content.split()[:60]), "passageSource": (h["sources"][0]["title"] if h["sources"] else f"Tư liệu về {name} trên nền tảng DSVHVN"),
                "options": [{"content": desc, "isCorrect": True}, {"content": "Di sản này mới xây dựng.", "isCorrect": False},
                            {"content": "Di sản này nằm ở nước ngoài.", "isCorrect": False}, {"content": "Di sản này không có giá trị.", "isCorrect": False}]}

    # ---- Tóm tắt ----
    def _summarize(self, user: str) -> dict:
        src = _di_san(user)
        tokens = _tokens(f"{src['name']}. {src.get('shortDescription') or ''} {src.get('content') or ''}")
        paras = [_sentences(tokens[i * 7:] + tokens[: i * 7], 100, 14) for i in range(3)]
        return {"shortText": _sentences(tokens, 100, 14), "detailedText": "\n\n".join(paras)}

    # ---- Dịch ----
    CANNED: ClassVar[dict] = {
        "en": ("History", "The heritage site was built by earlier dynasties and expanded over many centuries of continuous development.", "Heritage site", "Period", "Event", "Image"),
        "ko": ("역사", "이 유산은 여러 왕조에 의해 세워졌으며 오랜 세월 동안 계속해서 발전했습니다.", "문화유산", "시기", "사건", "사진"),
        "zh-Hans": ("历史", "这处遗产由历代王朝修建，并在漫长的岁月中不断发展。", "文化遗产", "时期", "事件", "图片"),
        "ja": ("歴史", "この遺産は歴代の王朝によって建てられ、長い年月にわたって発展を続けてきました。", "文化遺産", "時代", "出来事", "写真"),
    }

    def _translate(self, user: str) -> dict:
        target = re.search(r"sang [^()\n]*\(([\w-]+)\)", user).group(1)
        heading, sentence, name, period, event, image = self.CANNED[target]
        terms = [m.strip().split(" / ")[0] for m in re.findall(r"=> (.*)$", user, re.MULTILINE)]
        payload = _di_san(user)
        c = payload["content"]
        glossary_line = ("Terms: " if target == "en" else "") + ", ".join(terms)

        def fit(src: str | None, minimum: int = 0) -> str | None:
            if not src or not src.strip():
                return None
            reps = max(1, int(len(src) * (0.6 if target in ("en", "ko") else 0.35) / max(1, len(sentence))) + 1)
            return " ".join([sentence] * min(reps, 60))

        lines = []
        for line in (c.get("content") or "").split("\n"):
            if re.match(r"^\s{0,3}#{1,6}\s", line):
                lines.append(re.match(r"^(\s{0,3}#{1,6}\s)", line).group(1) + heading)
            elif line.strip():
                lines.append(fit(line) or sentence)
            else:
                lines.append("")
        content_text = "\n".join(lines).strip() or None
        if content_text and terms:
            content_text += "\n\n" + glossary_line
        out_content = {
            "name": (terms[0] if terms else name),
            "shortDescription": fit(c.get("shortDescription")),
            "content": content_text,
            "timelines": [{"id": t["id"], "name": f"{period} {t['id']}", "description": fit(t.get("description"))} for t in c["timelines"]],
            "events": [{"id": e["id"], "timelineId": e["timelineId"], "name": f"{event} {e['id']}", "description": fit(e.get("description"))} for e in c["events"]],
            "media": [{"id": m["id"], "caption": f"{image} {m['id']}"} for m in c["media"]],
        }
        result: dict = {"content": out_content}
        if payload.get("summary"):
            s = payload["summary"]
            result["summary"] = {
                "shortText": fit(s["shortText"]) or sentence,
                "detailedText": "\n\n".join([fit(p) or sentence for p in s["detailedText"].split("\n\n") if p.strip()] or [sentence]),
            }
        return result
