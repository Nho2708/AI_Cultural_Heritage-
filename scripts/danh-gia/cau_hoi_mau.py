"""Dựng câu hỏi mẫu cho bộ đánh giá gợi ý từ chính dữ liệu của di sản (tỉnh, loại hình, cấp công nhận, năm công nhận, vùng, ảnh).

Mỗi di sản trong một bài kiểm tra nhận 4 câu: hai câu nhiều phương án (một đáp án đúng, hoặc chọn hình ở cấp 1) và hai câu đúng/sai
(hai mệnh đề ở cấp 3). Nội dung chỉ để các em ảo có thứ để trả lời; chất lượng nội dung không phải đối tượng đo.

Không mạng, không đọc tệp: chỉ nhận dữ liệu di sản và `random.Random`. Dùng chung bởi `hoc-sinh-ao.py` và test.
"""
from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from danh_gia_chung import KIEU_3_PHUONG_AN, KIEU_4_PHUONG_AN, KIEU_DUNG_SAI

SO_CAU_MOI_DI_SAN = 4
MAU_NHIEU_PHUONG_AN = ("tinh", "loai", "cap", "nam", "di_san_trong_tinh")
MAU_DUNG_SAI = ("tinh", "loai", "vung", "nam", "cap")
GIOI_HAN_NHAN_ANH = 50  # nhãn thẻ hình tối đa 50 ký tự


@dataclass(frozen=True)
class DiSan:
    id: int
    ten: str
    tinh_id: int
    tinh: str
    vung: str
    loai: str  # mã loại hình (TANGIBLE...)
    cap: str  # mã cấp công nhận (UNESCO...)
    nam: int | None
    anh: tuple[tuple[str, str], ...] = ()  # (đường dẫn ảnh, chú thích) trong thư viện ảnh của di sản


@dataclass(frozen=True)
class NhanHienThi:
    """Tên hiển thị tiếng Việt của loại hình và cấp công nhận, lấy từ bộ lọc công khai của backend."""

    loai: dict[str, str]
    cap: dict[str, str]
    tinh: tuple[str, ...]


@dataclass
class CauHoi:
    payload: dict  # thân gửi POST /teacher/questions
    loai: str  # QuestionType
    kieu: str  # KIEU_*: dùng để chọn xác suất đoán khi mô phỏng
    di_san_id: int
    dap_an: dict = field(default_factory=dict)  # đáp án chuẩn để dựng câu trả lời đúng hoặc sai khi mô phỏng


def _nhan_anh(chu_thich: str, da_dung: set[str]) -> str:
    nhan = chu_thich.strip()
    if len(nhan) > GIOI_HAN_NHAN_ANH:
        cat = nhan[: GIOI_HAN_NHAN_ANH - 1]
        nhan = (cat.rsplit(" ", 1)[0] if " " in cat[20:] else cat).rstrip(" ,;–-") + "…"
    goc, dem = nhan, 2
    while nhan in da_dung:
        nhan = f"{goc[: GIOI_HAN_NHAN_ANH - 4]} ({dem})"
        dem += 1
    da_dung.add(nhan)
    return nhan


def _chon_sai(rng: random.Random, tat_ca: Sequence[str], dung: str, so: int = 3) -> list[str]:
    ung = [x for x in dict.fromkeys(tat_ca) if x != dung]
    return rng.sample(ung, min(so, len(ung)))


def _du_lieu_mau(mau: str, ds: DiSan, nhan: NhanHienThi, tat_ca: Sequence[DiSan]) -> tuple[str, str, list[str]] | None:
    """(phần câu hỏi, đáp án đúng, danh sách mọi giá trị có thể để lấy phương án sai) cho một mẫu; None nếu thiếu dữ liệu."""
    if mau == "tinh":
        return "nằm ở tỉnh, thành phố nào", ds.tinh, list(nhan.tinh)
    if mau == "loai":
        return "thuộc loại hình di sản nào", nhan.loai.get(ds.loai, ds.loai), list(nhan.loai.values())
    if mau == "cap":
        return "được công nhận ở cấp nào", nhan.cap.get(ds.cap, ds.cap), list(nhan.cap.values())
    if mau == "nam" and ds.nam is not None:
        return "được công nhận vào năm nào", str(ds.nam), [str(ds.nam + d) for d in (-9, -7, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 7, 9)]
    if mau == "vung":
        return "thuộc vùng nào của nước ta", ds.vung, [v for v in {d.vung for d in tat_ca} if v]
    return None


def _mau_hop_le(ds: DiSan, nhan: NhanHienThi, tat_ca: Sequence[DiSan], danh_sach: Sequence[str], bat_dau: int, can: int) -> list[str]:
    """Lấy đủ `can` mẫu hợp lệ (có dữ liệu) theo vòng tròn từ vị trí `bat_dau`."""
    ra: list[str] = []
    for i in range(len(danh_sach) * 2):
        mau = danh_sach[(bat_dau + i) % len(danh_sach)]
        if mau in ra:
            continue
        if mau == "di_san_trong_tinh" or _du_lieu_mau(mau, ds, nhan, tat_ca) is not None:
            ra.append(mau)
        if len(ra) == can:
            break
    return ra


