"""Gọi API của backend (urllib, không phụ thuộc thư viện ngoài) cho các script đánh giá. Dùng được từ nhiều luồng cùng lúc.

Biến môi trường: BASE (mặc định http://localhost:5090), API_LOG (tệp log của backend, để đọc liên kết đặt mật khẩu khi Email:Mode=Log),
ADMIN_LOGIN (mặc định admin.nho), ADMIN_PASSWORD (không bao giờ in ra hay ghi ra tệp).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CONG_CAM = {5080, 8080, 8081, 8082, 8090}  # cổng của các backend khác: không bao giờ đo trên đó


class LoiApi(RuntimeError):
    pass


class Backend:
    def __init__(self, base: str | None = None, log: str | None = None) -> None:
        self.base = (base or os.environ.get("BASE", "http://localhost:5090")).rstrip("/")
        cong = urllib.parse.urlparse(self.base).port
        if cong in CONG_CAM:
            sys.exit(f"Từ chối chạy trên cổng {cong}: đó là backend khác. Dùng backend tạm (xem README, cổng 5090).")
        self.log = log or os.environ.get("API_LOG")

    def call(self, method: str, path: str, body: object | None = None, token: str | None = None, timeout: int = 180) -> tuple[dict, int]:
        du_lieu = None
        dau = {"Accept": "application/json"}
        if body is not None:
            du_lieu = json.dumps(body, ensure_ascii=False).encode("utf-8")
            dau["Content-Type"] = "application/json; charset=utf-8"
        if token:
            dau["Authorization"] = "Bearer " + token
        yeu_cau = urllib.request.Request(self.base + "/api/v1" + path, data=du_lieu, headers=dau, method=method)
        for lan in range(3):
            try:
                with urllib.request.urlopen(yeu_cau, timeout=timeout) as r:
                    ma, tho = r.status, r.read()
                break
            except urllib.error.HTTPError as e:
                ma, tho = e.code, e.read()
                break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                if lan == 2:
                    raise
                time.sleep(1 + lan)
        try:
            noi_dung = json.loads(tho.decode("utf-8")) if tho else {}
        except ValueError:
            noi_dung = {}
        return noi_dung, ma

    def can(self, method: str, path: str, body: object | None = None, token: str | None = None, mong: int = 200):
        """Gọi và bắt buộc đúng mã mong đợi; trả `data`. Sai thì dừng cả script kèm thông điệp."""
        noi_dung, ma = self.call(method, path, body, token)
        if ma != mong:
            raise LoiApi(f"{method} {path}: mong {mong}, nhận {ma}: {str(noi_dung)[:400]}")
        return noi_dung.get("data")

    def ma_trong_thu(self, email: str) -> str:
        """Lấy mã trong liên kết đặt mật khẩu từ log backend (Email:Mode=Log)."""
        if not self.log:
            raise LoiApi("Thiếu API_LOG: cần tệp log của backend để đọc liên kết đặt mật khẩu.")
        email = email.lower()
        for _ in range(100):
            chu = Path(self.log).read_text(encoding="utf-8", errors="replace")
            vi_tri = chu.lower().rfind("tới: " + email)
            if vi_tri < 0:
                vi_tri = chu.lower().rfind(": " + email + " |")
            if vi_tri >= 0:
                m = re.search(r"token=([A-Za-z0-9_\-%]+)", chu[vi_tri:])
                if m:
                    return m.group(1)
            time.sleep(0.3)
        raise LoiApi("không thấy thư tới " + email + " trong log backend (backend phải chạy với Email:Mode=Log)")

    def dang_nhap_quan_tri(self) -> str:
        mat_khau = os.environ.get("ADMIN_PASSWORD")
        if not mat_khau:
            sys.exit("Thiếu ADMIN_PASSWORD (mật khẩu quản trị hệ thống của backend tạm). Chạy qua chay-danh-gia.ps1 để tự lấy từ User Secrets.")
        d = self.can("POST", "/auth/login", {"emailOrUsername": os.environ.get("ADMIN_LOGIN", "admin.nho"), "password": mat_khau})
        return d["accessToken"]

    def xuat_ban_di_san(self, quan_tri: str) -> int:
        """Xuất bản mọi di sản đang nháp; trả số di sản đã xuất bản."""
        nhap = self.can("GET", "/admin/heritages?status=DRAFT&pageSize=100", token=quan_tri)["items"]
        for h in sorted(nhap, key=lambda x: x["id"]):
            self.call("POST", f"/admin/heritages/{h['id']}/publish", token=quan_tri)
        return len(self.can("GET", "/admin/heritages?status=PUBLISHED&pageSize=100", token=quan_tri)["items"])


def lay_di_san_cong_khai(backend: Backend, kem_anh_su_kien: bool = False) -> list[dict]:
    """Mọi di sản đã xuất bản qua API công khai (không cần đăng nhập), sắp theo mã.

    Mỗi phần tử là chi tiết di sản (`/public/heritages/{slug}`) cộng `provinceId` và `shortDescription` của thẻ danh sách.
    `kem_anh_su_kien`: thêm khóa `anhSuKien` (ảnh của các sự kiện trên dòng thời gian, thuộc thư viện ảnh của di sản).
    """
    the: list[dict] = []
    trang = 1
    while True:
        d = backend.can("GET", f"/public/heritages?pageSize=100&page={trang}")
        the.extend(d["items"])
        if trang >= d.get("totalPages", 1):
            break
        trang += 1
    ra = []
    for t in sorted(the, key=lambda x: x["id"]):
        chi_tiet = backend.can("GET", "/public/heritages/" + urllib.parse.quote(t["slug"]))
        chi_tiet["provinceId"] = t["provinceId"]
        chi_tiet["shortDescription"] = t.get("shortDescription") or chi_tiet.get("shortDescription")
        if kem_anh_su_kien:
            dong = backend.can("GET", "/public/heritages/" + urllib.parse.quote(t["slug"]) + "/timeline")
            chi_tiet["anhSuKien"] = [m for g in dong.get("phases", []) for e in g.get("events", []) for m in e.get("media", [])]
        ra.append(chi_tiet)
    return ra
