"""Gợi ý di sản liên quan theo nội dung (content-based): loại, tỉnh, vùng, cấp xếp hạng, khoảng năm và độ giống chữ.

Độ giống chữ tính bằng TF-IDF + cosine (scikit-learn) trên tên và mô tả đã bỏ dấu. Không gọi mô hình ngôn ngữ, không lưu gì.
Trọng số và câu lý do cùng thang với bộ tính của backend để điểm hai bên so sánh được: tối đa 10 điểm mỗi cặp, nhân trọng số của di sản tham chiếu.
"""
from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from ..schemas.recommend import HeritageFeatures, RankRequest, Related
from ..text import fold

TYPE_WEIGHT = 3.0
PROVINCE_WEIGHT = 2.0
REGION_WEIGHT = 1.0
LEVEL_WEIGHT = 1.0
ERA_WEIGHT = 1.0
TEXT_WEIGHT = 2.0
TEXT_THRESHOLD = 0.12

STOP_WORDS = ["cua", "va", "cac", "mot", "nhung", "trong", "duoc", "la", "co", "cho", "voi", "tai", "nay", "khi", "den", "tu", "da", "the", "nam"]

_REASON = {
    "SAME_TYPE": "cùng loại",
    "SAME_PROVINCE": "cùng tỉnh",
    "SAME_REGION": "cùng vùng",
    "SAME_LEVEL": "cùng cấp xếp hạng",
    "OVERLAPPING_ERA": "cùng thời kỳ",
    "SIMILAR_TEXT": "nội dung gần nhau",
}


def _same(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def _era_overlaps(a: HeritageFeatures, b: HeritageFeatures) -> bool:
    if a.year_from is None or b.year_from is None:
        return False
    a_to = a.year_to if a.year_to is not None else a.year_from
    b_to = b.year_to if b.year_to is not None else b.year_from
    return a.year_from <= b_to and b.year_from <= a_to


def _document(h: HeritageFeatures) -> str:
    return f"{h.name or ''} {h.text or ''}"


def _text_similarities(references: list[HeritageFeatures], candidates: list[HeritageFeatures]):
    """Ma trận cosine TF-IDF (ứng viên x tham chiếu); rỗng nếu không có từ nào dùng được."""
    docs = [_document(h) for h in references] + [_document(h) for h in candidates]
    vectorizer = TfidfVectorizer(
        preprocessor=fold,
        token_pattern=r"(?u)\b[a-z0-9]{3,}\b",
        stop_words=STOP_WORDS,
        sublinear_tf=True,
    )
    try:
        matrix = vectorizer.fit_transform(docs)
    except ValueError:  # không có từ vựng
        return None
    refs = matrix[: len(references)]
    cands = matrix[len(references):]
    return linear_kernel(cands, refs)


def compare(a: HeritageFeatures, b: HeritageFeatures, text_similarity: float) -> tuple[float, list[str]]:
    score = 0.0
    factors: list[str] = []
    if _same(a.type, b.type):
        score += TYPE_WEIGHT
        factors.append("SAME_TYPE")
    if a.province_id is not None and a.province_id == b.province_id:
        score += PROVINCE_WEIGHT
        factors.append("SAME_PROVINCE")
    elif _same(a.region, b.region):
        score += REGION_WEIGHT
        factors.append("SAME_REGION")
    if a.level and a.level.upper() != "NONE" and _same(a.level, b.level):
        score += LEVEL_WEIGHT
        factors.append("SAME_LEVEL")
    if _era_overlaps(a, b):
        score += ERA_WEIGHT
        factors.append("OVERLAPPING_ERA")
    if text_similarity >= TEXT_THRESHOLD:
        score += TEXT_WEIGHT * min(1.0, text_similarity * 2.0)
        factors.append("SIMILAR_TEXT")
    return score, factors


def reason_of(factors: list[str], reference_name: str | None) -> str:
    text = ", ".join(_REASON[f] for f in factors[:2])
    first = text[:1].upper() + text[1:] if text else text
    return f"{first} với {reference_name}" if reference_name and reference_name.strip() else first


def _best_reference_match(
    candidate: HeritageFeatures,
    references: list,
    similarities,
    candidate_index: int,
) -> tuple[float, list[str], str | None] | None:
    """Gi? nguy?n h?nh vi c?: ch?n tham chi?u c? ?i?m c? tr?ng s? cao nh?t."""
    best: tuple[float, list[str], str | None] | None = None

    for reference_index, reference in enumerate(references):
        similarity = (
            float(similarities[candidate_index, reference_index])
            if similarities is not None
            else 0.0
        )
        score, factors = compare(candidate, reference.heritage, similarity)
        if not factors:
            continue

        weighted_score = score * reference.weight
        if best is None or weighted_score > best[0]:
            best = (weighted_score, factors, reference.heritage.name)

    return best


def rank_related(req: RankRequest) -> list[Related]:
    references = [r for r in req.references if r.weight > 0]
    reference_ids = {r.heritage.id for r in references}
    candidates = [c for c in req.candidates if c.id not in reference_ids]
    if not references or not candidates:
        return []

    ref_features = [r.heritage for r in references]
    similarities = _text_similarities(ref_features, candidates)

    results: list[Related] = []
    for candidate_index, candidate in enumerate(candidates):
        best = _best_reference_match(
            candidate, references, similarities, candidate_index
        )
        if best is not None:
            score, factors, reference_name = best
            results.append(
                Related(
                    heritage_id=candidate.id,
                    score=round(score, 4),
                    reason=reason_of(factors, reference_name),
                )
            )

    results.sort(key=lambda r: (-r.score, r.heritage_id))
    return results
