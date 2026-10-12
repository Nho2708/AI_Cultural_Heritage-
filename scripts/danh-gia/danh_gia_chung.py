"""Hàm thuần của bộ đánh giá gợi ý: precision@k, hit@k, đường cơ sở, mô phỏng học sinh ảo, độ khớp độ khó.

Không mạng, không đọc tệp, không số ngẫu nhiên toàn cục: mọi ngẫu nhiên đi qua `random.Random` dựng từ hạt giống truyền vào,
nên cùng hạt giống cho cùng kết quả. Hai script đo (`do-di-san-lien-quan.py`, `hoc-sinh-ao.py`) và test dùng chung tệp này.
"""
from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

K = 3  # mỗi phần gợi ý có tối đa 3 mục

DO_KHO = ("EASY", "MEDIUM", "HARD")
DO_KHO_TEN = {"EASY": "Dễ", "MEDIUM": "Trung bình", "HARD": "Khó"}
# Mức khó mặc định theo cấp học khi em chưa có kết quả: cấp 1 Dễ, cấp 2 và cấp 3 Trung bình.
MUC_KHO_MAC_DINH_THEO_CAP = {1: "EASY", 2: "MEDIUM", 3: "MEDIUM"}
# Mức khó em nhận là "khớp" theo vùng năng lực thật của em (tính từ tham số mô phỏng, không từ backend): em yếu nhận Dễ hoặc Trung bình,
# em đã vững nhận Khó, vùng giữa (chỉ để tham khảo, đề bài không quy định) nhận Trung bình.
MUC_KHO_CHAP_NHAN = {"yeu": frozenset({"EASY", "MEDIUM"}), "trung_binh": frozenset({"MEDIUM"}), "vung": frozenset({"HARD"})}
NGUONG_YEU = 0.5  # cùng ngưỡng với quy tắc của backend: dưới 50% hợp Dễ, từ 80% hợp Khó
NGUONG_VUNG = 0.8

KIEU_4_PHUONG_AN = "4_phuong_an"
KIEU_3_PHUONG_AN = "3_phuong_an"
KIEU_DUNG_SAI = "dung_sai"


# --------------------------------------------------------------------------------------------------------------------
# Độ chính xác và trúng
# --------------------------------------------------------------------------------------------------------------------

def precision_at_k(xep_hang: Sequence[int], lien_quan: Iterable[int], k: int = K) -> float:
    """Tỉ lệ trong k mục đầu của `xep_hang` thuộc `lien_quan`; luôn chia cho k (danh sách ngắn hơn k bị tính thiệt)."""
    if k <= 0:
        raise ValueError("k phải dương")
    tap = set(lien_quan)
    return sum(1 for x in list(xep_hang)[:k] if x in tap) / k


def hit_at_k(de_xuat: Sequence[int], muc_tieu: Iterable[int], k: int = K) -> bool:
    """Có ít nhất một mục tiêu nằm trong k mục đầu của `de_xuat`."""
    tap = set(muc_tieu)
    return any(x in tap for x in list(de_xuat)[:k])


def xac_suat_trung_ngau_nhien(tong: int, so_trung: int, k: int = K) -> float:
    """Xác suất rút ngẫu nhiên k mục (không hoàn lại) từ `tong` mục mà có ít nhất một trong `so_trung` mục trúng. Giá trị kỳ vọng chính xác."""
    if tong <= 0 or so_trung <= 0:
        return 0.0
    k = min(k, tong)
    if tong - so_trung < k:
        return 1.0
    return 1.0 - math.comb(tong - so_trung, k) / math.comb(tong, k)


def hop_xac_suat(*xac_suat: float) -> float:
    """Xác suất có ít nhất một sự kiện xảy ra, khi các sự kiện độc lập."""
    khong = 1.0
    for p in xac_suat:
        khong *= 1.0 - p
    return 1.0 - khong


def trung_binh(gia_tri: Iterable[float]) -> float:
    ds = list(gia_tri)
    return sum(ds) / len(ds) if ds else 0.0


