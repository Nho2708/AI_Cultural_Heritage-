"""Tạo thuyết minh tạo sẵn cho bản tóm tắt di sản rồi tải lên máy chủ qua API quản trị.

Chạy được bằng Python >= 3.11 bất kỳ (chỉ thư viện chuẩn); máy đọc thật chạy trong hai venv riêng (xem cai-dat.ps1).
Các bước: đăng nhập quản trị -> lấy danh sách tóm tắt còn thiếu thuyết minh theo từng ngôn ngữ -> tách câu, chuẩn hóa
tiếng Việt -> gọi máy đọc (VieNeu cho tiếng Việt, MeloTTS cho Anh/Hàn/Trung/Nhật) -> tải MP3 + mốc câu lên.

Chạy lại bất cứ lúc nào: máy chủ chỉ trả phần còn thiếu, âm thanh đã tạo được giữ trong thư mục ra (khóa theo textHash
và giọng) nên tải lên hỏng không phải tạo lại. Mật khẩu chỉ nhập qua ô ẩn; token chỉ nằm trong bộ nhớ của tiến trình.

  python tao_thuyet_minh.py                       # hỏi tên đăng nhập, mật khẩu rồi làm 5 ngôn ngữ
  python tao_thuyet_minh.py --dry-run             # chỉ liệt kê phần còn thiếu
  python tao_thuyet_minh.py --cuc-bo mau/vi-du.json --ra ../../ra-thu   # không mạng: đọc mục từ tệp, ghi ra thư mục
"""
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import os
import secrets
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

THU_MUC = Path(__file__).resolve().parent
sys.path.insert(0, str(THU_MUC))
from chia_cau import chia_mau, tach_cau
from chuan_hoa_vi import chuan_hoa_doan

API_MAC_DINH = "https://34.124.169.74/api/v1"
NGON_NGU_MAC_DINH = "vi,en,ko,zh,ja"
TEN_DANG_NHAP_MAC_DINH = "admin.vietnamheritage"
GIONG = {"vi": "vieneu-mai-anh", "en": "melo-en-us", "ko": "melo-kr", "zh": "melo-zh", "ja": "melo-jp"}
DONG_CO = {"vieneu-mai-anh": "vieneu", "melo-en-us": "melo", "melo-kr": "melo", "melo-zh": "melo", "melo-jp": "melo"}
MAY_DOC = {"vieneu": "doc_vieneu.py", "melo": "doc_melo.py"}
COT_NHAT_KY = ["thoi_diem", "buoc", "ket_qua", "heritageId", "slug", "language", "voice", "textHash", "durationMs",
               "giay_tao", "tep", "ghi_chu"]


# ---- Chuẩn bị văn bản ----

def bam(van_ban: str) -> str:
    return hashlib.sha256(van_ban.encode("utf-8")).hexdigest()


def chuan_bi_cau(van_ban: str, ngon_ngu: str) -> list[dict]:
    """Câu hiển thị là câu gốc; mẩu đưa vào máy đọc được chuẩn hóa (tiếng Việt) và cắt <= 250 ký tự."""
    cau = []
    for c in tach_cau(van_ban):
        doc = chuan_hoa_doan(c) if ngon_ngu == "vi" else c
        cau.append({"text": c, "chunks": chia_mau(doc) or [c]})
    return cau


def chuan_hoa_muc(muc: dict) -> dict:
    """Mục từ API hoặc từ tệp cục bộ -> cùng một dạng; thiếu textHash thì tự băm như máy chủ (SHA-256 của UTF-8)."""
    ngon_ngu = str(muc["language"]).lower()
    if ngon_ngu == "zh-hans":
        ngon_ngu = "zh"
    if ngon_ngu not in GIONG:
        raise ValueError(f"ngôn ngữ không hỗ trợ: {muc['language']}")
    van_ban = muc["shortText"]
    if not isinstance(van_ban, str) or not van_ban.strip():
        raise ValueError("shortText rỗng")
    return {
        "heritageId": muc.get("heritageId", muc.get("id")), "slug": muc.get("slug", ""), "name": muc.get("name", ""),
        "language": ngon_ngu, "shortText": van_ban, "textHash": muc.get("textHash") or bam(van_ban), "voice": GIONG[ngon_ngu],
    }