def _cau_nhieu_phuong_an(cap: int, ds: DiSan, mau: str, nhan: NhanHienThi, tat_ca: Sequence[DiSan], do_kho: str, rng: random.Random) -> CauHoi:
    if mau == "di_san_trong_tinh":
        noi_dung = f"Trong các di sản sau, di sản nào nằm ở {ds.tinh}?"
        dung = ds.ten
        sai = _chon_sai(rng, [d.ten for d in tat_ca if d.tinh_id != ds.tinh_id], dung)
        giai_thich = f"{ds.ten} nằm ở {ds.tinh}."
    else:
        phan, dung, kho = _du_lieu_mau(mau, ds, nhan, tat_ca)  # type: ignore[misc]
        noi_dung = f"Di sản «{ds.ten}» {phan}?"
        sai = _chon_sai(rng, kho, dung)
        giai_thich = f"Đáp án đúng là {dung}."
    phuong_an = [(dung, True), *[(s, False) for s in sai]]
    rng.shuffle(phuong_an)
    payload = {
        "questionType": "SINGLE_CHOICE", "heritageId": ds.id, "content": noi_dung, "explanation": giai_thich,
        "difficultyLevel": do_kho, "levelMin": cap, "levelMax": cap,
        "options": [{"content": t, "isCorrect": d} for t, d in phuong_an],
    }
    return CauHoi(payload, "SINGLE_CHOICE", KIEU_4_PHUONG_AN, ds.id, {"dung": dung, "sai": sai[0]})


def _cau_chon_hinh(ds: DiSan, do_kho: str, rng: random.Random) -> CauHoi:
    """Cấp 1: chọn hình đúng trong 3 hoặc 4 hình của thư viện ảnh của di sản (cần ít nhất 3 hình)."""
    so = min(4, len(ds.anh))
    chon = rng.sample(list(ds.anh), so)
    da_dung: set[str] = set()
    nhan = [_nhan_anh(chu_thich, da_dung) for _, chu_thich in chon]
    dung = rng.randrange(so)
    the = [{"content": nhan[i], "imageUrl": chon[i][0], "isCorrect": i == dung} for i in range(so)]
    payload = {
        "questionType": "IMAGE_CHOICE", "heritageId": ds.id, "content": f"Em hãy chọn hình có tên: {nhan[dung]}",
        "explanation": f"Hình đúng là hình {nhan[dung]}.", "difficultyLevel": do_kho, "levelMin": 1, "levelMax": 1, "options": the,
    }
    kieu = KIEU_4_PHUONG_AN if so == 4 else KIEU_3_PHUONG_AN
    return CauHoi(payload, "IMAGE_CHOICE", kieu, ds.id, {"dung": nhan[dung], "sai": nhan[(dung + 1) % so]})


def _menh_de(mau: str, ds: DiSan, nhan: NhanHienThi, tat_ca: Sequence[DiSan], dung: bool, rng: random.Random) -> tuple[str, str]:
    """(mệnh đề, giải thích) đúng hoặc sai về một thuộc tính của di sản."""
    phan, gia_tri, kho = _du_lieu_mau(mau, ds, nhan, tat_ca)  # type: ignore[misc]
    chon = gia_tri if dung else _chon_sai(rng, kho, gia_tri, 1)[0]
    nhan_mau = {
        "tinh": f"«{ds.ten}» nằm ở {chon}.",
        "loai": f"«{ds.ten}» thuộc loại hình di sản {chon}.",
        "cap": f"«{ds.ten}» được công nhận ở cấp {chon}.",
        "nam": f"«{ds.ten}» được công nhận vào năm {chon}.",
        "vung": f"«{ds.ten}» thuộc vùng {chon} của nước ta.",
    }[mau]
    giai_thich = f"Đúng, {nhan_mau[0].lower()}{nhan_mau[1:]}" if dung else f"Sai. {phan.capitalize()}: {gia_tri}."
    return nhan_mau, giai_thich


def _cau_dung_sai(cap: int, ds: DiSan, mau: str, nhan: NhanHienThi, tat_ca: Sequence[DiSan], do_kho: str, rng: random.Random) -> CauHoi:
    dung = rng.random() < 0.5
    menh_de, giai_thich = _menh_de(mau, ds, nhan, tat_ca, dung, rng)
    payload: dict = {
        "questionType": "TRUE_FALSE", "heritageId": ds.id, "explanation": giai_thich, "difficultyLevel": do_kho,
        "levelMin": cap, "levelMax": cap, "answerIsTrue": dung,
    }
    if cap == 1:
        hinh = rng.choice(list(ds.anh))
        payload["imageUrl"] = hinh[0]
        payload["content"] = f"Em hãy xem hình. Hình này thuộc di sản {ds.ten}. Em cho biết: {menh_de}"
    else:
        payload["content"] = menh_de
    return CauHoi(payload, "TRUE_FALSE", KIEU_DUNG_SAI, ds.id, {"la_dung": dung})


