"""Tiến trình tạo thuyết minh (tools/thuyet-minh/tao_thuyet_minh.py) chạy trước một API quản trị giả bằng http.server:
đăng nhập, lấy danh sách thiếu, gọi máy đọc (thay bằng bản giả), tải lên multipart, đăng nhập lại khi 401, bỏ qua khi 409,
chạy lại chỉ dùng lại âm thanh đã có, chế độ cục bộ không mạng, chế độ lặp đến giờ chốt (đồng hồ giả, không nghỉ thật). Không cần gói nào ngoài thư viện chuẩn."""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
from datetime import datetime
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

THU_MUC_CONG_CU = Path(__file__).resolve().parent.parent / "tools" / "thuyet-minh"
sys.path.insert(0, str(THU_MUC_CONG_CU))

import tao_thuyet_minh as tao

MAT_KHAU = "MatKhauQuanTri!2026"
TOM_TAT = {
    (1, "vi"): "Khu đền tháp Mỹ Sơn được xây từ thế kỷ IV. Ngày 1/12/1999, UNESCO ghi danh Mỹ Sơn.",
    (2, "vi"): "Văn Miếu được dựng năm 1070 tại TP. Hà Nội. Có 82 bia tiến sĩ.",
    (3, "en"): "Hoi An is a trading port. Mr. Kazik helped restore it.",
}


class TrangThai:
    """Trạng thái của máy chủ giả, đặt lại cho mỗi test."""

    def __init__(self):
        self.so_lan_dang_nhap = 0
        self.da_tai: dict[tuple[int, str], dict] = {}
        self.yeu_cau_put: list[dict] = []
        self.tom_tat_doi: set[tuple[int, str]] = set()      # trả 409
        self.token_het_han: set[str] = set()                 # trả 401 khi PUT bằng token này
        self.het_han_mot_lan: tuple[int, str] | None = None  # di sản mà lần PUT đầu bằng token-1 bị 401
        self.token_lay_het_han: set[str] = set()             # trả 401 khi lấy danh sách thiếu bằng token này