def khoa_cache(muc: dict) -> str:
    return f"{muc['textHash']}__{muc['voice']}"


def tep_cache(ra: Path, muc: dict) -> tuple[Path, Path]:
    goc = ra / "am-thanh" / khoa_cache(muc)
    return goc.with_suffix(".mp3"), goc.with_suffix(".json")


def doc_cache(ra: Path, muc: dict) -> dict | None:
    """Kết quả đã tạo trước đó (mp3 + json hợp lệ) hoặc None."""
    mp3, js = tep_cache(ra, muc)
    if not (mp3.is_file() and js.is_file() and mp3.stat().st_size > 0):
        return None
    try:
        kq = json.loads(js.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if not isinstance(kq.get("durationMs"), int) or not kq.get("sentences"):
        return None
    return kq


# ---- Máy đọc ----

def duong_dan_python_mac_dinh(ten_venv: str) -> Path:
    goc = THU_MUC / "moi-truong" / ten_venv
    return goc / "Scripts" / "python.exe" if os.name == "nt" else goc / "bin" / "python"


def chay_may_doc(dong_co: str, tep_viec: Path, cau_hinh: dict) -> int:
    """Chạy máy đọc trong venv riêng; trả mã thoát. Tách hàm để test thay bằng bản giả."""
    python = Path(cau_hinh["python"][dong_co])
    if not python.is_file():
        print(f"  Chưa có Python của máy đọc {dong_co}: {python}. Chạy cai-dat.ps1 hoặc truyền --python-{dong_co}.")
        return 127
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", HF_HOME=str(cau_hinh["hf_home"]),
               HF_HUB_DISABLE_SYMLINKS_WARNING="1")
    return subprocess.run([str(python), "-X", "utf8", str(THU_MUC / MAY_DOC[dong_co]), str(tep_viec)], env=env,
                          check=False).returncode