def khoang_tin_cay_wilson(ty_le: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Khoảng tin cậy 95% Wilson cho một tỉ lệ; (0, 0) khi n = 0."""
    if n <= 0:
        return 0.0, 0.0
    mau = 1.0 + z * z / n
    tam = (ty_le + z * z / (2 * n)) / mau
    do_rong = z * math.sqrt(ty_le * (1 - ty_le) / n + z * z / (4 * n * n)) / mau
    return max(0.0, tam - do_rong), min(1.0, tam + do_rong)


# --------------------------------------------------------------------------------------------------------------------
# Đồng thuận giữa hai người gán nhãn
# --------------------------------------------------------------------------------------------------------------------

def jaccard(a: Iterable[int], b: Iterable[int]) -> float:
    """Độ giao nhau trên hợp; hai tập đều rỗng thì coi là 1."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def cohen_kappa(a: Sequence[bool], b: Sequence[bool]) -> float | None:
    """Hệ số kappa của Cohen cho hai dãy quyết định nhị phân cùng độ dài; None khi không xác định (hai người đều chỉ chọn một giá trị)."""
    if len(a) != len(b):
        raise ValueError("hai dãy phải cùng độ dài")
    n = len(a)
    if n == 0:
        return None
    quan_sat = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    pa, pb = sum(a) / n, sum(b) / n
    ky_vong = pa * pb + (1 - pa) * (1 - pb)
    if ky_vong >= 1.0:
        return None
    return (quan_sat - ky_vong) / (1 - ky_vong)


# --------------------------------------------------------------------------------------------------------------------
# Nội dung lớp (bài học, bài kiểm tra) và học sinh ảo
# --------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class BaiHoc:
    """Một bài học đã xuất bản của lớp cùng bài kiểm tra duy nhất của bài. `id` và `quiz_id` tăng theo thứ tự tạo (bài mới hơn có số lớn hơn)."""

    id: int
    quiz_id: int
    so_cau_di_san: tuple[tuple[int, int], ...]  # (mã di sản, số câu của di sản đó trong bài kiểm tra)
    do_kho: str
    han_dong: int  # số ngày từ lúc dựng lớp tới hạn đóng của bài kiểm tra; nhỏ hơn là đóng sớm hơn

    @property
    def di_san(self) -> tuple[int, ...]:
        return tuple(h for h, _ in self.so_cau_di_san)

    @property
    def so_cau(self) -> int:
        return sum(n for _, n in self.so_cau_di_san)


@dataclass(frozen=True)
class HocSinhAo:
    chi_so: int
    nhom: str  # "yeu", "trung_binh", "vung" hoặc "chua_lam"
    bai_da_lam: tuple[int, ...]  # mã bài học (cũng là bài kiểm tra) em đã làm, theo thứ tự làm
    di_san_yeu: frozenset[int]  # di sản yếu thật của em (đáp án đúng để đo), chọn trong các di sản em đã gặp
    boc_tham: tuple[tuple[float, ...], ...]  # mỗi câu một số u trong [0,1): dùng chung giữa các mức nhiễu để so sánh công bằng


def chia_nhom(n: int, ty_le: Mapping[str, float], rng: random.Random) -> list[str]:
    """Chia n em vào các nhóm theo tỉ lệ (làm tròn, nhóm cuối nhận phần dư), rồi xáo bằng `rng`."""
    ten = list(ty_le)
    so = [round(n * ty_le[t]) for t in ten[:-1]]
    so.append(max(0, n - sum(so)))
    ds = [t for t, c in zip(ten, so, strict=True) for _ in range(c)][:n]
    rng.shuffle(ds)
    return ds


def tao_hoc_sinh(chi_so: int, nhom: str, lop: Sequence[BaiHoc], hat: int | str, ty_le_yeu_nhom_yeu: float, so_bai: int = 2) -> HocSinhAo:
    """Dựng một học sinh ảo: chọn `so_bai` bài kiểm tra, các di sản yếu và bộ số ngẫu nhiên cho từng câu.

    `hat` nên suy từ (cấp, chỉ số em) chứ không từ mức nhiễu, để cùng một em ở ba mức nhiễu cùng bài, cùng di sản yếu, cùng số ngẫu nhiên.
    Nhóm `yeu`: phần lớn di sản em gặp là yếu; `trung_binh`: đúng một di sản yếu; `vung`: không có; `chua_lam`: chưa làm bài nào.
    """
    rng = random.Random(hat)
    if nhom == "chua_lam":
        return HocSinhAo(chi_so, nhom, (), frozenset(), ())
    # Chọn theo VỊ TRÍ trong lớp (không theo mã) để các lớp có nội dung giống nhau nhưng mã khác nhau cho cùng một em.
    vi_tri = rng.sample(range(len(lop)), so_bai)
    bai = [lop[p].id for p in vi_tri]
    theo_id = {b.id: b for b in lop}
    gap = sorted({h for i in bai for h in theo_id[i].di_san})
    if nhom == "yeu":
        so_yeu = max(1, math.ceil(ty_le_yeu_nhom_yeu * len(gap)))
    elif nhom == "trung_binh":
        so_yeu = 1
    elif nhom == "vung":
        so_yeu = 0
    else:
        raise ValueError(f"nhóm lạ: {nhom}")
    yeu = frozenset(rng.sample(gap, so_yeu))
    boc = tuple(tuple(rng.random() for _ in range(theo_id[i].so_cau)) for i in bai)
    return HocSinhAo(chi_so, nhom, tuple(bai), yeu, boc)


def tra_loi_dung(kieu_cau: str, la_di_san_yeu: bool, u: float, ty_le_nham: float, xac_suat_doan: Mapping[str, float]) -> bool:
    """Em trả lời đúng câu này không? Di sản yếu: đúng với xác suất đoán của dạng câu (4 phương án 25%, đúng/sai 50%...).
    Di sản đã vững: sai với xác suất `ty_le_nham` (10%, 15%, 20% = ba mức nhiễu). `u` là số ngẫu nhiên cố định của câu."""
    if la_di_san_yeu:
        return u < xac_suat_doan[kieu_cau]
    return u >= ty_le_nham


def tra_loi_ca_bai(hs: HocSinhAo, thu_tu_bai: int, cau: Sequence[tuple[int, str]], ty_le_nham: float, xac_suat_doan: Mapping[str, float]) -> list[bool]:
    """Kết quả đúng/sai từng câu của bài thứ `thu_tu_bai` em làm. `cau` là (mã di sản, kiểu câu) theo thứ tự câu trong bài."""
    u = hs.boc_tham[thu_tu_bai]
    if len(u) != len(cau):
        raise ValueError("số câu không khớp bộ số ngẫu nhiên")
    return [tra_loi_dung(kieu, di_san in hs.di_san_yeu, u[i], ty_le_nham, xac_suat_doan) for i, (di_san, kieu) in enumerate(cau)]


def ky_vong_ti_le_dung(hs: HocSinhAo, cau_theo_bai: Mapping[int, Sequence[tuple[int, str]]], ty_le_nham: float, xac_suat_doan: Mapping[str, float]) -> float | None:
    """Tỉ lệ đúng kỳ vọng của em trên các câu em đã làm, tính từ tham số mô phỏng (không phải từ kết quả đã xảy ra). None khi em chưa làm bài nào."""
    tong = dung = 0.0
    for ma_bai in hs.bai_da_lam:
        for di_san, kieu in cau_theo_bai[ma_bai]:
            dung += xac_suat_doan[kieu] if di_san in hs.di_san_yeu else 1.0 - ty_le_nham
            tong += 1
    return dung / tong if tong else None


def vung_nang_luc(ty_le_dung_ky_vong: float | None) -> str:
    """Vùng năng lực thật của em: "yeu" (< 50%), "vung" (>= 80%), "trung_binh" ở giữa, "chua_lam" khi chưa có bài nào."""
    if ty_le_dung_ky_vong is None:
        return "chua_lam"
    if ty_le_dung_ky_vong < NGUONG_YEU:
        return "yeu"
    return "vung" if ty_le_dung_ky_vong >= NGUONG_VUNG - 1e-9 else "trung_binh"


# --------------------------------------------------------------------------------------------------------------------
# Đường cơ sở
# --------------------------------------------------------------------------------------------------------------------

def quiz_chua_lam_theo_han_dong(lop: Sequence[BaiHoc], da_lam: Iterable[int], k: int = K) -> list[BaiHoc]:
    """Đường cơ sở "quiz chưa làm theo hạn đóng": các quiz em chưa làm, hạn đóng gần nhất trước (hòa thì quiz tạo trước)."""
    xong = set(da_lam)
    return sorted((b for b in lop if b.id not in xong), key=lambda b: (b.han_dong, b.id))[:k]


def quiz_moi_nhat(lop: Sequence[BaiHoc], da_lam: Iterable[int], k: int = K) -> list[BaiHoc]:
    """Đường cơ sở "bài mới nhất của lớp" cho quiz: các quiz em chưa làm, mới tạo nhất trước."""
    xong = set(da_lam)
    return sorted((b for b in lop if b.id not in xong), key=lambda b: -b.id)[:k]


def bai_hoc_moi_nhat(lop: Sequence[BaiHoc], k: int = K) -> list[BaiHoc]:
    """Đường cơ sở "bài mới nhất của lớp" cho bài học: mọi bài của lớp, mới tạo nhất trước."""
    return sorted(lop, key=lambda b: -b.id)[:k]


def di_san_nhieu_cau_nhat(lop: Sequence[BaiHoc], da_lam: Iterable[int], k: int = K) -> list[int]:
    """Đường cơ sở "3 di sản có nhiều câu nhất": trong các quiz em đã làm, di sản có nhiều câu nhất trước (hòa thì mã nhỏ trước)."""
    xong = set(da_lam)
    dem: dict[int, int] = {}
    for b in lop:
        if b.id in xong:
            for h, n in b.so_cau_di_san:
                dem[h] = dem.get(h, 0) + n
    return [h for h, _ in sorted(dem.items(), key=lambda x: (-x[1], x[0]))[:k]]


def di_san_cua_quiz_da_lam(lop: Sequence[BaiHoc], da_lam: Iterable[int]) -> list[int]:
    """Tập di sản (không lặp) trong các quiz em đã làm: kho để rút ngẫu nhiên 3 di sản."""
    xong = set(da_lam)
    return sorted({h for b in lop if b.id in xong for h in b.di_san})


def cham_trung(muc: Sequence[BaiHoc], di_san_yeu: frozenset[int]) -> bool:
    """Có bài nào trong `muc` chứa di sản yếu không."""
    return any(di_san_yeu & set(b.di_san) for b in muc)


def xac_suat_trung_bai_ngau_nhien(ung_vien: Sequence[BaiHoc], di_san_yeu: frozenset[int], k: int = K) -> float:
    so_trung = sum(1 for b in ung_vien if di_san_yeu & set(b.di_san))
    return xac_suat_trung_ngau_nhien(len(ung_vien), so_trung, k)


@dataclass(frozen=True)
class GoiY:
    """Phần gợi ý của backend cho một học sinh, đã quy về mã (không giữ chữ)."""

    quiz_ids: tuple[int, ...]
    bai_on_lai_ids: tuple[int, ...]
    bai_moi_ids: tuple[int, ...]
    di_san_nen_on_ids: tuple[int, ...]

    def bai_hoc_ids(self, k: int = K) -> tuple[int, ...]:
        """Ba bài học được gợi ý: bài nên ôn lại trước, rồi bài mới nên học, không lặp."""
        gop: list[int] = []
        for i in (*self.bai_on_lai_ids, *self.bai_moi_ids):
            if i not in gop:
                gop.append(i)
        return tuple(gop[:k])


def danh_gia_hit_hoc_sinh(hs: HocSinhAo, lop: Sequence[BaiHoc], goi_y: GoiY) -> dict[str, dict[str, float | bool]]:
    """Trúng di sản yếu của một em, so với ba đường cơ sở và hai đường cơ sở của phần nên ôn. Chỉ gọi khi em có di sản yếu.

    Giá trị bool: kết quả tất định; giá trị float: xác suất kỳ vọng chính xác của đường cơ sở ngẫu nhiên.
    """
    yeu = hs.di_san_yeu
    theo_quiz = {b.quiz_id: b for b in lop}
    theo_bai = {b.id: b for b in lop}

    def ket_qua(quiz: Sequence[BaiHoc], bai: Sequence[BaiHoc]) -> dict[str, float | bool]:
        q, b = cham_trung(quiz, yeu), cham_trung(bai, yeu)
        return {"quiz": q, "bai_hoc": b, "chung": q or b}

    dich_vu = ket_qua([theo_quiz[i] for i in goi_y.quiz_ids if i in theo_quiz], [theo_bai[i] for i in goi_y.bai_hoc_ids() if i in theo_bai])
    dich_vu_chi_bai_moi = cham_trung([theo_bai[i] for i in goi_y.bai_moi_ids[:K] if i in theo_bai], yeu)

    quiz_han = quiz_chua_lam_theo_han_dong(lop, hs.bai_da_lam)
    # Phía bài học của đường cơ sở theo hạn đóng: chính các bài chứa ba quiz đó (mỗi bài một quiz).
    co_so_han = ket_qua(quiz_han, quiz_han)

    moi_nhat = ket_qua(quiz_moi_nhat(lop, hs.bai_da_lam), bai_hoc_moi_nhat(lop))

    chua_lam = [b for b in lop if b.id not in set(hs.bai_da_lam)]
    p_quiz = xac_suat_trung_bai_ngau_nhien(chua_lam, yeu)
    p_bai = xac_suat_trung_bai_ngau_nhien(lop, yeu)
    ngau_nhien = {"quiz": p_quiz, "bai_hoc": p_bai, "chung": hop_xac_suat(p_quiz, p_bai)}

    kho = di_san_cua_quiz_da_lam(lop, hs.bai_da_lam)
    nen_on = {
        "dich_vu": hit_at_k(goi_y.di_san_nen_on_ids, yeu),
        "di_san_ngau_nhien": xac_suat_trung_ngau_nhien(len(kho), len(yeu & set(kho))),
        "nhieu_cau_nhat": hit_at_k(di_san_nhieu_cau_nhat(lop, hs.bai_da_lam), yeu),
    }
    return {
        "dich_vu": dich_vu,
        "quiz_chua_lam_theo_han": co_so_han,
        "bai_moi_nhat": moi_nhat,
        "bai_ngau_nhien": ngau_nhien,
        "nen_on": nen_on,
        "bien_the": {"dich_vu_chi_bai_moi": dich_vu_chi_bai_moi},
    }


# --------------------------------------------------------------------------------------------------------------------
# Độ khó khớp mức
# --------------------------------------------------------------------------------------------------------------------

def muc_kho_chap_nhan(vung: str, cap: int) -> frozenset[str]:
    """Các mức khó coi là khớp mức mục tiêu của em: theo vùng năng lực (đã có kết quả) hoặc theo cấp học (chưa làm bài nào)."""
    if vung == "chua_lam":
        return frozenset({MUC_KHO_MAC_DINH_THEO_CAP[cap]})
    return MUC_KHO_CHAP_NHAN[vung]


def dem_khop(do_kho: Sequence[str], chap_nhan: frozenset[str]) -> tuple[int, int]:
    """(số mục khớp, tổng số mục)."""
    return sum(1 for d in do_kho if d in chap_nhan), len(do_kho)


def do_kho_khop_hoc_sinh(hs: HocSinhAo, cap: int, lop: Sequence[BaiHoc], goi_y: GoiY, vung: str) -> dict[str, tuple[float, int]]:
    """Với một em: (số mục khớp, tổng số mục) của quiz và bài học được gợi ý, của đường cơ sở "bài mới nhất" và của chọn ngẫu nhiên (kỳ vọng).

    Bài học tính theo độ khó của bài kiểm tra duy nhất của bài. Số khớp của đường cơ sở ngẫu nhiên là kỳ vọng nên có thể không nguyên.
    """
    chap = muc_kho_chap_nhan(vung, cap)
    theo_quiz = {b.quiz_id: b for b in lop}
    theo_bai = {b.id: b for b in lop}
    chua_lam = [b for b in lop if b.id not in set(hs.bai_da_lam)]

    def khop(muc: Sequence[BaiHoc]) -> tuple[float, int]:
        k, n = dem_khop([b.do_kho for b in muc], chap)
        return float(k), n

    def khop_ngau_nhien(ung_vien: Sequence[BaiHoc], so_chon: int) -> tuple[float, int]:
        if not ung_vien:
            return 0.0, 0
        n = min(so_chon, len(ung_vien))
        ty_le = sum(1 for b in ung_vien if b.do_kho in chap) / len(ung_vien)
        return ty_le * n, n

    return {
        "quiz_dich_vu": khop([theo_quiz[i] for i in goi_y.quiz_ids if i in theo_quiz]),
        "bai_hoc_dich_vu": khop([theo_bai[i] for i in goi_y.bai_hoc_ids() if i in theo_bai]),
        "bai_moi_dich_vu": khop([theo_bai[i] for i in goi_y.bai_moi_ids if i in theo_bai]),
        "quiz_moi_nhat": khop(quiz_moi_nhat(lop, hs.bai_da_lam)),
        "bai_hoc_moi_nhat": khop(bai_hoc_moi_nhat(lop)),
        "quiz_ngau_nhien": khop_ngau_nhien(chua_lam, K),
        "bai_hoc_ngau_nhien": khop_ngau_nhien(lop, K),
    }


def gop_ty_le(cap_khop: Iterable[tuple[float, int]]) -> tuple[float, int]:
    """Gộp nhiều (số khớp, tổng) thành (tỉ lệ, tổng mục). Tỉ lệ 0 khi chưa có mục nào."""
    khop = tong = 0.0
    for k, n in cap_khop:
        khop += k
        tong += n
    return (khop / tong if tong else 0.0), int(tong)


# --------------------------------------------------------------------------------------------------------------------
# Đúng lớp
# --------------------------------------------------------------------------------------------------------------------

def thuoc_lop(goi_y: GoiY, lop: Sequence[BaiHoc]) -> tuple[int, int]:
    """(số mục gợi ý thuộc lớp của em, tổng số mục quiz và bài học được gợi ý)."""
    quiz = {b.quiz_id for b in lop}
    bai = {b.id for b in lop}
    ids_quiz = goi_y.quiz_ids
    ids_bai = (*goi_y.bai_on_lai_ids, *goi_y.bai_moi_ids)
    dung = sum(1 for i in ids_quiz if i in quiz) + sum(1 for i in ids_bai if i in bai)
    return dung, len(ids_quiz) + len(ids_bai)


@dataclass
class TongHop:
    """Bộ đếm cộng dồn cho một ô (mức nhiễu x cấp) hoặc một nhóm."""

    so_em: int = 0
    tong: dict[str, float] = field(default_factory=dict)

    def cong(self, ten: str, gia_tri: float) -> None:
        self.tong[ten] = self.tong.get(ten, 0.0) + float(gia_tri)

    def ty_le(self, ten: str) -> float:
        return self.tong.get(ten, 0.0) / self.so_em if self.so_em else 0.0
