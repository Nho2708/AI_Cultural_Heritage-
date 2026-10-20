"""Vòng chạy chung của máy đọc: đọc tệp việc, sinh từng mục, ghi MP3 + JSON mốc câu, ghi kết quả.

Tệp việc (do tao_thuyet_minh.py viết):
  {"items": [{"key": "...", "language": "vi", "voice": "vieneu-mai-anh",
              "sentences": [{"text": "câu gốc", "chunks": ["mẩu đưa vào máy đọc", ...]}],
              "mp3": "đường dẫn ra", "json": "đường dẫn ra"}]}
Mỗi mục xong thì có <json> = {"voice", "language", "durationMs", "sentences": [{"text","startMs","endMs"}], ...}.
Kết quả từng mục ghi vào <tệp việc>.ket-qua.json để tiến trình gọi đọc lại. Mô hình chỉ nạp một lần cho cả tệp việc.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from am_thanh import ghep_theo_cau, luu_mp3


def chay(duong_dan_viec: str, lay_may_doc) -> int:
    """lay_may_doc(voice) -> (sinh(mẩu) -> sóng, tần số mẫu); được gọi lại nhiều lần nên tự giữ mô hình đã nạp."""
    tep_viec = Path(duong_dan_viec)
    viec = json.loads(tep_viec.read_text(encoding="utf-8"))
    ket_qua: dict[str, dict] = {}
    for muc in viec["items"]:
        try:
            sinh, sr = lay_may_doc(muc["voice"])
            t0 = time.perf_counter()
            song, moc = ghep_theo_cau(muc["sentences"], sinh, sr)
            giay_tao = time.perf_counter() - t0
            duration_ms = round(song.size * 1000 / sr)
            luu_mp3(song, sr, muc["mp3"])
            noi_dung = {
                "voice": muc["voice"], "language": muc["language"], "durationMs": duration_ms, "sentences": moc,
                "generationSeconds": round(giay_tao, 2), "sampleRate": sr, "engine": viec.get("engine", ""),
            }
            tam = Path(muc["json"] + ".tmp")
            tam.write_text(json.dumps(noi_dung, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tam, muc["json"])
            ket_qua[muc["key"]] = {"ok": True, "durationMs": duration_ms, "generationSeconds": round(giay_tao, 2)}
            print(f"  xong {muc['key']}: {giay_tao:.1f} s tạo / {duration_ms / 1000:.1f} s âm thanh, {len(moc)} câu",
                  flush=True)
        except Exception as e:  # noqa: BLE001 - ghi lỗi rồi làm tiếp mục khác, mục hỏng không chặn cả lượt
            traceback.print_exc()
            ket_qua[muc["key"]] = {"ok": False, "error": repr(e)[:300]}
    Path(str(tep_viec) + ".ket-qua.json").write_text(json.dumps(ket_qua, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if all(k["ok"] for k in ket_qua.values()) else 1