class MayChuGia(BaseHTTPRequestHandler):
    trang_thai = TrangThai()

    def log_message(self, *a):  # im lặng
        pass

    def _tra(self, ma: int, data=None, message: str | None = None):
        than = json.dumps({"success": ma < 400, "data": data, "message": message, "errorCode": None, "traceId": "t"},
                          ensure_ascii=False).encode("utf-8")
        self.send_response(ma)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(than)))
        self.end_headers()
        self.wfile.write(than)

    def _than(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def _token(self) -> str:
        return self.headers.get("Authorization", "").removeprefix("Bearer ").strip()

    def do_POST(self):
        tt = self.trang_thai
        if urlparse(self.path).path != "/api/v1/auth/login":
            return self._tra(404)
        than = json.loads(self._than())
        if than != {"emailOrUsername": "admin.vietnamheritage", "password": MAT_KHAU}:
            return self._tra(401, message="Sai tài khoản hoặc mật khẩu")
        tt.so_lan_dang_nhap += 1
        return self._tra(200, {"tokenType": "Bearer", "accessToken": f"token-{tt.so_lan_dang_nhap}", "user": {}})

    def do_GET(self):
        tt = self.trang_thai
        u = urlparse(self.path)
        if u.path != "/api/v1/admin/narrations/missing":
            return self._tra(404)
        if self._token() not in {f"token-{i}" for i in range(1, tt.so_lan_dang_nhap + 1)} or self._token() in tt.token_lay_het_han:
            return self._tra(401)
        q = parse_qs(u.query)
        ngon_ngu, limit = q["language"][0], int(q["limit"][0])
        items = [{"heritageId": hid, "slug": f"di-san-{hid}", "name": f"Di sản {hid}", "language": ng, "shortText": vb,
                  "textHash": tao.bam(vb)}
                 for (hid, ng), vb in TOM_TAT.items() if ng == ngon_ngu and (hid, ng) not in tt.da_tai]
        return self._tra(200, {"items": items[:limit], "total": len(items)})

    def do_PUT(self):
        tt = self.trang_thai
        phan = urlparse(self.path).path.split("/")   # ['', 'api', 'v1', 'admin', 'heritages', '{id}', 'narrations', '{lang}']
        if len(phan) != 8 or phan[4] != "heritages" or phan[6] != "narrations":
            return self._tra(404)
        hid, ngon_ngu = int(phan[5]), phan[7]
        than = self._than()
        token = self._token()
        msg = BytesParser().parsebytes(b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + than)
        truong, tep = {}, None
        for p in msg.get_payload():
            ten = p.get_param("name", header="content-disposition")
            if p.get_filename():
                tep = {"filename": p.get_filename(), "type": p.get_content_type(), "bytes": p.get_payload(decode=True)}
            else:
                truong[ten] = p.get_payload(decode=True).decode("utf-8")
        yeu_cau = {"heritageId": hid, "language": ngon_ngu, "fields": truong, "audio": tep, "token": token}
        tt.yeu_cau_put.append(yeu_cau)
        if token in tt.token_het_han or (tt.het_han_mot_lan == (hid, ngon_ngu) and token == "token-1"):
            tt.token_het_han.add(token)
            return self._tra(401, message="Token hết hạn")
        if (hid, ngon_ngu) not in TOM_TAT:
            return self._tra(404, message="Không có tóm tắt")
        if (hid, ngon_ngu) in tt.tom_tat_doi or truong.get("textHash") != tao.bam(TOM_TAT[(hid, ngon_ngu)]):
            return self._tra(409, message="Tóm tắt đã đổi, tạo lại")
        tt.da_tai[(hid, ngon_ngu)] = yeu_cau
        return self._tra(200, {"heritageId": hid, "language": ngon_ngu, "sentenceCount": len(json.loads(truong["sentences"]))})


@pytest.fixture
def may_chu():
    MayChuGia.trang_thai = TrangThai()
    server = ThreadingHTTPServer(("127.0.0.1", 0), MayChuGia)
    luong = threading.Thread(target=server.serve_forever, daemon=True)
    luong.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/api/v1", MayChuGia.trang_thai
    finally:
        server.shutdown()
        server.server_close()


def may_doc_gia(goi_lai: list):
    """Thay máy đọc thật: ghi MP3 giả (mở đầu bằng khung MPEG) và mốc câu 1 giây mỗi câu, cách 350 ms."""
    def chay(dong_co, tep_viec, cau_hinh):
        viec = json.loads(Path(tep_viec).read_text(encoding="utf-8"))
        goi_lai.append((dong_co, [m["key"] for m in viec["items"]]))
        ket_qua = {}
        for m in viec["items"]:
            moc, t = [], 150
            for c in m["sentences"]:
                moc.append({"text": c["text"], "startMs": t, "endMs": t + 1000})
                t += 1350
            Path(m["mp3"]).parent.mkdir(parents=True, exist_ok=True)
            Path(m["mp3"]).write_bytes(b"\xff\xfb\x90\x00" + bytes(200))
            Path(m["json"]).write_text(json.dumps({"voice": m["voice"], "language": m["language"], "durationMs": t,
                                                    "sentences": moc, "generationSeconds": 0.5}), encoding="utf-8")
            ket_qua[m["key"]] = {"ok": True, "durationMs": t, "generationSeconds": 0.5}
        Path(str(tep_viec) + ".ket-qua.json").write_text(json.dumps(ket_qua), encoding="utf-8")
        return 0
    return chay


def doc_nhat_ky(ra: Path) -> list[dict]:
    import csv
    tep = max((ra / "nhat-ky").glob("*.csv"))
    with open(tep, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def mat_khau_an(monkeypatch):
    hoi = []
    monkeypatch.setattr(tao.getpass, "getpass", lambda prompt="": (hoi.append(prompt), MAT_KHAU)[1])
    return hoi


def test_chay_tron_ven_tai_len_dang_nhap_lai_va_bo_qua_409(may_chu, tmp_path, monkeypatch, capsys, mat_khau_an):
    api, tt = may_chu
    tt.tom_tat_doi.add((2, "vi"))
    tt.het_han_mot_lan = (3, "en")
    goi_lai: list = []
    monkeypatch.setattr(tao, "chay_may_doc", may_doc_gia(goi_lai))

    ma = tao.main(["--api", api, "--ra", str(tmp_path), "--username", "admin.vietnamheritage", "--languages", "vi,en,ko"])

    assert ma == 0
    assert mat_khau_an == ["Mật khẩu của admin.vietnamheritage: "]
    # Máy đọc: mỗi máy chạy một lần với đủ mục của nó
    assert sorted(goi_lai) == [("melo", [f"{tao.bam(TOM_TAT[(3, 'en')])}__melo-en-us"]),
                               ("vieneu", [f"{tao.bam(TOM_TAT[(1, 'vi')])}__vieneu-mai-anh", f"{tao.bam(TOM_TAT[(2, 'vi')])}__vieneu-mai-anh"])]
    # Tải lên đúng dạng multipart
    assert set(tt.da_tai) == {(1, "vi"), (3, "en")}
    yc = tt.da_tai[(1, "vi")]
    assert yc["fields"]["textHash"] == tao.bam(TOM_TAT[(1, "vi")])
    assert yc["fields"]["voice"] == "vieneu-mai-anh"
    assert yc["fields"]["durationMs"] == str(150 + 1350 * 2)
    cau = json.loads(yc["fields"]["sentences"])
    assert [c["text"] for c in cau] == ["Khu đền tháp Mỹ Sơn được xây từ thế kỷ IV.", "Ngày 1/12/1999, UNESCO ghi danh Mỹ Sơn."]
    assert cau[0] == {"text": cau[0]["text"], "startMs": 150, "endMs": 1150} and cau[1]["startMs"] == 1500
    assert yc["audio"]["type"] == "audio/mpeg" and yc["audio"]["filename"].endswith(".mp3")
    assert yc["audio"]["bytes"][:2] == b"\xff\xfb" and len(yc["audio"]["bytes"]) == 204
    # 401 ở di sản 3: đăng nhập lại rồi gửi lại bằng token mới
    assert tt.so_lan_dang_nhap == 2
    assert [y["token"] for y in tt.yeu_cau_put if y["heritageId"] == 3] == ["token-1", "token-2"]
    assert tt.da_tai[(3, "en")]["fields"]["voice"] == "melo-en-us"
    # 409 ở di sản 2: bỏ qua, có trong nhật ký, không phải lỗi
    nk = doc_nhat_ky(tmp_path)
    assert [(d["buoc"], d["ket_qua"]) for d in nk if d["heritageId"] == "2"] == [("tạo", "ok"), ("tải lên", "bỏ qua: tóm tắt đã đổi")]
    assert sum(1 for d in nk if d["buoc"] == "tải lên" and d["ket_qua"] == "ok") == 2
    # Không lộ mật khẩu hay token
    ra = capsys.readouterr().out
    noi_dung_nk = "".join(",".join(d.values()) for d in nk)
    assert MAT_KHAU not in ra and "token-1" not in ra and "token-" not in noi_dung_nk and MAT_KHAU not in noi_dung_nk
    assert "đăng nhập lại" in ra and "bỏ qua [vi] di-san-2" in ra


def test_chay_lai_chi_lam_phan_con_thieu_va_dung_lai_am_thanh_da_co(may_chu, tmp_path, monkeypatch, mat_khau_an):
    api, tt = may_chu
    monkeypatch.setattr(tao, "chay_may_doc", may_doc_gia([]))
    assert tao.main(["--api", api, "--ra", str(tmp_path), "--username", "admin.vietnamheritage", "--languages", "vi"]) == 0
    assert set(tt.da_tai) == {(1, "vi"), (2, "vi")}

    # Máy chủ đổi tóm tắt của di sản 2 (băm mới) -> lại thiếu; di sản 1 đã có nên không trả về nữa.
    TOM_TAT[(2, "vi")] = "Văn Miếu được dựng năm 1070. Bản tóm tắt đã sửa."
    try:
        del tt.da_tai[(2, "vi")]
        goi_lai: list = []
        monkeypatch.setattr(tao, "chay_may_doc", may_doc_gia(goi_lai))
        assert tao.main(["--api", api, "--ra", str(tmp_path), "--username", "admin.vietnamheritage", "--languages", "vi"]) == 0
        assert goi_lai == [("vieneu", [f"{tao.bam(TOM_TAT[(2, 'vi')])}__vieneu-mai-anh"])]
        assert set(tt.da_tai) == {(1, "vi"), (2, "vi")}
        # Tải lên hỏng (giả lập: máy chủ báo tóm tắt đổi) rồi chạy lại: không tạo lại vì đã có âm thanh đúng băm
        del tt.da_tai[(2, "vi")]
        tt.tom_tat_doi.add((2, "vi"))
        monkeypatch.setattr(tao, "chay_may_doc", lambda *a: pytest.fail("không được gọi máy đọc khi đã có âm thanh"))
        assert tao.main(["--api", api, "--ra", str(tmp_path), "--username", "admin.vietnamheritage", "--languages", "vi"]) == 0
        assert len([f for f in (tmp_path / "am-thanh").glob("*.mp3")]) == 3
    finally:
        TOM_TAT[(2, "vi")] = "Văn Miếu được dựng năm 1070 tại TP. Hà Nội. Có 82 bia tiến sĩ."


def test_dry_run_chi_liet_ke(may_chu, tmp_path, monkeypatch, capsys, mat_khau_an):
    api, tt = may_chu
    monkeypatch.setattr(tao, "chay_may_doc", lambda *a: pytest.fail("dry-run không được gọi máy đọc"))
    assert tao.main(["--api", api, "--ra", str(tmp_path), "--username", "admin.vietnamheritage", "--dry-run"]) == 0
    ra = capsys.readouterr().out
    assert "vi: còn thiếu 2, lấy 2 mục" in ra and "en: còn thiếu 1, lấy 1 mục" in ra and "ko: còn thiếu 0" in ra
    assert "di-san-1" in ra and "Tổng 3 mục" in ra
    assert not tt.yeu_cau_put and not (tmp_path / "nhat-ky").exists()


def test_dang_nhap_sai_thi_dung(may_chu, tmp_path, monkeypatch):
    api, _ = may_chu
    monkeypatch.setattr(tao.getpass, "getpass", lambda prompt="": "sai")
    with pytest.raises(SystemExit, match="Đăng nhập thất bại \\(401\\)"):
        tao.main(["--api", api, "--ra", str(tmp_path), "--username", "admin.vietnamheritage"])


def test_may_doc_loi_thi_ghi_nhat_ky_va_thoat_ma_1(may_chu, tmp_path, monkeypatch, mat_khau_an):
    api, tt = may_chu

    def may_doc_hong(dong_co, tep_viec, cau_hinh):
        return 1   # không ghi gì
    monkeypatch.setattr(tao, "chay_may_doc", may_doc_hong)
    assert tao.main(["--api", api, "--ra", str(tmp_path), "--username", "admin.vietnamheritage", "--languages", "en"]) == 1
    nk = doc_nhat_ky(tmp_path)
    assert [(d["buoc"], d["ket_qua"]) for d in nk] == [("tạo", "lỗi")] and "mã 1" in nk[0]["ghi_chu"]
    assert not tt.yeu_cau_put


def test_che_do_cuc_bo_khong_mang(tmp_path, monkeypatch):
    goi_lai: list = []
    monkeypatch.setattr(tao, "chay_may_doc", may_doc_gia(goi_lai))
    monkeypatch.setattr(tao.getpass, "getpass", lambda prompt="": pytest.fail("cục bộ không hỏi mật khẩu"))
    monkeypatch.setattr(tao.urllib.request, "urlopen", lambda *a, **k: pytest.fail("cục bộ không gọi mạng"))

    ma = tao.main(["--cuc-bo", str(THU_MUC_CONG_CU / "mau" / "vi-du.json"), "--ra", str(tmp_path), "--languages", "vi,ja"])

    assert ma == 0
    assert [(d, len(k)) for d, k in sorted(goi_lai)] == [("melo", 1), ("vieneu", 2)]
    ra = tmp_path / "cuc-bo"
    assert {p.name for p in ra.iterdir()} == {"khu-den-thap-my-son__vi.mp3", "khu-den-thap-my-son__vi.json",
                                               "van-mieu-quoc-tu-giam__vi.mp3", "van-mieu-quoc-tu-giam__vi.json",
                                               "phong-nha-ke-bang__ja.mp3", "phong-nha-ke-bang__ja.json"}
    kq = json.loads((ra / "khu-den-thap-my-son__vi.json").read_text(encoding="utf-8"))
    assert kq["voice"] == "vieneu-mai-anh" and len(kq["sentences"]) == 4
    assert all(d["buoc"] == "ghi ra" or d["buoc"] == "tạo" for d in doc_nhat_ky(tmp_path))


def test_chuan_bi_cau_tieng_viet_mau_doc_duoc_chuan_hoa_con_cau_hien_thi_giu_nguyen():
    cau = tao.chuan_bi_cau("Ngày 1/12/1999, UNESCO ghi danh Mỹ Sơn. Có 82 bia tiến sĩ ở TP. Hà Nội.", "vi")
    assert [c["text"] for c in cau] == ["Ngày 1/12/1999, UNESCO ghi danh Mỹ Sơn.", "Có 82 bia tiến sĩ ở TP. Hà Nội."]
    assert cau[0]["chunks"] == ["Ngày một tháng mười hai năm một nghìn chín trăm chín mươi chín, U-nét-xcô ghi danh Mỹ Sơn."]
    assert cau[1]["chunks"] == ["Có tám mươi hai bia tiến sĩ ở thành phố Hà Nội."]
    en = tao.chuan_bi_cau("Hoi An was inscribed in 1999. " + ", ".join(["a long clause"] * 40) + ".", "en")
    assert en[0]["chunks"] == ["Hoi An was inscribed in 1999."] and len(en[1]["chunks"]) > 1
    assert all(len(m) <= 250 for m in en[1]["chunks"])


def test_ma_hoa_multipart_doc_lai_duoc_bang_thu_vien_chuan():
    than, kieu = tao.ma_hoa_multipart({"textHash": "a" * 64, "sentences": "[{\"text\": \"Xin chào\"}]"}, "x.mp3", b"\xff\xfb\x00\x01")
    msg = BytesParser().parsebytes(b"Content-Type: " + kieu.encode() + b"\r\n\r\n" + than)
    phan = msg.get_payload()
    assert [p.get_param("name", header="content-disposition") for p in phan] == ["textHash", "sentences", "audio"]
    assert phan[1].get_payload(decode=True).decode("utf-8") == "[{\"text\": \"Xin chào\"}]"
    assert phan[2].get_filename() == "x.mp3" and phan[2].get_content_type() == "audio/mpeg"
    assert phan[2].get_payload(decode=True) == b"\xff\xfb\x00\x01"


def test_chuan_hoa_muc_tu_bam_va_nhan_zh_hans():
    m = tao.chuan_hoa_muc({"id": 7, "slug": "x", "language": "zh-Hans", "shortText": "下龙湾。"})
    assert m["heritageId"] == 7 and m["language"] == "zh" and m["voice"] == "melo-zh" and m["textHash"] == tao.bam("下龙湾。")
    with pytest.raises(ValueError):
        tao.chuan_hoa_muc({"id": 8, "language": "fr", "shortText": "x"})


# ---- Chế độ lặp (--lap-den) ----

class DongHoGia:
    """Đồng hồ giả: ngu() chỉ cộng giờ, ghi số giây và gọi móc để test đổi dữ liệu giữa hai lượt."""

    def __init__(self, bat_dau: str, moc=None):
        self.t = datetime.strptime(bat_dau, "%Y-%m-%d %H:%M").timestamp()
        self.moc = moc or (lambda lan, dong_ho: None)
        self.giay_nghi: list[float] = []

    def __call__(self) -> float:
        return self.t

    def ngu(self, giay: float) -> None:
        self.giay_nghi.append(giay)
        self.t += giay
        self.moc(len(self.giay_nghi), self)


def tham_so_lap(api: str, ra: Path, *them: str) -> list[str]:
    return ["--api", api, "--ra", str(ra), "--username", "admin.vietnamheritage", *them]


def test_lap_nhat_muc_moi_giua_hai_luot_ngon_ngu_sau_cho_tep_va_dung_som(may_chu, tmp_path, monkeypatch, capsys, mat_khau_an):
    api, tt = may_chu
    monkeypatch.setitem(TOM_TAT, (4, "ko"), "하롱베이는 석회암 섬으로 유명합니다.")
    monkeypatch.setattr(tao, "chay_may_doc", may_doc_gia([]))
    tep_duyet = tmp_path / "duyet-xong.txt"
    da_tai_luc_nghi: list[set] = []

    def moc(lan, dong_ho):
        da_tai_luc_nghi.append(set(tt.da_tai))
        if lan == 1:
            monkeypatch.setitem(TOM_TAT, (6, "vi"), "Phố cổ Hội An có nhiều nhà gỗ. Chùa Cầu nằm ở phía tây.")   # xuất hiện sau
            tt.token_lay_het_han.add("token-1")                                                  # phiên hết hạn giữa hai lượt
        else:
            tep_duyet.write_text("xong", encoding="utf-8")

    dong_ho = DongHoGia("2026-10-20 22:00", moc)
    ma = tao.main(tham_so_lap(api, tmp_path / "ra", "--languages", "vi,en,ko", "--lap-den", "2026-10-21 08:00",
                              "--cho-tep", str(tep_duyet)), dong_ho=dong_ho, ngu=dong_ho.ngu)

    assert ma == 0
    assert set(tt.da_tai) == {(1, "vi"), (2, "vi"), (3, "en"), (6, "vi"), (4, "ko")}
    # Nghỉ đúng hai lần 5 phút; lượt đầu đã xong vi và en, trước khi có tệp duyệt không có mục tiếng Hàn nào được tải
    assert dong_ho.giay_nghi == [300, 300]
    assert da_tai_luc_nghi[0] == {(1, "vi"), (2, "vi"), (3, "en")}
    assert (4, "ko") not in da_tai_luc_nghi[1] and (6, "vi") in da_tai_luc_nghi[1]
    # Dừng sớm khi đủ (còn xa giờ chốt); đăng nhập thêm một lần vì 401, mật khẩu chỉ hỏi một lần
    assert dong_ho.t < datetime.strptime("2026-10-21 08:00", "%Y-%m-%d %H:%M").timestamp()
    assert tt.so_lan_dang_nhap == 2 and len(mat_khau_an) == 1
    nk = doc_nhat_ky(tmp_path / "ra")
    assert [d["language"] for d in nk if d["buoc"] == "tải lên"] == ["vi", "vi", "en", "vi", "ko"]
    ra = capsys.readouterr().out
    assert "Lượt 1: vi thiếu 2 tải 2, en thiếu 1 tải 1, ko chờ tệp duyệt" in ra
    assert "Dừng sau 6 lượt: mọi ngôn ngữ đã đủ." in ra
    assert MAT_KHAU not in ra and "token-" not in "".join(",".join(d.values()) for d in nk)


def test_lap_dung_o_gio_chot_khi_tep_duyet_khong_co(may_chu, tmp_path, monkeypatch, capsys, mat_khau_an):
    api, tt = may_chu
    monkeypatch.setitem(TOM_TAT, (4, "ko"), "하롱베이는 석회암 섬으로 유명합니다.")
    monkeypatch.setattr(tao, "chay_may_doc", may_doc_gia([]))
    dong_ho = DongHoGia("2026-10-20 23:55")

    ma = tao.main(tham_so_lap(api, tmp_path, "--languages", "vi,en,ko", "--lap-den", "2026-10-21 00:12",
                              "--cho-tep", str(tmp_path / "khong-co.txt")), dong_ho=dong_ho, ngu=dong_ho.ngu)

    assert ma == 0
    assert set(tt.da_tai) == {(1, "vi"), (2, "vi"), (3, "en")}          # tiếng Hàn chưa bao giờ bị đụng tới
    assert dong_ho.giay_nghi == [300, 300, 300, 120]                    # lần cuối chỉ nghỉ tới đúng giờ chốt
    assert dong_ho.t == datetime.strptime("2026-10-21 00:12", "%Y-%m-%d %H:%M").timestamp()
    assert "Dừng sau 5 lượt: hết giờ." in capsys.readouterr().out


def test_lap_het_gio_giua_chung_thi_khong_mo_lo_moi_nhung_van_tai_phan_da_tao(may_chu, tmp_path, monkeypatch, capsys, mat_khau_an):
    api, tt = may_chu
    monkeypatch.setattr(tao, "LO_TOI_DA", 1)
    dong_ho = DongHoGia("2026-10-20 23:50")
    goi_lai: list = []
    may_doc = may_doc_gia(goi_lai)

    def may_doc_cham(dong_co, tep_viec, cau_hinh):
        dong_ho.t += 600                                                # mỗi lô mất 10 phút: lô đầu làm qua 00:00
        return may_doc(dong_co, tep_viec, cau_hinh)
    monkeypatch.setattr(tao, "chay_may_doc", may_doc_cham)

    ma = tao.main(tham_so_lap(api, tmp_path, "--languages", "vi", "--lap-den", "2026-10-21 00:00"),
                  dong_ho=dong_ho, ngu=dong_ho.ngu)

    assert ma == 0
    assert len(goi_lai) == 1 and set(tt.da_tai) == {(1, "vi")}          # mục 2 để lại; mục 1 đã tạo thì vẫn tải xong
    assert dong_ho.giay_nghi == []
    assert "Dừng sau 1 lượt: hết giờ." in capsys.readouterr().out


def test_lap_mang_chap_chon_thi_nghi_roi_thu_lai(may_chu, tmp_path, monkeypatch, capsys, mat_khau_an):
    api, tt = may_chu
    monkeypatch.setattr(tao, "chay_may_doc", may_doc_gia([]))
    lay_that = tao.KhachApi.lay_thieu
    loi_mot_lan = [True]

    def lay_hong(self, ngon_ngu, limit):
        if loi_mot_lan:
            loi_mot_lan.pop()
            raise urllib.error.URLError("mất mạng")
        return lay_that(self, ngon_ngu, limit)
    monkeypatch.setattr(tao.KhachApi, "lay_thieu", lay_hong)
    dong_ho = DongHoGia("2026-10-20 22:00")

    ma = tao.main(tham_so_lap(api, tmp_path, "--languages", "vi", "--lap-den", "2026-10-21 08:00", "--nghi", "1"),
                  dong_ho=dong_ho, ngu=dong_ho.ngu)

    assert ma == 0 and set(tt.da_tai) == {(1, "vi"), (2, "vi")} and dong_ho.giay_nghi == [60]
    ra = capsys.readouterr().out
    assert "Lượt 1: lỗi mạng" in ra and "Dừng sau 3 lượt: mọi ngôn ngữ đã đủ." in ra


def test_tham_so_lap_sai_thi_bao_loi_va_mac_dinh_ngon_ngu_sau(tmp_path):
    for sai in (["--lap-den", "21/10/2026 08:00"], ["--lap-den", "2026-10-21 08:00", "--dry-run"],
                ["--lap-den", "2026-10-21 08:00", "--cuc-bo", "x.json"], ["--ngon-ngu-sau", "ko"],
                ["--cho-tep", "x", "--ngon-ngu-sau", "fr"], ["--nghi", "0"]):
        with pytest.raises(SystemExit):
            tao.doc_tham_so(sai)
    a = tao.doc_tham_so(["--cho-tep", str(tmp_path / "x")])
    assert a.ngon_ngu_sau == ["ko", "zh", "ja"] and a.lap_den is None and a.nghi == 5
    assert tao.doc_tham_so([]).ngon_ngu_sau == []
