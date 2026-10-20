"""Ghép sóng âm theo câu kèm mốc thời gian, chuẩn hóa âm lượng, ghi MP3 mono. Chỉ chạy trong venv của máy đọc (cần numpy, lameenc)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

DAU_TEP_MS = 150        # im lặng đầu tệp
GIUA_CAU_MS = 350       # im lặng giữa hai câu hiển thị
GIUA_MAU_MS = 120       # im lặng giữa hai mẩu của cùng một câu dài
CUOI_TEP_MS = 200
KBPS = 80               # trong khoảng 64–96 kbps của hợp đồng


def mono_float(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x)
    if x.ndim == 2:
        x = x.mean(axis=0 if x.shape[0] < x.shape[1] else 1)
    if x.dtype.kind in "iu":
        x = x.astype(np.float32) / np.iinfo(x.dtype).max
    return x.astype(np.float32)


def cat_lang(x: np.ndarray, sr: int, nguong: float = 0.004, chua_ms: int = 60) -> np.ndarray:
    """Bỏ im lặng thừa ở hai đầu mẩu, giữ lại một chút đệm để không cụt tiếng."""
    if x.size == 0:
        return x
    ok = np.flatnonzero(np.abs(x) > nguong)
    if ok.size == 0:
        return x[: int(sr * 0.1)]
    chua = int(sr * chua_ms / 1000)
    return x[max(0, ok[0] - chua): min(x.size, ok[-1] + chua)]


def ghep_theo_cau(cau: list[dict], sinh, sr: int) -> tuple[np.ndarray, list[dict]]:
    """cau = [{"text": câu hiển thị, "chunks": [mẩu đọc...]}]; sinh(mẩu) -> sóng.

    Trả về (sóng đã ghép, [{"text", "startMs", "endMs"}]) với mốc tính trên tệp ghép: ~150 ms đầu tệp,
    ~350 ms giữa câu. Chuẩn hóa âm lượng chỉ nhân hệ số nên không đổi mốc.
    """
    def lang(ms: int) -> np.ndarray:
        return np.zeros(int(sr * ms / 1000), dtype=np.float32)

    phan: list[np.ndarray] = [lang(DAU_TEP_MS)]
    vi_tri = phan[0].size
    moc: list[dict] = []
    for i, c in enumerate(cau):
        if i > 0:
            phan.append(lang(GIUA_CAU_MS))
            vi_tri += phan[-1].size
        bat_dau = vi_tri
        for j, mau in enumerate(c["chunks"]):
            w = cat_lang(mono_float(sinh(mau)), sr)
            if w.size == 0:
                continue
            if vi_tri > bat_dau:
                phan.append(lang(GIUA_MAU_MS))
                vi_tri += phan[-1].size
            phan.append(w)
            vi_tri += w.size
        if vi_tri == bat_dau:          # máy đọc không ra tiếng: vẫn giữ câu với một khoảng ngắn
            phan.append(lang(100))
            vi_tri += phan[-1].size
        moc.append({"text": c["text"], "startMs": round(bat_dau * 1000 / sr), "endMs": round(vi_tri * 1000 / sr)})
    phan.append(lang(CUOI_TEP_MS))
    return chuan_hoa_am_luong(np.concatenate(phan)), moc


def chuan_hoa_am_luong(x: np.ndarray, rms_dbfs: float = -20.0, dinh_dbfs: float = -1.0) -> np.ndarray:
    """Đưa RMS về khoảng -20 dBFS rồi giới hạn đỉnh ở -1 dBFS (chỉ nhân hệ số, không đổi thời gian)."""
    x = mono_float(x)
    if x.size == 0:
        return x
    rms = float(np.sqrt(np.mean(x ** 2)) + 1e-9)
    x = x * (10 ** (rms_dbfs / 20) / rms)
    dinh = float(np.max(np.abs(x)) + 1e-9)
    gioi_han = 10 ** (dinh_dbfs / 20)
    if dinh > gioi_han:
        x = x * (gioi_han / dinh)
    return x.astype(np.float32)


_LAME_SR = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000)


def _lay_mau_lai(x: np.ndarray, sr: int, sr_moi: int) -> np.ndarray:
    n_moi = round(x.size * sr_moi / sr)
    return np.interp(np.arange(n_moi) / sr_moi, np.arange(x.size) / sr, x).astype(np.float32)


def luu_mp3(x: np.ndarray, sr: int, duong_dan: str | Path, kbps: int = KBPS) -> None:
    """Ghi MP3 mono CBR bằng lameenc; ghi tệp tạm rồi đổi tên để không bao giờ để lại tệp dở."""
    import lameenc
    duong_dan = Path(duong_dan)
    duong_dan.parent.mkdir(parents=True, exist_ok=True)
    x = mono_float(x)
    if sr not in _LAME_SR:
        sr_moi = min((s for s in _LAME_SR if s >= sr), default=48000)
        x, sr = _lay_mau_lai(x, sr, sr_moi), sr_moi
    enc = lameenc.Encoder()
    enc.set_bit_rate(kbps)
    enc.set_in_sample_rate(sr)
    enc.set_channels(1)
    enc.set_quality(2)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    tam = duong_dan.with_name(duong_dan.name + ".tmp")
    tam.write_bytes(enc.encode(pcm) + enc.flush())
    tam.replace(duong_dan)
