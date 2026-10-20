"""Tiến trình tạo thuyết minh (tools/thuyet-minh/tao_thuyet_minh.py) chạy trước một API quản trị giả bằng http.server:
đăng nhập, lấy danh sách thiếu, gọi máy đọc (thay bằng bản giả), tải lên multipart, đăng nhập lại khi 401, bỏ qua khi 409,
chạy lại chỉ dùng lại âm thanh đã có, chế độ cục bộ không mạng. Không cần gói nào ngoài thư viện chuẩn."""
from __future__ import annotations

import json
import sys
import threading
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
        if self._token() not in {f"token-{i}" for i in range(1, tt.so_lan_dang_nhap + 1)}:
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