def _cau_nhieu_menh_de(ds: DiSan, cac_mau: Sequence[str], nhan: NhanHienThi, tat_ca: Sequence[DiSan], do_kho: str, rng: random.Random) -> CauHoi:
    """Cấp 3: ba mệnh đề, có cả đúng và sai. Cả câu chỉ đúng khi cả ba mệnh đề đều đúng."""
    while True:
        bit = [rng.random() < 0.5 for _ in range(3)]
        if 0 < sum(bit) < 3:
            break
    menh_de = []
    for mau, dung in zip(cac_mau, bit, strict=True):
        text, _ = _menh_de(mau, ds, nhan, tat_ca, dung, rng)
        menh_de.append((text, dung))
    payload = {
        "questionType": "MULTI_TRUE_FALSE", "heritageId": ds.id, "difficultyLevel": do_kho, "levelMin": 3, "levelMax": 3,
        "content": f"Em hãy đọc các nhận định về di sản {ds.ten} và xác định đúng hoặc sai.",
        "explanation": "Mỗi nhận định được đối chiếu với thông tin của di sản trong kho di sản.",
        "statements": [{"text": t, "isTrue": d} for t, d in menh_de],
    }
    return CauHoi(payload, "MULTI_TRUE_FALSE", KIEU_DUNG_SAI, ds.id, {"menh_de": menh_de})


def tao_cau_hoi_cho_di_san(cap: int, ds: DiSan, tat_ca: Sequence[DiSan], nhan: NhanHienThi, lan_xuat_hien: int, do_kho: str, rng: random.Random) -> list[CauHoi]:
    """Bốn câu của một di sản trong một bài kiểm tra: nhiều phương án, đúng/sai, nhiều phương án, đúng/sai.

    `lan_xuat_hien` (0, 1) là lần di sản này xuất hiện trong các bài của lớp; lần sau dùng mẫu khác để hai bài không lặp câu.
    Cấp 1 cần ít nhất một ảnh cho câu đúng/sai và ít nhất ba ảnh cho câu chọn hình; di sản ít ảnh hơn thì thay bằng câu đúng/sai có hình.
    """
    if cap not in (1, 2, 3):
        raise ValueError("cấp phải là 1, 2 hoặc 3")
    if cap == 1 and not ds.anh:
        raise ValueError(f"di sản {ds.id} không có ảnh nên không dựng được câu cấp 1")
    mau_a = _mau_hop_le(ds, nhan, tat_ca, MAU_NHIEU_PHUONG_AN, 2 * lan_xuat_hien, 2)
    mau_t = _mau_hop_le(ds, nhan, tat_ca, [m for m in MAU_DUNG_SAI], 2 * lan_xuat_hien, 3 if cap == 3 else 2)
    ra: list[CauHoi] = []
    for i in range(2):
        if cap == 1:
            ra.append(_cau_chon_hinh(ds, do_kho, rng) if len(ds.anh) >= 3 else _cau_dung_sai(1, ds, mau_t[i], nhan, tat_ca, do_kho, rng))
        else:
            ra.append(_cau_nhieu_phuong_an(cap, ds, mau_a[i], nhan, tat_ca, do_kho, rng))
        if cap == 3:
            ra.append(_cau_nhieu_menh_de(ds, mau_t[:3] if i == 0 else mau_t[::-1][:3], nhan, tat_ca, do_kho, rng))
        else:
            ra.append(_cau_dung_sai(cap, ds, mau_t[i], nhan, tat_ca, do_kho, rng))
    return ra


def dap_an_gui_len(cau: CauHoi, dang_hien: dict, dung: bool) -> dict:
    """Thân của PUT .../answers/{câu}: đáp án đúng (`dung`) hoặc một đáp án sai, theo đúng thứ tự em đang thấy (`dang_hien` là câu trong đề)."""
    if cau.loai in ("SINGLE_CHOICE", "IMAGE_CHOICE"):
        muon = cau.dap_an["dung"] if dung else cau.dap_an["sai"]
        return {"selectedIndex": [o["content"] for o in dang_hien["options"]].index(muon)}
    if cau.loai == "TRUE_FALSE":
        muon = "Đúng" if cau.dap_an["la_dung"] == dung else "Sai"
        return {"selectedIndex": [o["content"] for o in dang_hien["options"]].index(muon)}
    if cau.loai == "MULTI_TRUE_FALSE":
        sat = dict(cau.dap_an["menh_de"])
        hien = [s if isinstance(s, str) else s["text"] for s in dang_hien["statements"]]
        return {"statements": [(sat[t] if dung else not sat[t]) for t in hien]}
    raise ValueError(cau.loai)
