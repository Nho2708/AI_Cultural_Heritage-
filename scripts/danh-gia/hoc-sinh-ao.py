"""Học sinh ảo và gợi ý cá nhân hóa: dựng lớp ở cả 3 cấp trên backend TẠM, cho khoảng 200 em ảo mỗi mức nhiễu làm 2 bài kiểm tra bằng đáp án mô phỏng
từ THAM SỐ CỐ ĐỊNH ngay dưới đây, đọc "Gợi ý cho em" của từng em từ backend rồi đo so với các đường cơ sở.

Đo: trúng di sản yếu (hit@3) ở 3 mức nhiễu và phần "di sản nên ôn"; độ khó khớp mức của em; tác động của khối lớp với em chưa có lượt nào;
gợi ý đúng lớp. Chỉ gọi API của backend tạm (Ai:Mode=Simulated, email chỉ ghi log); không gọi mô hình ngôn ngữ.

    # qua chay-danh-gia.ps1 (khuyến nghị: tự dựng và xóa backend, cơ sở dữ liệu tạm)
    pwsh -File scripts/danh-gia/chay-danh-gia.ps1 -Phan goi-y-ca-nhan
    # hoặc tự chạy trên backend tạm đã có
    BASE=http://localhost:5090 API_LOG=<log backend> ADMIN_PASSWORD=<mật khẩu quản trị tạm> python scripts/danh-gia/hoc-sinh-ao.py --out <thư mục>
    python scripts/danh-gia/hoc-sinh-ao.py --thu-nho --out <thư mục>     # cỡ nhỏ để thử đường đi (vài phút)

Kết quả: hoc-sinh-ao.md (báo cáo tiếng Việt, bảng) và hoc-sinh-ao.json (số liệu thô) trong --out. Không đưa vào git.
Mã thoát: 0 xong; 1 có bước lỗi.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import os
import random
import sys
import time
from pathlib import Path

QUI_MUC = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI_MUC))
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]

import danh_gia_chung as dg
from backend_api import Backend, LoiApi, lay_di_san_cong_khai
from cau_hoi_mau import SO_CAU_MOI_DI_SAN, CauHoi, DiSan, NhanHienThi, dap_an_gui_len, tao_cau_hoi_cho_di_san

# =====================================================================================================================
# THAM SỐ MÔ PHỎNG: chốt trước khi đo, in ra đầu báo cáo. Đổi một giá trị là đo lại từ đầu và phải ghi vào báo cáo.
# =====================================================================================================================
HAT_GIONG = 20261013
# Ở di sản YẾU em đoán đúng với xác suất này (câu 4 phương án 25%, câu đúng/sai 50%; chọn hình 3 hình 1/3 vì thư viện ảnh một số di sản chỉ có 3 hình).
XAC_SUAT_DOAN_DI_SAN_YEU = {dg.KIEU_4_PHUONG_AN: 0.25, dg.KIEU_3_PHUONG_AN: 1 / 3, dg.KIEU_DUNG_SAI: 0.5}
# Ở di sản đã VỮNG em nhầm với tỉ lệ này: ba mức nhiễu.
MUC_NHIEU = (("thấp", 0.10), ("vừa", 0.15), ("cao", 0.20))
# Kiểu em: yếu (phần lớn di sản em gặp là yếu), trung bình (đúng một di sản yếu), vững (không có di sản yếu).
TY_LE_NHOM = {"yeu": 0.20, "trung_binh": 0.55, "vung": 0.25}
TY_LE_DI_SAN_YEU_O_NHOM_YEU = 0.85
SO_BAI_MOI_EM = 2  # mỗi em làm 2 bài kiểm tra
SO_BAI_HOC_MOI_LOP = 10  # mỗi lớp 10 bài học đã xuất bản, mỗi bài một bài kiểm tra đang mở
SO_DI_SAN_MOI_BAI = 4
# SO_CAU_MOI_DI_SAN = 4 (khai báo ở cau_hoi_mau.py): mỗi bài kiểm tra 16 câu, hai câu nhiều phương án và hai câu đúng/sai cho mỗi di sản
SO_HOC_SINH_MOI_LOP = 60  # mỗi mức nhiễu x mỗi cấp một lớp 60 em (tối đa của một lớp) = 180 em mỗi mức nhiễu
SO_LOP_CHUA_LAM_MOI_CAP = 5  # nhóm em chưa có lượt nào: 5 lớp mỗi cấp, mỗi lớp một cách xếp nội dung khác nhau
SO_HOC_SINH_CHUA_LAM_MOI_LOP = 8  # mỗi lớp 8 em, tức 40 em mỗi cấp
KHOI_THEO_CAP = {1: 3, 2: 8, 3: 11}  # khối lớp đại diện cho cấp 1, 2, 3
THOI_GIAN_LAM_THEO_CAP = {1: None, 2: None, 3: 30}  # phút; cấp 3 bắt buộc có thời gian làm
KIEU_HAN_DONG_MAC_DINH = "khac-nhau"  # hạn đóng mỗi bài kiểm tra một ngày khác nhau (cung-ngay: tất cả cùng ngày)
MAT_KHAU_HOC_SINH = "DanhGia2026Vh"
SO_LUONG_SONG_SONG = 6
# =====================================================================================================================

TEN_NHOM = {"yeu": "yếu", "trung_binh": "trung bình", "vung": "vững", "chua_lam": "chưa có lượt"}
CAP_TEN = {1: "cấp 1", 2: "cấp 2", 3: "cấp 3"}


def in_tham_so(hat: int, so_hs: int, so_chua: int, so_lop_chua: int, kieu_han: str) -> str:
    dong = [
        "| Tham số | Giá trị |", "|---|---|",
        f"| Hạt giống ngẫu nhiên | {hat} |",
        (f"| Xác suất đúng ở di sản yếu | câu 4 phương án {XAC_SUAT_DOAN_DI_SAN_YEU[dg.KIEU_4_PHUONG_AN]:.0%}; câu đúng/sai {XAC_SUAT_DOAN_DI_SAN_YEU[dg.KIEU_DUNG_SAI]:.0%}; "
         f"chọn hình 3 hình {XAC_SUAT_DOAN_DI_SAN_YEU[dg.KIEU_3_PHUONG_AN]:.1%} |"),
        "| Tỉ lệ nhầm ở di sản đã vững (3 mức nhiễu) | " + "; ".join(f"{t} {v:.0%}" for t, v in MUC_NHIEU) + " |",
        "| Nhóm em (tỉ lệ) | " + "; ".join(f"{TEN_NHOM[k]} {v:.0%}" for k, v in TY_LE_NHOM.items()) + f" (nhóm yếu: {TY_LE_DI_SAN_YEU_O_NHOM_YEU:.0%} di sản em gặp là yếu; nhóm trung bình: đúng một di sản yếu; nhóm vững: không có) |",
        f"| Số bài kiểm tra mỗi em làm | {SO_BAI_MOI_EM}, chọn ngẫu nhiên trong {SO_BAI_HOC_MOI_LOP} bài của lớp |",
        f"| Mỗi lớp | {SO_BAI_HOC_MOI_LOP} bài học đã xuất bản, mỗi bài {SO_DI_SAN_MOI_BAI} di sản và một bài kiểm tra {SO_DI_SAN_MOI_BAI * SO_CAU_MOI_DI_SAN} câu ({SO_CAU_MOI_DI_SAN} câu mỗi di sản); mỗi di sản xuất hiện trong 2 bài |",
        f"| Số em | {so_hs} em mỗi lớp x 3 cấp x 3 mức nhiễu; em chưa có lượt: {so_lop_chua} lớp x {so_chua} em mỗi cấp |",
        f"| Khối lớp đại diện | cấp 1 = khối {KHOI_THEO_CAP[1]}, cấp 2 = khối {KHOI_THEO_CAP[2]}, cấp 3 = khối {KHOI_THEO_CAP[3]} |",
        f"| Hạn đóng các bài kiểm tra | {'mỗi bài một ngày khác nhau' if kieu_han == 'khac-nhau' else 'tất cả cùng một ngày'} |",
        "| Độ khó các bài kiểm tra | chia đều Dễ, Trung bình, Khó rồi xáo theo hạt giống; lớp chưa có lượt xếp lại độ khó, thứ tự tạo và hạn đóng (độ khó của từng câu không ảnh hưởng gợi ý, backend dùng độ khó của bài kiểm tra) |",
    ]
    return "\n".join(dong)


# --------------------------------------------------------------------------------------------------------------------
# Dựng trường, giáo viên, nội dung lớp
# --------------------------------------------------------------------------------------------------------------------

def gio(phut: float) -> str:
    return (datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=phut)).strftime("%Y-%m-%dT%H:%M:%SZ")


def nang_han_muc_ai(api: Backend, quan_tri: str, can_it_nhat: int) -> None:
    """Gói Miễn phí của môi trường phát triển chỉ có 300 lượt AI; mỗi bài học soạn bằng AI giả lập tốn một lượt, nên nâng hạn mức trong backend tạm."""
    goi = next(g for g in api.can("GET", "/admin/plans", token=quan_tri) if g["isFree"])
    if goi["maxAiRequests"] is None or goi["maxAiRequests"] >= can_it_nhat:
        return
    api.can("PUT", f"/admin/plans/{goi['id']}", {"name": goi["name"], "price": goi["price"], "durationDays": goi["durationDays"],
                                                 "maxTeachers": goi["maxTeachers"], "maxAiRequests": can_it_nhat}, quan_tri)


def dung_truong(api: Backend, quan_tri: str, hau_to: str) -> dict[int, str]:
    """Một trường, quản trị trường, ba giáo viên (mỗi cấp một giáo viên). Trả token giáo viên theo cấp."""
    mat_khau = "GiaoVien2026Vh"
    email_qt = f"truong.{hau_to}@danhgia.local"
    api.can("POST", "/admin/organizations", {"name": f"Trường đánh giá gợi ý {hau_to}", "address": "Hà Nội",
                                             "orgAdmin": {"fullName": "Nguyễn Thị Đánh Giá", "username": f"truong.{hau_to}", "email": email_qt}}, quan_tri, 201)
    api.can("POST", "/auth/set-password", {"token": api.ma_trong_thu(email_qt), "newPassword": mat_khau})
    qt = api.can("POST", "/auth/login", {"emailOrUsername": f"truong.{hau_to}", "password": mat_khau})["accessToken"]
    token: dict[int, str] = {}
    for cap in (1, 2, 3):
        email = f"gv{cap}.{hau_to}@danhgia.local"
        api.can("POST", "/org/teachers", {"fullName": f"Giáo viên cấp {cap}", "username": f"gv{cap}.{hau_to}", "email": email}, qt, 201)
        api.can("POST", "/auth/set-password", {"token": api.ma_trong_thu(email), "newPassword": mat_khau})
        token[cap] = api.can("POST", "/auth/login", {"emailOrUsername": f"gv{cap}.{hau_to}", "password": mat_khau})["accessToken"]
    return token


def doc_di_san(api: Backend) -> tuple[list[DiSan], NhanHienThi]:
    chi_tiet = lay_di_san_cong_khai(api)
    loc = api.can("GET", "/public/filters")
    nhan = NhanHienThi(
        loai={x["value"]: x["label"] for x in loc["heritageTypes"]},
        cap={x["value"]: x["label"] for x in loc["recognitionLevels"]},
        tinh=tuple(p["name"] for p in loc["provinces"]),
    )
    ra = []
    for d in chi_tiet:
        anh = tuple((m["url"], m.get("caption") or d["name"]) for m in d["media"] if m.get("mediaType", "IMAGE") == "IMAGE")
        ra.append(DiSan(d["id"], d["name"], d["provinceId"], d["province"]["name"], d["province"]["region"], d["heritageType"],
                        d["recognitionLevel"], d.get("recognizedYear"), anh))
    return ra, nhan


def bien_the_ke_hoach(ke_hoach: list[dict], cau_hoi: list, rng: random.Random, kieu_han: str) -> tuple[list[dict], list]:
    """Cùng các bài (di sản, câu hỏi) nhưng thứ tự tạo, độ khó và hạn đóng xếp khác: một lần rút nội dung lớp khác."""
    thu_tu = rng.sample(range(len(ke_hoach)), len(ke_hoach))
    do_kho = [dg.DO_KHO[i % 3] for i in range(len(ke_hoach))]
    rng.shuffle(do_kho)
    ngay = list(range(len(ke_hoach)))
    rng.shuffle(ngay)
    moi = []
    for vi_tri, p in enumerate(thu_tu):
        moi.append({"di_san": ke_hoach[p]["di_san"], "do_kho": do_kho[vi_tri], "han_dong": 21 + 3 * ngay[vi_tri] if kieu_han == "khac-nhau" else 30})
    return moi, [cau_hoi[p] for p in thu_tu]


def ke_hoach_cap(cap: int, ma_di_san: list[int], so_bai: int, rng: random.Random, kieu_han: str) -> list[dict]:
    """Kế hoạch bài học của một cấp (dùng chung cho mọi lớp cùng cấp): di sản, độ khó, hạn đóng. Mỗi di sản xuất hiện trong đúng 2 bài."""
    thu_tu = rng.sample(ma_di_san, len(ma_di_san))
    buoc = len(thu_tu) // so_bai
    do_kho = [dg.DO_KHO[i % 3] for i in range(so_bai)]
    rng.shuffle(do_kho)
    ngay = list(range(so_bai))
    rng.shuffle(ngay)
    ra = []
    for i in range(so_bai):
        ra.append({
            "di_san": [thu_tu[(buoc * i + j) % len(thu_tu)] for j in range(SO_DI_SAN_MOI_BAI)],
            "do_kho": do_kho[i],
            "han_dong": 21 + 3 * ngay[i] if kieu_han == "khac-nhau" else 30,
        })
    return ra


def tao_cau_hoi_cua_cap(api: Backend, gv: str, cap: int, ke_hoach: list[dict], theo_id: dict[int, DiSan], tat_ca: list[DiSan],
                        nhan: NhanHienThi, rng: random.Random) -> list[list[tuple[int, CauHoi]]]:
    """Tạo mọi câu hỏi của một cấp trong ngân hàng (một lần, dùng cho mọi lớp cùng cấp). Trả mỗi bài một danh sách (mã câu, câu)."""
    da_gap: dict[int, int] = {}
    ra = []
    for bai in ke_hoach:
        cau_cua_bai: list[tuple[int, CauHoi]] = []
        for ma in bai["di_san"]:
            lan = da_gap.get(ma, 0)
            da_gap[ma] = lan + 1
            for cau in tao_cau_hoi_cho_di_san(cap, theo_id[ma], tat_ca, nhan, lan, bai["do_kho"], rng):
                tao = api.can("POST", "/teacher/questions", cau.payload, gv, 201)
                cau_cua_bai.append((tao["id"], cau))
        ra.append(cau_cua_bai)
    return ra


def tao_lop_noi_dung(api: Backend, gv: str, cap: int, ten_lop: str, ke_hoach: list[dict], cau_hoi: list[list[tuple[int, CauHoi]]],
                     theo_id: dict[int, DiSan]) -> tuple[int, list[dg.BaiHoc]]:
    """Một lớp có 10 bài học đã xuất bản, mỗi bài một bài kiểm tra đã phát hành. Trả mã lớp và danh sách bài (theo thứ tự tạo)."""
    lop = api.can("POST", "/teacher/classes", {"name": ten_lop, "grade": KHOI_THEO_CAP[cap], "schoolYear": "2026-2027"}, gv, 201)
    ra: list[dg.BaiHoc] = []
    for i, (bai, cau) in enumerate(zip(ke_hoach, cau_hoi, strict=True)):
        ten_ngan = ", ".join(theo_id[m].ten.split(" – ")[0] for m in bai["di_san"][:2])
        bh = api.can("POST", "/teacher/lessons", {"classId": lop["id"], "title": f"Bài {i + 1}: {ten_ngan}", "heritageIds": bai["di_san"]}, gv, 201)
        nhap = api.can("POST", f"/teacher/lessons/{bh['id']}/ai/compose", {"length": "SHORT"}, gv)
        api.can("PUT", f"/teacher/lessons/{bh['id']}", {"summary": nhap["summary"], "keyPoints": nhap["keyPoints"], "sections": [
            {k: s.get(k) for k in ("type", "title", "body", "imageUrl", "milestoneYear", "eventId", "sourceCitation")} for s in nhap["sections"]]}, gv)
        api.can("POST", f"/teacher/lessons/{bh['id']}/publish", None, gv)
        quiz = api.can("POST", "/teacher/quizzes", {
            "lessonId": bh["id"], "name": f"Kiểm tra bài {i + 1}", "difficultyLevel": bai["do_kho"], "timeLimitMinutes": THOI_GIAN_LAM_THEO_CAP[cap],
            "openAt": gio(-1), "closeAt": gio(bai["han_dong"] * 1440), "showAnswersAfterSubmit": True}, gv, 201)
        api.can("POST", f"/teacher/quizzes/{quiz['id']}/questions", {"questionIds": [qid for qid, _ in cau], "point": 1}, gv)
        api.can("POST", f"/teacher/quizzes/{quiz['id']}/publish", None, gv)
        dem: dict[int, int] = {}
        for _, c in cau:
            dem[c.di_san_id] = dem.get(c.di_san_id, 0) + 1
        ra.append(dg.BaiHoc(bh["id"], quiz["id"], tuple(dem.items()), bai["do_kho"], bai["han_dong"]))
    return lop["id"], ra


# --------------------------------------------------------------------------------------------------------------------
# Học sinh
# --------------------------------------------------------------------------------------------------------------------

def them_hoc_sinh(api: Backend, gv: str, lop_id: int, ten: list[str]) -> list[dict]:
    d = api.can("POST", f"/teacher/classes/{lop_id}/students/import", {"rows": [{"rowNumber": i + 2, "fullName": t} for i, t in enumerate(ten)]}, gv, 201)
    return d["created"]["sheet"]["entries"]


def doc_goi_y(du_lieu: dict) -> dg.GoiY:
    return dg.GoiY(
        quiz_ids=tuple(q["quizId"] for q in du_lieu["nextQuizzes"]),
        bai_on_lai_ids=tuple(b["lessonId"] for b in du_lieu["lessonsToReview"]),
        bai_moi_ids=tuple(b["lessonId"] for b in du_lieu["newLessons"]),
        di_san_nen_on_ids=tuple(h["heritageId"] for h in du_lieu["heritagesToReview"]),
    )


def xu_ly_hoc_sinh(api: Backend, o: dict) -> dict:
    """Một em: đăng nhập, đổi mật khẩu, làm các bài đã định (nếu có), đọc gợi ý và mức thành thạo. `o` là mô tả em (xem dung_viec)."""
    dang_nhap = api.can("POST", "/student/auth/login", {"studentCode": o["ma"], "password": o["mat_khau_tam"]})
    token = api.can("PUT", "/student/me/password", {"newPassword": MAT_KHAU_HOC_SINH, "confirmNewPassword": MAT_KHAU_HOC_SINH}, dang_nhap["accessToken"])["accessToken"]
    hs: dg.HocSinhAo = o["hs"]
    dung_tong = tong = 0
    for thu_tu, ma_bai in enumerate(hs.bai_da_lam):
        bai = o["bai_theo_id"][ma_bai]
        cau = o["cau_hoi"][ma_bai]
        ket_qua = dg.tra_loi_ca_bai(hs, thu_tu, [(c.di_san_id, c.kieu) for _, c in cau], o["ty_le_nham"], XAC_SUAT_DOAN_DI_SAN_YEU)
        luot = api.can("POST", f"/student/quizzes/{bai.quiz_id}/attempts", None, token, 201)
        dang_hien = {q["questionId"]: q for q in luot["questions"]}
        for (qid, c), dung in zip(cau, ket_qua, strict=True):
            api.can("PUT", f"/student/attempts/{luot['id']}/answers/{qid}", dap_an_gui_len(c, dang_hien[qid], dung), token)
        api.can("POST", f"/student/attempts/{luot['id']}/submit", None, token)
        dung_tong += sum(ket_qua)
        tong += len(ket_qua)
    goi_y = api.can("GET", "/student/recommendations", None, token)
    tien_do = api.can("GET", "/student/progress", None, token)
    can_on = {m["heritageId"] for m in tien_do.get("mastery", []) if m.get("level") == "NEEDS_REVIEW"} if tien_do else set()
    return {"goi_y": doc_goi_y(goi_y), "muc_kho_muc_tieu": goi_y["targetDifficulty"], "can_on_backend": sorted(can_on),
            "dung": dung_tong, "tong": tong, "ma_cap": goi_y["level"], "thong_diep": goi_y.get("message"), "du_phong": goi_y.get("relatedFromFallback")}


# --------------------------------------------------------------------------------------------------------------------
# Đo
# --------------------------------------------------------------------------------------------------------------------

def tong_hop_o(ban_ghi: list[dict]) -> dict:
    """Gộp số đo của một tập em (cùng cấp, cùng mức nhiễu hoặc cùng nhóm)."""
    ra: dict = {"so_em": len(ban_ghi)}
    co_yeu = [b for b in ban_ghi if b["hit"] is not None]
    ra["so_em_co_di_san_yeu"] = len(co_yeu)
    cac_cach = ("dich_vu", "quiz_chua_lam_theo_han", "bai_moi_nhat", "bai_ngau_nhien")
    for cach in cac_cach:
        for muc in ("quiz", "bai_hoc", "chung"):
            ra[f"hit_{cach}_{muc}"] = dg.trung_binh(float(b["hit"][cach][muc]) for b in co_yeu)
    for khoa in ("dich_vu", "di_san_ngau_nhien", "nhieu_cau_nhat"):
        ra[f"nen_on_{khoa}"] = dg.trung_binh(float(b["hit"]["nen_on"][khoa]) for b in co_yeu)
    ra["hit_dich_vu_chi_bai_moi"] = dg.trung_binh(float(b["hit"]["bien_the"]["dich_vu_chi_bai_moi"]) for b in co_yeu)
    for khoa in ("quiz_dich_vu", "bai_hoc_dich_vu", "bai_moi_dich_vu", "quiz_moi_nhat", "bai_hoc_moi_nhat", "quiz_ngau_nhien", "bai_hoc_ngau_nhien"):
        ty_le, tong = dg.gop_ty_le(b["khop"][khoa] for b in ban_ghi)
        ra[f"khop_{khoa}"], ra[f"tong_{khoa}"] = ty_le, tong
    ra["khop_chung_dich_vu"] = dg.gop_ty_le([*(b["khop"]["quiz_dich_vu"] for b in ban_ghi), *(b["khop"]["bai_hoc_dich_vu"] for b in ban_ghi)])[0]
    ra["khop_chung_moi_nhat"] = dg.gop_ty_le([*(b["khop"]["quiz_moi_nhat"] for b in ban_ghi), *(b["khop"]["bai_hoc_moi_nhat"] for b in ban_ghi)])[0]
    ra["khop_chung_ngau_nhien"] = dg.gop_ty_le([*(b["khop"]["quiz_ngau_nhien"] for b in ban_ghi), *(b["khop"]["bai_hoc_ngau_nhien"] for b in ban_ghi)])[0]
    dung, tong = (sum(b["thuoc_lop"][0] for b in ban_ghi), sum(b["thuoc_lop"][1] for b in ban_ghi))
    ra["thuoc_lop_dung"], ra["thuoc_lop_tong"] = dung, tong
    ra["co_quiz_nen_lam"] = dg.trung_binh(float(b["so_quiz"] > 0) for b in ban_ghi)
    ra["co_bai_moi"] = dg.trung_binh(float(b["so_bai_moi"] > 0) for b in ban_ghi)
    return ra


def do_ban_ghi(o: dict, ket_qua: dict) -> dict:
    hs: dg.HocSinhAo = o["hs"]
    cap, lop = o["cap"], o["lop"]
    goi_y: dg.GoiY = ket_qua["goi_y"]
    hit = dg.danh_gia_hit_hoc_sinh(hs, lop, goi_y) if hs.di_san_yeu else None
    cau_theo_bai = {ma: [(c.di_san_id, c.kieu) for _, c in cau] for ma, cau in o["cau_hoi"].items()}
    ky_vong = dg.ky_vong_ti_le_dung(hs, cau_theo_bai, o["ty_le_nham"], XAC_SUAT_DOAN_DI_SAN_YEU)
    vung = dg.vung_nang_luc(ky_vong)
    return {
        "chi_so": hs.chi_so, "nhom": hs.nhom, "cap": cap, "di_san_yeu": sorted(hs.di_san_yeu), "bai_da_lam": list(hs.bai_da_lam),
        "ky_vong_dung": ky_vong, "vung_nang_luc": vung,
        "hit": hit, "khop": dg.do_kho_khop_hoc_sinh(hs, cap, lop, goi_y, vung), "thuoc_lop": dg.thuoc_lop(goi_y, lop),
        "so_quiz": len(goi_y.quiz_ids), "so_bai_moi": len(goi_y.bai_moi_ids),
        "goi_y": {"quiz": list(goi_y.quiz_ids), "bai_on_lai": list(goi_y.bai_on_lai_ids), "bai_moi": list(goi_y.bai_moi_ids), "di_san_nen_on": list(goi_y.di_san_nen_on_ids)},
        "muc_kho_muc_tieu": ket_qua["muc_kho_muc_tieu"], "can_on_backend": ket_qua["can_on_backend"],
        "ty_le_dung_thuc_te": (ket_qua["dung"] / ket_qua["tong"]) if ket_qua["tong"] else None,
    }


def phan(x: float) -> str:
    return f"{x:.1%}".replace(".", ",")


def bang_hit(ten_o: dict[str, dict]) -> list[str]:
    d = ["| Mức nhiễu | Số em có di sản yếu | Dịch vụ gợi ý | Quiz chưa làm theo hạn đóng | Bài mới nhất của lớp | Bài ngẫu nhiên của lớp | Kết luận |", "|---|---|---|---|---|---|---|"]
    for ten, o in ten_o.items():
        dv = o["hit_dich_vu_chung"]
        co_so = {"hạn đóng": o["hit_quiz_chua_lam_theo_han_chung"], "mới nhất": o["hit_bai_moi_nhat_chung"], "ngẫu nhiên": o["hit_bai_ngau_nhien_chung"]}
        khoang = dg.khoang_tin_cay_wilson(dv, o["so_em_co_di_san_yeu"])
        vuot = all(dv > v for v in co_so.values())
        d.append(f"| {ten} | {o['so_em_co_di_san_yeu']} | **{phan(dv)}** (95%: {phan(khoang[0])} đến {phan(khoang[1])}) | {phan(co_so['hạn đóng'])} | {phan(co_so['mới nhất'])} | {phan(co_so['ngẫu nhiên'])} | "
                 f"{'Vượt cả 3' if vuot else 'Không vượt cả 3'} |")
    return d


def bang_hit_tach(ten_o: dict[str, dict]) -> list[str]:
    d = ["| Mức nhiễu | Phần | Dịch vụ | Theo hạn đóng | Mới nhất | Ngẫu nhiên |", "|---|---|---|---|---|---|"]
    for ten, o in ten_o.items():
        for phan_ten, khoa in (("3 quiz", "quiz"), ("3 bài học", "bai_hoc")):
            d.append(f"| {ten} | {phan_ten} | {phan(o['hit_dich_vu_' + khoa])} | {phan(o['hit_quiz_chua_lam_theo_han_' + khoa])} | {phan(o['hit_bai_moi_nhat_' + khoa])} | {phan(o['hit_bai_ngau_nhien_' + khoa])} |")
    return d


def bang_nen_on(ten_o: dict[str, dict]) -> list[str]:
    d = ["| Mức nhiễu | Số em | Di sản nên ôn của dịch vụ | 3 di sản ngẫu nhiên của quiz | 3 di sản nhiều câu nhất | Kết luận |", "|---|---|---|---|---|---|"]
    for ten, o in ten_o.items():
        dv, ngau, nhieu = o["nen_on_dich_vu"], o["nen_on_di_san_ngau_nhien"], o["nen_on_nhieu_cau_nhat"]
        d.append(f"| {ten} | {o['so_em_co_di_san_yeu']} | **{phan(dv)}** | {phan(ngau)} | {phan(nhieu)} | {'Vượt cả 2' if dv > ngau and dv > nhieu else 'Không vượt cả 2'} |")
    return d


def viet_bao_cao(ctx: dict, theo_nhieu: dict[str, dict], theo_nhieu_cap: dict[str, dict], theo_nhom: dict[str, dict], theo_vung: dict[str, dict], theo_cap_chua: dict[str, dict],
                 cho_chua: dict, phat_hien: dict, thoi_gian: float) -> str:
    d = ["# Đánh giá gợi ý cá nhân hóa trên học sinh ảo\n"]
    d.append(f"Ngày đo: {datetime.datetime.now():%d/%m/%Y %H:%M}; thời gian chạy {thoi_gian / 60:.1f} phút. Backend: bản đang chạy ở {ctx['backend']}, "
             "`Ai:Mode=Simulated`, email chỉ ghi log, cơ sở dữ liệu tạm đã xóa sau khi đo. Không gọi mô hình ngôn ngữ.\n")
    d.append("## 1. Tham số mô phỏng (chốt trước khi đo)\n")
    d.append(ctx["tham_so"] + "\n")
    d.append("Cùng một em ở ba mức nhiễu có cùng bài, cùng di sản yếu và cùng dãy số ngẫu nhiên (chỉ ngưỡng nhầm ở di sản vững khác), nên chênh lệch giữa các mức nhiễu là do nhiễu. "
             "Di sản yếu thật của em là đáp án để đo; backend không biết điều này mà chỉ thấy các câu em làm.\n")
    d.append("## 2. Cỡ mẫu\n")
    d.append("| Mức nhiễu | Em có lượt | Em có ít nhất một di sản yếu | Nhóm yếu / trung bình / vững |")
    d.append("|---|---|---|---|")
    for ten, o in theo_nhieu.items():
        n = ctx["nhom_theo_nhieu"][ten]
        d.append(f"| {ten} | {o['so_em']} | {o['so_em_co_di_san_yeu']} | {n.get('yeu', 0)} / {n.get('trung_binh', 0)} / {n.get('vung', 0)} |")
    d.append(f"\nEm chưa có lượt nào: {cho_chua['so_em']} em ({', '.join(f'{CAP_TEN[c]} {theo_cap_chua[str(c)]['so_em']}' for c in (1, 2, 3))}).\n")

    d.append("## 3. Trúng di sản yếu: hit@3 của gợi ý quiz và bài học\n")
    d.append("Trúng = em có ít nhất một di sản yếu thật nằm trong di sản của 3 quiz **hoặc** 3 bài học được gợi ý. Dịch vụ: `nextQuizzes` (tối đa 3) và 3 bài học đầu của "
             "`lessonsToReview` rồi `newLessons`. Đường cơ sở \"quiz chưa làm theo hạn đóng\": 3 quiz em chưa làm có hạn đóng gần nhất và bài chứa chúng. "
             "\"Bài mới nhất\": 3 quiz chưa làm mới tạo nhất và 3 bài học mới tạo nhất của lớp. \"Bài ngẫu nhiên\": rút ngẫu nhiên 3 quiz chưa làm và 3 bài của lớp, "
             "lấy giá trị kỳ vọng chính xác (không rút mẫu). Chỉ tiêu: dịch vụ cao hơn cả ba đường cơ sở ở cả ba mức nhiễu.\n")
    d.extend(bang_hit(theo_nhieu))
    d.append("\nTách theo phần:\n")
    d.extend(bang_hit_tach(theo_nhieu))
    d.append("\nBiến thể cách đếm: chỉ tính phần \"bài học mới nên học\" làm 3 bài học: " + "; ".join(f"{t} {phan(o['hit_dich_vu_chi_bai_moi'])}" for t, o in theo_nhieu.items()) + ".\n")
    d.append("### Phần di sản nên ôn\n")
    d.append("Trúng = ít nhất một di sản yếu thật nằm trong 3 di sản nên ôn. Hai đường cơ sở: 3 di sản ngẫu nhiên trong các quiz em đã làm (giá trị kỳ vọng), "
             "3 di sản có nhiều câu nhất trong các quiz em đã làm (hòa thì mã nhỏ trước). Chỉ tiêu: vượt cả hai, không đặt ngưỡng tuyệt đối.\n")
    d.extend(bang_nen_on(theo_nhieu))
    d.append("\n### Theo kiểu em (gộp ba mức nhiễu)\n")
    d.append("Em \"trung bình\" có đúng một di sản yếu: phép thử sắc nhất vì các đường cơ sở ít khi trúng ngẫu nhiên. Em \"yếu\" có hầu hết di sản là yếu nên mọi cách đều dễ trúng.\n")
    d.append("| Kiểu em | Số em có di sản yếu | Dịch vụ | Theo hạn đóng | Mới nhất | Ngẫu nhiên | Nên ôn: dịch vụ / ngẫu nhiên / nhiều câu |")
    d.append("|---|---|---|---|---|---|---|")
    for ten, o in theo_nhom.items():
        if o["so_em_co_di_san_yeu"]:
            d.append(f"| {ten} | {o['so_em_co_di_san_yeu']} | {phan(o['hit_dich_vu_chung'])} | {phan(o['hit_quiz_chua_lam_theo_han_chung'])} | {phan(o['hit_bai_moi_nhat_chung'])} | "
                     f"{phan(o['hit_bai_ngau_nhien_chung'])} | {phan(o['nen_on_dich_vu'])} / {phan(o['nen_on_di_san_ngau_nhien'])} / {phan(o['nen_on_nhieu_cau_nhat'])} |")
    d.append("\n### Backend có nhận ra di sản yếu không?\n")
    d.append("Backend coi di sản là yếu khi em đúng dưới 50% trên ít nhất 3 câu. Tỉ lệ di sản yếu thật mà backend gắn \"Cần ôn\", và tỉ lệ di sản vững bị gắn nhầm \"Cần ôn\":\n")
    d.append("| Mức nhiễu | Yếu thật được nhận ra | Vững bị gắn nhầm |")
    d.append("|---|---|---|")
    for ten, p in phat_hien.items():
        d.append(f"| {ten} | {phan(p['nhan_ra'])} ({p['yeu_thuc_te']} di sản) | {phan(p['nham'])} ({p['vung_thuc_te']} di sản) |")
    d.append("")
    d.append("### Theo từng cấp\n")
    d.append("| Mức nhiễu - cấp | Em có di sản yếu | Dịch vụ | Theo hạn đóng | Mới nhất | Ngẫu nhiên | Nên ôn: dịch vụ / ngẫu nhiên / nhiều câu |")
    d.append("|---|---|---|---|---|---|---|")
    for ten, o in theo_nhieu_cap.items():
        d.append(f"| {ten} | {o['so_em_co_di_san_yeu']} | {phan(o['hit_dich_vu_chung'])} | {phan(o['hit_quiz_chua_lam_theo_han_chung'])} | {phan(o['hit_bai_moi_nhat_chung'])} | "
                 f"{phan(o['hit_bai_ngau_nhien_chung'])} | {phan(o['nen_on_dich_vu'])} / {phan(o['nen_on_di_san_ngau_nhien'])} / {phan(o['nen_on_nhieu_cau_nhat'])} |")
    d.append("")

    d.append("## 4. Độ khó khớp mức của em\n")
    d.append("Vùng năng lực thật của em tính từ tham số mô phỏng: tỉ lệ đúng kỳ vọng dưới 50% là **yếu** (nhận Dễ hoặc Trung bình), từ 80% là **vững** (nhận Khó), ở giữa là trung bình "
             "(chỉ tham khảo, đề bài không quy định, nhận Trung bình). Tỉ lệ = số quiz và bài học được gợi ý có độ khó khớp / tổng số được gợi ý. Độ khó của bài học là độ khó của bài "
             "kiểm tra duy nhất của bài. Đường cơ sở \"bài mới nhất\" như mục 3; chọn ngẫu nhiên là kỳ vọng. Gộp ba mức nhiễu (vùng năng lực của cùng một em đổi theo mức nhiễu).\n")
    d.append("| Vùng năng lực | Số em | Dịch vụ: quiz | Dịch vụ: bài học | Dịch vụ: chung | Mới nhất: chung | Ngẫu nhiên: chung | Dịch vụ cao hơn mới nhất |")
    d.append("|---|---|---|---|---|---|---|---|")
    for ten, o in theo_vung.items():
        d.append(f"| {ten} | {o['so_em']} | {phan(o['khop_quiz_dich_vu'])} | {phan(o['khop_bai_hoc_dich_vu'])} | **{phan(o['khop_chung_dich_vu'])}** | "
                 f"{phan(o['khop_chung_moi_nhat'])} | {phan(o['khop_chung_ngau_nhien'])} | {'Có' if o['khop_chung_dich_vu'] > o['khop_chung_moi_nhat'] else 'Không'} |")
    d.append("")
    d.append("Theo từng mức nhiễu (em yếu và em vững gộp, đúng đề bài):\n")
    d.append("| Mức nhiễu | Số em | Dịch vụ: chung | Mới nhất: chung | Ngẫu nhiên: chung | Dịch vụ cao hơn mới nhất |")
    d.append("|---|---|---|---|---|---|")
    for ten, o in ctx["theo_nhieu_yeu_vung"].items():
        d.append(f"| {ten} | {o['so_em']} | **{phan(o['khop_chung_dich_vu'])}** | {phan(o['khop_chung_moi_nhat'])} | {phan(o['khop_chung_ngau_nhien'])} | {'Có' if o['khop_chung_dich_vu'] > o['khop_chung_moi_nhat'] else 'Không'} |")
    d.append("")

    d.append("## 5. Tác động của khối lớp: em chưa có lượt nào\n")
    d.append("Mức khớp mặc định của cấp: cấp 1 Dễ, cấp 2 và cấp 3 Trung bình. Quiz = `nextQuizzes`, bài mới = `newLessons`. Đường cơ sở \"bài mới nhất\" = 3 quiz và 3 bài học mới tạo nhất của lớp.\n")
    d.append("| Cấp | Số em | Khớp: quiz dịch vụ | Khớp: bài mới dịch vụ | Khớp: chung dịch vụ | Khớp: chung mới nhất | Khớp: chung ngẫu nhiên | Vượt mới nhất | Có quiz nên làm | Có bài mới nên học |")
    d.append("|---|---|---|---|---|---|---|---|---|---|")
    for c in (1, 2, 3):
        o = theo_cap_chua[str(c)]
        chung_dv = dg.gop_ty_le([(o["khop_quiz_dich_vu"] * o["tong_quiz_dich_vu"], o["tong_quiz_dich_vu"]), (o["khop_bai_moi_dich_vu"] * o["tong_bai_moi_dich_vu"], o["tong_bai_moi_dich_vu"])])[0]
        d.append(f"| {CAP_TEN[c]} | {o['so_em']} | {phan(o['khop_quiz_dich_vu'])} | {phan(o['khop_bai_moi_dich_vu'])} | **{phan(chung_dv)}** | {phan(o['khop_chung_moi_nhat'])} | "
                 f"{phan(o['khop_chung_ngau_nhien'])} | {'Có' if chung_dv > o['khop_chung_moi_nhat'] else 'Không'} | {phan(o['co_quiz_nen_lam'])} | {phan(o['co_bai_moi'])} |")
    d.append("")

    d.append("Mỗi cấp có nhiều lớp chưa có lượt, mỗi lớp một cách xếp nội dung (thứ tự tạo, độ khó, hạn đóng) khác nhau; so dịch vụ với \"bài mới nhất\" từng lớp:\n")
    d.append("| Lớp | Khớp chung: dịch vụ | Khớp chung: mới nhất | So sánh |")
    d.append("|---|---|---|---|")
    for ten, o in ctx["chua_theo_lop"].items():
        d.append(f"| {ten} | {phan(o['dich_vu'])} | {phan(o['moi_nhat'])} | {'Dịch vụ cao hơn' if o['dich_vu'] > o['moi_nhat'] + 1e-9 else ('Bằng nhau' if abs(o['dich_vu'] - o['moi_nhat']) <= 1e-9 else 'Dịch vụ thấp hơn')} |")
    d.append("")
    d.append("## 6. Gợi ý đúng lớp\n")
    tong = sum(o["thuoc_lop_tong"] for o in theo_nhieu.values()) + cho_chua["thuoc_lop_tong"]
    dung = sum(o["thuoc_lop_dung"] for o in theo_nhieu.values()) + cho_chua["thuoc_lop_dung"]
    d.append(f"Trong {tong} quiz và bài học được gợi ý cho {sum(o['so_em'] for o in theo_nhieu.values()) + cho_chua['so_em']} em, **{dung}** thuộc lớp của em ({phan(dung / tong) if tong else 'không có mục nào'}). "
             "Chỉ tiêu 100%. Các lớp cùng cấp có nội dung giống hệt nhau nhưng mã khác nhau nên gợi ý lẫn lớp sẽ bị phát hiện.\n")

    d.append("## 7. Điều không đo được hoặc cần lưu ý\n")
    d.append("- API \"Gợi ý cho em\" chỉ trả mã và tiêu đề của quiz và bài học, không trả di sản của chúng; di sản của từng quiz, bài học được lấy từ chính kế hoạch dựng lớp của script này (đã biết chắc). "
             "Nếu muốn đo trên dữ liệu thật không do script dựng thì cần thêm trường danh sách di sản vào `RecommendedQuizDto` và `RecommendedLessonDto`.")
    d.append("- Các lớp được dựng với 10 bài học mỗi lớp và mỗi di sản xuất hiện trong hai bài; kết quả phụ thuộc cách dựng này (số bài ứng viên, số di sản mỗi bài). Đường cơ sở ngẫu nhiên yếu hơn khi lớp có nhiều bài hơn.")
    d.append("- Xếp quiz của backend ưu tiên hạn đóng sớm trước độ khó; vì vậy khi mỗi bài một hạn đóng khác nhau, độ khó chỉ còn tác dụng khi hai quiz đóng cùng lúc. Xem lại hai mục độ khó khớp mức và tác động của khối lớp với `--kieu-han-dong cung-ngay`.")
    d.append("- Cấp 3 không có dạng câu Đúng/Sai đơn; câu đúng/sai ở cấp 3 là dạng nhiều mệnh đề (ba mệnh đề), tính là đúng khi đúng cả ba, và xác suất đúng của di sản yếu được áp ở mức cả câu (50%).")
    d.append("- Chọn hình ở cấp 1 chỉ có 3 hình với những di sản có 3 hình trong thư viện ảnh (xác suất đoán 1/3); di sản chỉ có 2 hình dùng câu đúng/sai có hình thay cho chọn hình.\n")
    return "\n".join(d)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None, help="thư mục ghi báo cáo và JSON (mặc định %%TEMP%%\\dsvhvn-danhgia-<giờ>)")
    ap.add_argument("--hoc-sinh-moi-lop", type=int, default=SO_HOC_SINH_MOI_LOP, help="số em có lượt mỗi lớp (tối đa 60)")
    ap.add_argument("--hoc-sinh-chua-lam", type=int, default=SO_HOC_SINH_CHUA_LAM_MOI_LOP, help="số em chưa có lượt mỗi lớp (tối đa 60)")
    ap.add_argument("--lop-chua-lam", type=int, default=SO_LOP_CHUA_LAM_MOI_CAP, help="số lớp chưa có lượt mỗi cấp")
    ap.add_argument("--kieu-han-dong", choices=("khac-nhau", "cung-ngay"), default=KIEU_HAN_DONG_MAC_DINH)
    ap.add_argument("--luong", type=int, default=SO_LUONG_SONG_SONG, help="số luồng gọi API song song cho phần học sinh")
    ap.add_argument("--thu-nho", action="store_true", help="cỡ nhỏ để thử đường đi: 6 em mỗi lớp, 3 em chưa có lượt mỗi cấp")
    ap.add_argument("--hat", type=int, default=HAT_GIONG)
    args = ap.parse_args()
    so_hs, so_chua, so_lop_chua = (6, 3, 2) if args.thu_nho else (args.hoc_sinh_moi_lop, args.hoc_sinh_chua_lam, args.lop_chua_lam)
    if not (1 <= so_hs <= 60 and 1 <= so_chua <= 60):
        sys.exit("Mỗi lớp tối đa 60 em đang hoạt động.")

    api = Backend()
    thu_muc = Path(args.out or Path(os.environ.get("TEMP", ".")) / f"dsvhvn-danhgia-{datetime.datetime.now():%Y%m%d%H%M%S}")
    thu_muc.mkdir(parents=True, exist_ok=True)
    tham_so = in_tham_so(args.hat, so_hs, so_chua, so_lop_chua, args.kieu_han_dong)
    print("THAM SỐ MÔ PHỎNG (chốt trước khi đo)\n" + tham_so + "\n", flush=True)

    bat_dau = time.time()
    hau_to = datetime.datetime.now().strftime("%H%M%S")
    quan_tri = api.dang_nhap_quan_tri()
    so_di_san = api.xuat_ban_di_san(quan_tri)
    print(f"Di sản đã xuất bản: {so_di_san}", flush=True)
    tat_ca, nhan = doc_di_san(api)
    if len(tat_ca) < SO_DI_SAN_MOI_BAI * 2:
        sys.exit("Không đủ di sản đã xuất bản.")
    theo_id = {d.id: d for d in tat_ca}
    nang_han_muc_ai(api, quan_tri, 3 * (3 + so_lop_chua) * SO_BAI_HOC_MOI_LOP + 100)
    gv = dung_truong(api, quan_tri, hau_to)
    print("Đã tạo trường và 3 giáo viên (mỗi cấp một người)", flush=True)

    # ---- Nội dung: câu hỏi mỗi cấp một lần, rồi mỗi cấp 4 lớp (3 mức nhiễu + 1 lớp chưa có lượt) có nội dung giống nhau ----
    lop_cua: dict[tuple[int, str], dict] = {}
    nhieu_ten = [t for t, _ in MUC_NHIEU]
    for cap in (1, 2, 3):
        rng = random.Random(f"{args.hat}/noi-dung/{cap}")
        ke_hoach = ke_hoach_cap(cap, [d.id for d in tat_ca], SO_BAI_HOC_MOI_LOP, rng, args.kieu_han_dong)
        cau_hoi = tao_cau_hoi_cua_cap(api, gv[cap], cap, ke_hoach, theo_id, tat_ca, nhan, rng)
        print(f"Cấp {cap}: đã tạo {sum(len(x) for x in cau_hoi)} câu hỏi", flush=True)
        # Ba lớp nhiễu có nội dung y hệt nhau (cùng em ở ba mức nhiễu so được). Các lớp chưa có lượt mỗi lớp một cách xếp khác (thứ tự tạo, độ khó, hạn đóng),
        # vì gợi ý cho em chưa có lượt chỉ phụ thuộc nội dung lớp: mỗi lớp là một lần rút nội dung.
        ky_hieu = [(ten, ke_hoach, cau_hoi) for ten in nhieu_ten]
        for k in range(so_lop_chua):
            kh_k, ch_k = bien_the_ke_hoach(ke_hoach, cau_hoi, random.Random(f"{args.hat}/chua-lam/{cap}/{k}"), args.kieu_han_dong)
            ky_hieu.append((f"chua_lam#{k + 1}", kh_k, ch_k))
        for ten, kh, ch in ky_hieu:
            ten_lop = f"{KHOI_THEO_CAP[cap]}A-{'chưa làm ' + ten.split('#')[1] if ten.startswith('chua_lam') else 'nhiễu ' + ten}"
            lop_id, bai = tao_lop_noi_dung(api, gv[cap], cap, ten_lop, kh, ch, theo_id)
            lop_cua[(cap, ten)] = {"lop_id": lop_id, "bai": bai, "cau_hoi": {b.id: cau for b, cau in zip(bai, ch, strict=True)}}
            print(f"  Lớp {ten_lop}: {len(bai)} bài học và bài kiểm tra đã xuất bản", flush=True)

    # ---- Học sinh: tạo tài khoản theo lớp, rồi làm việc song song ----
    viec: list[dict] = []
    for (cap, ten), lop in lop_cua.items():
        chua = ten.startswith("chua_lam")
        n = so_chua if chua else so_hs
        thu_tu = [f"Học Sinh Ảo {KHOI_THEO_CAP[cap]}-{ten.replace('chua_lam#', 'chua') if chua else ten}-{i:03d}" for i in range(n)]
        the = them_hoc_sinh(api, gv[cap], lop["lop_id"], thu_tu)
        rng_nhom = random.Random(f"{args.hat}/nhom/{cap}")
        nhom = ["chua_lam"] * n if chua else dg.chia_nhom(n, TY_LE_NHOM, rng_nhom)
        ty_le_nham = dict(MUC_NHIEU).get(ten, 0.0)
        bai_theo_id = {b.id: b for b in lop["bai"]}
        for i, entry in enumerate(the):
            hs = dg.tao_hoc_sinh(i, nhom[i], lop["bai"], f"{args.hat}/hs/{cap}/{i}", TY_LE_DI_SAN_YEU_O_NHOM_YEU, SO_BAI_MOI_EM)
            viec.append({"cap": cap, "nhieu": ten, "hs": hs, "ma": entry["studentCode"], "mat_khau_tam": entry["temporaryPassword"], "ty_le_nham": ty_le_nham,
                         "bai_theo_id": bai_theo_id, "cau_hoi": lop["cau_hoi"], "lop": lop["bai"]})
    print(f"Đã tạo {len(viec)} tài khoản học sinh; bắt đầu làm bài và đọc gợi ý ({args.luong} luồng)", flush=True)

    ban_ghi: list[dict] = []
    loi: list[str] = []

    def chay(o: dict) -> dict | None:
        try:
            return {"o": o, "kq": xu_ly_hoc_sinh(api, o)}
        except (LoiApi, KeyError, ValueError, OSError) as e:
            loi.append(f"{o['cap']}/{o['nhieu']}/{o['hs'].chi_so}: {type(e).__name__}: {str(e)[:200]}")
            return None

    xong = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.luong) as pool:
        for ket in pool.map(chay, viec):
            xong += 1
            if ket:
                o = ket["o"]
                b = do_ban_ghi(o, ket["kq"])
                b["nhieu"] = o["nhieu"]
                ban_ghi.append(b)
            if xong % 50 == 0:
                print(f"  {xong}/{len(viec)} em", flush=True)
    if loi:
        print(f"{len(loi)} em lỗi, ví dụ:\n  " + "\n  ".join(loi[:5]), file=sys.stderr)
    if len(loi) > max(2, len(viec) // 50):
        print("Quá nhiều em lỗi; dừng, không ghi số đo.", file=sys.stderr)
        return 1

    # ---- Gộp số đo ----
    co_lan = [b for b in ban_ghi if not b["nhieu"].startswith("chua_lam")]
    theo_nhieu = {f"Nhiễu {t} ({dict(MUC_NHIEU)[t]:.0%})": tong_hop_o([b for b in co_lan if b["nhieu"] == t]) for t in nhieu_ten}
    theo_nhieu_cap = {f"{t} - {CAP_TEN[c]}": tong_hop_o([b for b in co_lan if b["nhieu"] == t and b["cap"] == c]) for t in nhieu_ten for c in (1, 2, 3)}
    theo_nhieu_cap = {f"Nhiễu {k}": v for k, v in theo_nhieu_cap.items()}
    theo_nhom = {TEN_NHOM[n]: tong_hop_o([b for b in co_lan if b["nhom"] == n]) for n in ("yeu", "trung_binh", "vung")}
    theo_vung = {TEN_NHOM[n]: tong_hop_o([b for b in co_lan if b["vung_nang_luc"] == n]) for n in ("yeu", "trung_binh", "vung")}
    theo_vung["yếu và vững (đúng đề bài)"] = tong_hop_o([b for b in co_lan if b["vung_nang_luc"] in ("yeu", "vung")])
    theo_nhieu_yeu_vung = {f"Nhiễu {t} ({dict(MUC_NHIEU)[t]:.0%})": tong_hop_o([b for b in co_lan if b["nhieu"] == t and b["vung_nang_luc"] in ("yeu", "vung")]) for t in nhieu_ten}
    chua = [b for b in ban_ghi if b["nhieu"].startswith("chua_lam")]
    theo_cap_chua = {str(c): tong_hop_o([b for b in chua if b["cap"] == c]) for c in (1, 2, 3)}
    cho_chua = tong_hop_o(chua)
    phat_hien = {}
    for t in nhieu_ten:
        yeu_tt = nhan_ra = vung_tt = nham = 0
        for b in (x for x in co_lan if x["nhieu"] == t):
            gap = {h for i in b["bai_da_lam"] for h in next(bb for bb in lop_cua[(b["cap"], t)]["bai"] if bb.id == i).di_san}
            backend_yeu = set(b["can_on_backend"])
            yeu = set(b["di_san_yeu"])
            yeu_tt += len(yeu)
            nhan_ra += len(yeu & backend_yeu)
            vung_tt += len(gap - yeu)
            nham += len((gap - yeu) & backend_yeu)
        phat_hien[f"Nhiễu {t} ({dict(MUC_NHIEU)[t]:.0%})"] = {"yeu_thuc_te": yeu_tt, "nhan_ra": nhan_ra / yeu_tt if yeu_tt else 0.0, "vung_thuc_te": vung_tt, "nham": nham / vung_tt if vung_tt else 0.0}
    nhom_theo_nhieu = {}
    for t in nhieu_ten:
        dem: dict[str, int] = {}
        for b in (x for x in co_lan if x["nhieu"] == t):
            dem[b["nhom"]] = dem.get(b["nhom"], 0) + 1
        nhom_theo_nhieu[f"Nhiễu {t} ({dict(MUC_NHIEU)[t]:.0%})"] = dem

    chua_theo_lop = {}
    for (c, ten_lop) in sorted(k for k in lop_cua if k[1].startswith("chua_lam")):
        o = tong_hop_o([b for b in chua if b["cap"] == c and b["nhieu"] == ten_lop])
        chung_dv = dg.gop_ty_le([(o["khop_quiz_dich_vu"] * o["tong_quiz_dich_vu"], o["tong_quiz_dich_vu"]), (o["khop_bai_moi_dich_vu"] * o["tong_bai_moi_dich_vu"], o["tong_bai_moi_dich_vu"])])[0]
        chua_theo_lop[f"{CAP_TEN[c]} - lớp {ten_lop.split('#')[1]}"] = {"dich_vu": chung_dv, "moi_nhat": o["khop_chung_moi_nhat"], "ngau_nhien": o["khop_chung_ngau_nhien"]}
    ctx = {"backend": api.base, "tham_so": tham_so, "nhom_theo_nhieu": nhom_theo_nhieu, "theo_nhieu_yeu_vung": theo_nhieu_yeu_vung, "chua_theo_lop": chua_theo_lop}
    bao_cao = viet_bao_cao(ctx, theo_nhieu, theo_nhieu_cap, theo_nhom, theo_vung, theo_cap_chua, cho_chua, phat_hien, time.time() - bat_dau)
    (thu_muc / "hoc-sinh-ao.md").write_text(bao_cao, encoding="utf-8")
    (thu_muc / "hoc-sinh-ao.json").write_text(json.dumps({
        "tham_so": {"hat": args.hat, "xac_suat_doan_di_san_yeu": XAC_SUAT_DOAN_DI_SAN_YEU, "muc_nhieu": dict(MUC_NHIEU), "ty_le_nhom": TY_LE_NHOM,
                    "ty_le_di_san_yeu_o_nhom_yeu": TY_LE_DI_SAN_YEU_O_NHOM_YEU, "so_bai_moi_em": SO_BAI_MOI_EM, "so_bai_hoc_moi_lop": SO_BAI_HOC_MOI_LOP,
                    "so_di_san_moi_bai": SO_DI_SAN_MOI_BAI, "so_cau_moi_di_san": SO_CAU_MOI_DI_SAN, "so_hoc_sinh_moi_lop": so_hs,
                    "so_lop_chua_lam_moi_cap": so_lop_chua, "so_hoc_sinh_chua_lam_moi_lop": so_chua, "kieu_han_dong": args.kieu_han_dong},
        "theo_muc_nhieu": theo_nhieu, "theo_muc_nhieu_va_cap": theo_nhieu_cap, "theo_kieu_em": theo_nhom, "theo_vung_nang_luc": theo_vung, "theo_muc_nhieu_yeu_va_vung": theo_nhieu_yeu_vung, "em_chua_co_luot_theo_lop": chua_theo_lop, "em_chua_co_luot_theo_cap": theo_cap_chua,
        "backend_nhan_ra_di_san_yeu": phat_hien, "so_em_loi": len(loi),
        "lop": {f"{c}/{t}": [{"bai_hoc": b.id, "quiz": b.quiz_id, "di_san": list(b.di_san), "do_kho": b.do_kho, "han_dong_ngay": b.han_dong} for b in v["bai"]] for (c, t), v in lop_cua.items()},
        "hoc_sinh": ban_ghi,
    }, ensure_ascii=False, indent=1, default=lambda x: sorted(x) if isinstance(x, frozenset) else str(x)), encoding="utf-8")
    print("\n" + bao_cao)
    print(f"\nĐã ghi {thu_muc / 'hoc-sinh-ao.md'} và {thu_muc / 'hoc-sinh-ao.json'}")
    return 1 if loi else 0


if __name__ == "__main__":
    sys.exit(main())
