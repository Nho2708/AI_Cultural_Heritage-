"""Chạy nối: backend (Ai:Mode=Remote) -> dịch vụ AI -> backend, qua API thật của backend trên CƠ SỞ DỮ LIỆU TẠM.

Các bước: xuất bản di sản; dịch và tóm tắt một di sản sang 4 ngôn ngữ; tạo trường, giáo viên, ba lớp (khối 3, 8, 11);
soạn bài học cho mỗi lớp; sinh câu hỏi cho mỗi lớp; gợi ý di sản liên quan cho khách.

Biến môi trường: BASE (mặc định http://localhost:5090), ADMIN_LOGIN, ADMIN_PASSWORD (mật khẩu quản trị của backend tạm),
API_LOG (tệp log của backend, để đọc liên kết đặt mật khẩu khi Email:Mode=Log), AI_URL (mặc định http://localhost:8000).
Không in mật khẩu hay khóa. Thoát với mã 1 nếu có bước lỗi.
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("BASE", "http://localhost:5090").rstrip("/")
AI_URL = os.environ.get("AI_URL", "http://localhost:8000").rstrip("/")
API_LOG = os.environ["API_LOG"]
ADMIN_LOGIN = os.environ.get("ADMIN_LOGIN", "admin.huy")
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
PW = "MatKhau2026"
SUFFIX = datetime.datetime.now().strftime("%H%M%S")
LEVEL_OF_GRADE = {3: 1, 8: 2, 11: 3}
FRAME = {1: (150, 250), 2: (300, 500), 3: (600, 900)}
TYPES_OF_LEVEL = {1: {"TRUE_FALSE", "IMAGE_CHOICE", "MATCHING", "ORDERING"},
                  2: {"SINGLE_CHOICE", "TRUE_FALSE", "ORDERING", "FILL_BLANK"},
                  3: {"SINGLE_CHOICE", "MULTI_TRUE_FALSE", "SOURCE_READING"}}
failures = []


def check(name, ok, detail=""):
    print(("DAT  " if ok else "LOI  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures.append(name)
    return ok


def call(method, path, body=None, token=None, headers=None, timeout=180):
    data = None
    h = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json; charset=utf-8"
    if token:
        h["Authorization"] = "Bearer " + token
    h.update(headers or {})
    req = urllib.request.Request(BASE + "/api/v1" + path, data=data, headers=h, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        payload = {}
    return payload, status, time.perf_counter() - started


def need(method, path, body=None, token=None, expect=200, headers=None):
    payload, status, _ = call(method, path, body, token, headers)
    if status != expect:
        sys.exit(f"{method} {path}: mong {expect}, nhận {status}: {str(payload)[:300]}")
    return payload.get("data")


def mail_token(email):
    email = email.lower()
    for _ in range(60):
        text = open(API_LOG, encoding="utf-8", errors="replace").read()
        pos = text.lower().rfind("tới: " + email)
        if pos < 0:
            pos = text.lower().rfind(": " + email + " |")
        if pos >= 0:
            m = re.search(r"token=([A-Za-z0-9_\-%]+)", text[pos:])
            if m:
                return m.group(1)
        time.sleep(0.3)
    sys.exit("không thấy thư tới " + email)


def words(text):
    return len((text or "").split())


# ---- Quản trị: di sản ----
admin = need("POST", "/auth/login", {"emailOrUsername": ADMIN_LOGIN, "password": ADMIN_PASSWORD})
A = admin["accessToken"]
drafts = need("GET", "/admin/heritages?status=DRAFT&pageSize=100", token=A)["items"]
published = 0
for h in sorted(drafts, key=lambda item: item["id"]):
    _, st, _ = call("POST", f"/admin/heritages/{h['id']}/publish", token=A)
    published += st == 200
items = need("GET", "/admin/heritages?status=PUBLISHED&pageSize=100", token=A)["items"]
check("có di sản đã xuất bản", len(items) >= 3, f"{len(items)} di sản ({published} vừa xuất bản)")
H = next((p["id"] for p in items if p["slug"].startswith("khu-trung-tam-hoang-thanh")), items[0]["id"])

# ---- Dịch và tóm tắt (1 lần tóm tắt tiếng Việt + 4 lần dịch) ----
payload, status, secs = call("POST", f"/admin/heritages/{H}/translations/generate", {}, token=A)
check("dịch và tóm tắt di sản (200)", status == 200, f"{status} trong {secs:.1f}s {payload.get('errorCode') or ''}")
for lang in ("en", "ko", "zh-Hans", "ja"):
    d, st, _ = call("GET", f"/admin/heritages/{H}/translations/{lang}/translation", token=A)
    t = (d or {}).get("data", {}).get("translated") if st == 200 else None
    check(f"bản dịch {lang} có tên và nội dung", bool(t and t.get("name") and t.get("content")), f"trạng thái {(d or {}).get('data', {}).get('status')}")
for lang in ("vi", "en", "ko", "zh-Hans", "ja"):
    d, st, _ = call("GET", f"/admin/heritages/{H}/translations/{lang}/summary", token=A)
    s = (d or {}).get("data", {}).get("summary") if st == 200 else None
    check(f"tóm tắt {lang}", bool(s and s.get("shortText") and s.get("detailedText")),
          f"ngắn {words((s or {}).get('shortText'))} từ, chi tiết {words((s or {}).get('detailedText'))} từ")

# ---- Trường, giáo viên, lớp ----
org_mail = f"thu.{SUFFIX}@tam.edu.vn"
need("POST", "/admin/organizations", {"name": f"Trường thử nghiệm {SUFFIX}", "orgAdmin": {
    "fullName": "Lê Thị Thu", "username": f"thu.{SUFFIX}", "email": org_mail}}, token=A, expect=201)
need("POST", "/auth/set-password", {"token": mail_token(org_mail), "newPassword": PW})
thu = need("POST", "/auth/login", {"emailOrUsername": f"thu.{SUFFIX}", "password": PW})
tmail = f"linh.{SUFFIX}@tam.edu.vn"
need("POST", "/org/teachers", {"fullName": "Đặng Thị Mỹ Linh", "username": f"linh.{SUFFIX}", "email": tmail}, token=thu["accessToken"], expect=201)
need("POST", "/auth/set-password", {"token": mail_token(tmail), "newPassword": PW})
T = need("POST", "/auth/login", {"emailOrUsername": f"linh.{SUFFIX}", "password": PW})["accessToken"]
quota = need("GET", "/teacher/lessons/ai-quota", token=T)
print(f"     hạn mức lượt AI của gói: {quota}")

# ---- Soạn bài học và sinh câu hỏi cho mỗi cấp ----
lesson_ids = {}
for grade, name in ((3, "3A"), (8, "8A1"), (11, "11A2")):
    level = LEVEL_OF_GRADE[grade]
    cls = need("POST", "/teacher/classes", {"name": name, "grade": grade, "schoolYear": "2026-2027"}, token=T, expect=201)
    les = need("POST", "/teacher/lessons", {"classId": cls["id"], "title": f"Di sản khối {grade}", "heritageIds": [H]}, token=T, expect=201)
    lesson_ids[grade] = les["id"]

    payload, status, secs = call("POST", f"/teacher/lessons/{les['id']}/ai/compose", {"length": "MEDIUM"}, token=T)
    d = payload.get("data") or {}
    ok = status == 200
    check(f"soạn bài cấp {level} (khối {grade})", ok, f"{status} trong {secs:.1f}s {payload.get('errorCode') or ''}")
    if ok:
        lo, hi = FRAME[level]
        n = d.get("wordCount") or words(d.get("summary"))
        check(f"  số từ cấp {level} trong khung {lo}-{hi}", lo <= n <= hi, f"{n} từ; cảnh báo={d.get('warnings', [])}")
        kinds = sorted({s["type"] for s in d["sections"]})
        check(f"  phần theo khung cấp {level}", bool(d["sections"]), ",".join(kinds))
        check(f"  3-7 ý chính", 3 <= len(d["keyPoints"]) <= 7, str(len(d["keyPoints"])))

    payload, status, secs = call("POST", f"/teacher/lessons/{les['id']}/ai/questions", {"count": 6, "difficultyLevel": "MEDIUM"}, token=T)
    d = payload.get("data") or {}
    qs = d.get("questions") or d.get("items") or []
    check(f"sinh câu hỏi cấp {level} (khối {grade})", status == 200 and len(qs) >= 1,
          f"{status} trong {secs:.1f}s, {len(qs)} câu {payload.get('errorCode') or ''}")
    if status == 200:
        got = {q.get("questionType") for q in qs}
        check(f"  dạng câu thuộc cấp {level}", bool(got) and got <= TYPES_OF_LEVEL[level], ",".join(sorted(x for x in got if x)))

# ---- Gợi ý liên quan cho khách (rank-related) ----
payload, status, _ = call("POST", "/public/guest/devices", {"platform": "WEB"})
key = ((payload or {}).get("data") or {}).get("deviceKey")
check("tạo thiết bị khách", bool(key), str(status))
if key:
    hdr = {"X-Device-Key": key, "X-Client-Platform": "WEB"}
    recorded = 0
    for p in items[:3]:
        d, st, _ = call("POST", "/public/guest/activities", {"type": "VIEW", "slug": p["slug"]}, headers=hdr)
        recorded += bool(((d or {}).get("data") or {}).get("recorded"))
    check("ghi lượt xem di sản của khách", recorded >= 1, f"{recorded} lượt")
    payload, status, secs = call("GET", "/public/guest/recommendations?lang=vi", headers=hdr)
    d = payload.get("data") or {}
    its = d.get("items") or []
    check("gợi ý cho khách dùng kết quả của dịch vụ AI (không dự phòng)",
          status == 200 and d.get("isPersonalized") and not d.get("usedFallback") and len(its) >= 1,
          f"{status} trong {secs:.2f}s; {len(its)} mục; cá nhân hóa={d.get('isPersonalized')}; dự phòng={d.get('usedFallback')}; "
          f"lý do={[r for i in its[:1] for r in i.get('reasons', [])]}")

# ---- Sai khóa nội bộ gọi thẳng dịch vụ AI ----
req = urllib.request.Request(AI_URL + "/v1/rank-related", data=b"{}", headers={"Content-Type": "application/json", "X-Internal-Key": "sai-khoa"}, method="POST")
try:
    urllib.request.urlopen(req, timeout=10)
    code = 200
except urllib.error.HTTPError as e:
    code = e.code
check("dịch vụ AI từ chối khóa nội bộ sai bằng 401", code == 401, str(code))

print("\nTổng kết:", "TẤT CẢ ĐẠT" if not failures else "CÓ LỖI: " + "; ".join(failures))
sys.exit(1 if failures else 0)