def tao_am_thanh(ra: Path, muc_can_tao: list[dict], cau_hinh: dict, nhat_ky: NhatKy) -> None:
    """Gom mục theo máy đọc, mỗi máy chạy một lần (nạp mô hình một lần), ghi kết quả từng mục vào nhật ký."""
    theo_dong_co: dict[str, dict[str, dict]] = {}
    for muc in muc_can_tao:
        theo_dong_co.setdefault(DONG_CO[muc["voice"]], {}).setdefault(khoa_cache(muc), muc)
    (ra / "viec").mkdir(parents=True, exist_ok=True)
    for dong_co, cac_muc in theo_dong_co.items():
        tep_viec = ra / "viec" / f"{time.strftime('%Y%m%d-%H%M%S')}-{dong_co}.json"
        items = []
        for khoa, muc in cac_muc.items():
            mp3, js = tep_cache(ra, muc)
            items.append({"key": khoa, "language": muc["language"], "voice": muc["voice"],
                          "sentences": chuan_bi_cau(muc["shortText"], muc["language"]), "mp3": str(mp3), "json": str(js)})
        tep_viec.write_text(json.dumps({"engine": dong_co, "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nMáy đọc {dong_co}: {len(items)} mục")
        t0 = time.perf_counter()
        ma = chay_may_doc(dong_co, tep_viec, cau_hinh)
        tep_kq = Path(str(tep_viec) + ".ket-qua.json")
        ket_qua = json.loads(tep_kq.read_text(encoding="utf-8")) if tep_kq.is_file() else {}
        for khoa, muc in cac_muc.items():
            kq = ket_qua.get(khoa) or {"ok": False, "error": f"máy đọc thoát mã {ma}, không có kết quả"}
            nhat_ky.ghi(muc, "tạo", "ok" if kq["ok"] else "lỗi", durationMs=kq.get("durationMs", ""),
                        giay_tao=kq.get("generationSeconds", ""), tep=tep_cache(ra, muc)[0].name, ghi_chu=kq.get("error", ""))
        print(f"Máy đọc {dong_co} xong sau {time.perf_counter() - t0:.0f} s (mã thoát {ma})")


# ---- API quản trị ----

def ma_hoa_multipart(truong: dict[str, str], ten_tep: str, noi_dung: bytes, kieu: str = "audio/mpeg",
                     truong_tep: str = "audio") -> tuple[bytes, str]:
    """Bộ mã hóa multipart/form-data nhỏ: các trường chữ rồi một tệp."""
    ranh = "----DSVHVN" + secrets.token_hex(16)
    phan = [f'--{ranh}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
            for k, v in truong.items()]
    phan.append(f'--{ranh}\r\nContent-Disposition: form-data; name="{truong_tep}"; filename="{ten_tep}"\r\n'
                f"Content-Type: {kieu}\r\n\r\n".encode() + noi_dung + b"\r\n")
    phan.append(f"--{ranh}--\r\n".encode())
    return b"".join(phan), f"multipart/form-data; boundary={ranh}"


class KhachApi:
    """Gọi API quản trị bằng urllib; giữ token trong bộ nhớ, tự đăng nhập lại khi gặp 401."""

    def __init__(self, goc: str, timeout: float, ca: str | None = None):
        self.goc = goc.rstrip("/")
        self.timeout = timeout
        self.ssl = ssl.create_default_context(cafile=ca)   # luôn kiểm chứng chứng chỉ
        self._token: str | None = None
        self._ten: str | None = None
        self._mat_khau: str | None = None

    def goi(self, method: str, duong_dan: str, du_lieu: bytes | None = None, kieu: str | None = None,
            can_token: bool = True) -> tuple[int, dict]:
        h = {"Accept": "application/json"}
        if kieu:
            h["Content-Type"] = kieu
        if can_token and self._token:
            h["Authorization"] = "Bearer " + self._token
        req = urllib.request.Request(self.goc + duong_dan, data=du_lieu, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ssl) as r:
                trang_thai, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            trang_thai, raw = e.code, e.read()
        try:
            phong_bi = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            phong_bi = {}
        return trang_thai, phong_bi if isinstance(phong_bi, dict) else {}

    def dang_nhap(self, ten: str, mat_khau: str) -> None:
        self._ten, self._mat_khau = ten, mat_khau
        than = json.dumps({"emailOrUsername": ten, "password": mat_khau}).encode("utf-8")
        trang_thai, pb = self.goi("POST", "/auth/login", than, "application/json; charset=utf-8", can_token=False)
        token = (pb.get("data") or {}).get("accessToken") if trang_thai == 200 else None
        if not token:
            raise SystemExit(f"Đăng nhập thất bại ({trang_thai}): {pb.get('message') or 'không có token trong phản hồi'}")
        self._token = token

    def goi_co_dang_nhap_lai(self, method: str, duong_dan: str, du_lieu: bytes | None = None,
                             kieu: str | None = None) -> tuple[int, dict]:
        trang_thai, pb = self.goi(method, duong_dan, du_lieu, kieu)
        if trang_thai == 401 and self._ten is not None:
            print("  Phiên hết hạn, đăng nhập lại...")
            self.dang_nhap(self._ten, self._mat_khau or "")
            trang_thai, pb = self.goi(method, duong_dan, du_lieu, kieu)
        return trang_thai, pb

    def lay_thieu(self, ngon_ngu: str, limit: int) -> tuple[list[dict], int]:
        q = urllib.parse.urlencode({"language": ngon_ngu, "limit": limit})
        trang_thai, pb = self.goi_co_dang_nhap_lai("GET", f"/admin/narrations/missing?{q}")
        if trang_thai != 200:
            raise SystemExit(f"Lấy danh sách thiếu ({ngon_ngu}) thất bại ({trang_thai}): {pb.get('message') or ''}")
        d = pb.get("data") or {}
        return list(d.get("items") or []), int(d.get("total") or 0)

    def tai_len(self, muc: dict, mp3: Path, kq: dict) -> tuple[int, str]:
        truong = {"textHash": muc["textHash"], "voice": kq["voice"], "durationMs": str(kq["durationMs"]),
                  "sentences": json.dumps(kq["sentences"], ensure_ascii=False)}
        than, kieu = ma_hoa_multipart(truong, mp3.name, mp3.read_bytes())
        trang_thai, pb = self.goi_co_dang_nhap_lai("PUT", f"/admin/heritages/{muc['heritageId']}/narrations/{muc['language']}",
                                                   than, kieu)
        return trang_thai, str(pb.get("message") or pb.get("errorCode") or "")


# ---- Nhật ký ----

class NhatKy:
    def __init__(self, tep: Path):
        tep.parent.mkdir(parents=True, exist_ok=True)
        self.tep = tep
        self.dem: dict[str, int] = {}
        with open(tep, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COT_NHAT_KY).writeheader()

    def ghi(self, muc: dict, buoc: str, ket_qua: str, **them) -> None:
        self.dem[f"{buoc}: {ket_qua}"] = self.dem.get(f"{buoc}: {ket_qua}", 0) + 1
        dong = {"thoi_diem": time.strftime("%Y-%m-%d %H:%M:%S"), "buoc": buoc, "ket_qua": ket_qua,
                "heritageId": muc.get("heritageId", ""), "slug": muc.get("slug", ""), "language": muc.get("language", ""),
                "voice": muc.get("voice", ""), "textHash": muc.get("textHash", "")}
        dong.update(them)
        with open(self.tep, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COT_NHAT_KY).writerow({k: dong.get(k, "") for k in COT_NHAT_KY})


# ---- Chạy ----

def doc_tham_so(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Tạo thuyết minh tạo sẵn và tải lên máy chủ.")
    ap.add_argument("--api", default=API_MAC_DINH, help=f"gốc API (mặc định {API_MAC_DINH})")
    ap.add_argument("--languages", default=NGON_NGU_MAC_DINH, help="mã ngôn ngữ cách nhau bằng dấu phẩy")
    ap.add_argument("--limit", type=int, default=500, help="số mục tối đa mỗi ngôn ngữ một lượt (1..1000)")
    ap.add_argument("--dry-run", action="store_true", help="chỉ liệt kê phần còn thiếu, không tạo, không tải lên")
    ap.add_argument("--cuc-bo", metavar="TEP_JSON", help="không mạng: đọc danh sách mục từ tệp JSON, ghi ra thư mục --ra")
    ap.add_argument("--ra", default=str(THU_MUC / "ra"), help="thư mục chứa âm thanh đã tạo (cache), tệp việc và nhật ký")
    ap.add_argument("--username", help=f"tên đăng nhập quản trị (không có thì hỏi, mặc định {TEN_DANG_NHAP_MAC_DINH})")
    ap.add_argument("--python-vieneu", default=str(duong_dan_python_mac_dinh("vieneu")), help="Python của venv vieneu")
    ap.add_argument("--python-melo", default=str(duong_dan_python_mac_dinh("melo")), help="Python của venv melo")
    ap.add_argument("--hf-home", default=str(THU_MUC / ".cache" / "hf"), help="thư mục cache mô hình Hugging Face")
    ap.add_argument("--ca", help="tệp PEM chứa chứng chỉ gốc tin cậy thêm (vẫn kiểm chứng TLS)")
    ap.add_argument("--timeout", type=float, default=120, help="giây chờ mỗi lần gọi API")
    a = ap.parse_args(argv)
    a.languages = [n.strip().lower() for n in a.languages.split(",") if n.strip()]
    la = [n for n in a.languages if n not in GIONG]
    if la:
        ap.error(f"ngôn ngữ không hỗ trợ: {', '.join(la)} (chỉ {', '.join(GIONG)})")
    if not 1 <= a.limit <= 1000:
        ap.error("--limit phải trong 1..1000")
    return a


def doc_muc_cuc_bo(tep: Path, ngon_ngu: list[str]) -> list[dict]:
    du_lieu = json.loads(tep.read_text(encoding="utf-8"))
    if isinstance(du_lieu, dict):
        du_lieu = du_lieu.get("items") or []
    muc = [chuan_hoa_muc(m) for m in du_lieu]
    return [m for m in muc if m["language"] in ngon_ngu]


def main(argv: list[str] | None = None) -> int:
    a = doc_tham_so(argv)
    ra = Path(a.ra)
    cau_hinh = {"python": {"vieneu": a.python_vieneu, "melo": a.python_melo}, "hf_home": Path(a.hf_home)}
    api: KhachApi | None = None

    if a.cuc_bo:
        muc = doc_muc_cuc_bo(Path(a.cuc_bo), a.languages)
        print(f"Chế độ cục bộ: {len(muc)} mục từ {a.cuc_bo}, không gọi mạng.")
    else:
        ten = a.username or input(f"Tên đăng nhập [{TEN_DANG_NHAP_MAC_DINH}]: ").strip() or TEN_DANG_NHAP_MAC_DINH
        mat_khau = getpass.getpass(f"Mật khẩu của {ten}: ")
        api = KhachApi(a.api, a.timeout, a.ca)
        api.dang_nhap(ten, mat_khau)
        del mat_khau
        muc = []
        for ngon_ngu in a.languages:
            items, tong = api.lay_thieu(ngon_ngu, a.limit)
            print(f"{ngon_ngu}: còn thiếu {tong}, lấy {len(items)} mục")
            muc.extend(chuan_hoa_muc(m) for m in items)

    if not muc:
        print("Không có gì để làm.")
        return 0
    da_co = {khoa_cache(m) for m in muc if doc_cache(ra, m)}
    for m in muc:
        print(f"  [{m['language']}] {m['heritageId']} {m['slug']}  {len(m['shortText'])} ký tự"
              f"{'  (đã có âm thanh)' if khoa_cache(m) in da_co else ''}")
    if a.dry_run:
        print(f"\nTổng {len(muc)} mục, {len(da_co)} đã có âm thanh trong {ra / 'am-thanh'}.")
        return 0

    nhat_ky = NhatKy(ra / "nhat-ky" / f"{time.strftime('%Y%m%d-%H%M%S')}.csv")
    can_tao = [m for m in muc if khoa_cache(m) not in da_co]
    if can_tao:
        tao_am_thanh(ra, can_tao, cau_hinh, nhat_ky)
    else:
        print("Mọi mục đã có âm thanh, chỉ tải lên.")

    print()
    loi = 0
    for m in muc:
        kq = doc_cache(ra, m)
        mp3 = tep_cache(ra, m)[0]
        if kq is None:
            loi += 1
            continue                                  # đã ghi lỗi ở bước tạo
        if api is None:
            dich = ra / "cuc-bo" / f"{m['slug'] or m['heritageId']}__{m['language']}"
            dich.parent.mkdir(parents=True, exist_ok=True)
            dich.with_suffix(".mp3").write_bytes(mp3.read_bytes())
            dich.with_suffix(".json").write_text(json.dumps(kq, ensure_ascii=False, indent=1), encoding="utf-8")
            nhat_ky.ghi(m, "ghi ra", "ok", durationMs=kq["durationMs"], tep=str(dich.with_suffix(".mp3")))
            continue
        trang_thai, thong_bao = api.tai_len(m, mp3, kq)
        if trang_thai == 200:
            nhat_ky.ghi(m, "tải lên", "ok", durationMs=kq["durationMs"], tep=mp3.name)
            print(f"  đã tải [{m['language']}] {m['slug']}")
        elif trang_thai == 409:
            nhat_ky.ghi(m, "tải lên", "bỏ qua: tóm tắt đã đổi", durationMs=kq["durationMs"], tep=mp3.name, ghi_chu=thong_bao)
            print(f"  bỏ qua [{m['language']}] {m['slug']}: tóm tắt đã đổi (409), lần chạy sau sẽ tạo lại")
        else:
            loi += 1
            nhat_ky.ghi(m, "tải lên", "lỗi", durationMs=kq["durationMs"], tep=mp3.name, ghi_chu=f"{trang_thai} {thong_bao}")
            print(f"  lỗi [{m['language']}] {m['slug']}: {trang_thai} {thong_bao}")

    print("\nTóm tắt: " + "; ".join(f"{k} {v}" for k, v in nhat_ky.dem.items()) + f". Nhật ký: {nhat_ky.tep}")
    return 1 if loi else 0


if __name__ == "__main__":
    sys.exit(main())
