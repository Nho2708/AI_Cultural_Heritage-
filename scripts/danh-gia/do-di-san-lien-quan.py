"""Đo gợi ý di sản liên quan: precision@3 của hai cách xếp, "chỉ thuộc tính" và "thuộc tính + TF-IDF" (đúng như dịch vụ AI đang chạy).

Cách xếp là hàm `rank_related` của dịch vụ AI (app/recommender/rank.py) gọi trực tiếp trong tiến trình này, không qua mạng và không gọi mô hình ngôn ngữ.
Cách "chỉ thuộc tính" tắt phần giống chữ (TF-IDF) của đúng hàm đó. Dữ liệu 20 di sản lấy từ API công khai của backend (không cần đăng nhập),
cùng cách ghép thuộc tính mà backend dùng khi gọi dịch vụ AI (tên + mô tả ngắn; khoảng năm từ dòng thời gian).

Bộ nhãn do HAI NGƯỜI gán độc lập (3 đến 5 di sản liên quan cho mỗi di sản, chọn trong 20 di sản) rồi thống nhất chỗ lệch: tệp `nhan-di-san-lien-quan.json`.
Chưa có nhãn thì script chỉ in và ghi ba di sản đứng đầu của hai cách để người gán nhãn xem, không bịa số đo.

    BASE=http://localhost:5090 python scripts/danh-gia/do-di-san-lien-quan.py --out <thư mục>
    python scripts/danh-gia/do-di-san-lien-quan.py --tao-mau            # dựng tệp nhãn trống từ 20 di sản của backend (không ghi đè tệp đã có)

Biến môi trường: BASE (mặc định http://localhost:5090). Không cần đăng nhập. Chạy bằng Python của môi trường ảo (cần scikit-learn).
Mã thoát: 0 xong; 2 tệp nhãn sai cấu trúc.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from unittest import mock

QUI_MUC = Path(__file__).resolve().parent
GOC = QUI_MUC.parent.parent
sys.path.insert(0, str(GOC))
sys.path.insert(0, str(QUI_MUC))
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]

import danh_gia_chung as dg
from backend_api import Backend, lay_di_san_cong_khai

from app.recommender import rank
from app.schemas.recommend import HeritageFeatures, RankRequest, WeightedHeritage

NGUONG = 0.5
CACH_XEP = (("chi_thuoc_tinh", "Chỉ thuộc tính"), ("thuoc_tinh_va_tfidf", "Thuộc tính + TF-IDF"))
TEP_NHAN_MAC_DINH = QUI_MUC / "nhan-di-san-lien-quan.json"
HUONG_DAN = [
    "Hai người gán nhãn làm ĐỘC LẬP, không xem nhãn của nhau: với mỗi di sản, điền vào nhanNguoi1 và nhanNguoi2 từ 3 đến 5 mã (id) của các di sản liên quan, chọn trong 20 di sản của danh sách này (không chọn chính nó).",
    "Liên quan là em học về di sản này thì nên được gợi ý đọc tiếp di sản kia (cùng chủ đề, cùng thời kỳ, cùng vùng, cùng loại hình...). Không xem kết quả xếp hạng của dịch vụ trước khi gán.",
    "Sau khi cả hai xong, đối chiếu chỗ lệch và điền danh sách đã thống nhất vào thongNhat (3 đến 5 mã). Nếu mời được một giáo viên thì cho giáo viên gán thêm theo cách tương tự trên một bản sao của tệp này và đối chiếu chung ở bước thống nhất.",
    "Điền tên hai người vào nguoiGan1 và nguoiGan2. Tệp này chỉ đưa vào git khi nhãn do người thật gán.",
]


def dung_dac_trung(chi_tiet: dict) -> HeritageFeatures:
    pha = chi_tiet.get("timeline") or []
    nam_tu = min((p["startYear"] for p in pha if p.get("startYear") is not None), default=None)
    nam_den = max((p.get("endYear") if p.get("endYear") is not None else p["startYear"] for p in pha if p.get("startYear") is not None), default=None)
    vung = (chi_tiet.get("province") or {}).get("region")
    return HeritageFeatures(
        id=chi_tiet["id"], name=chi_tiet["name"], type=chi_tiet.get("heritageType"), province_id=chi_tiet.get("provinceId"),
        region=vung, level=chi_tiet.get("recognitionLevel"), year_from=nam_tu, year_to=nam_den,
        text=f"{chi_tiet['name']} {chi_tiet.get('shortDescription') or ''}",
    )


def xep_hang(dac_trung: list[HeritageFeatures], cach: str) -> dict[int, list[int]]:
    """Với mỗi di sản: mã các di sản còn lại xếp theo điểm giảm dần (hòa điểm thì mã nhỏ trước, đúng như dịch vụ)."""
    ra: dict[int, list[int]] = {}
    for goc in dac_trung:
        yeu_cau = RankRequest(references=[WeightedHeritage(heritage=goc, weight=1.0)], candidates=[d for d in dac_trung if d.id != goc.id])
        if cach == "chi_thuoc_tinh":
            with mock.patch.object(rank, "_text_similarities", lambda *_args, **_kw: None):
                ket_qua = rank.rank_related(yeu_cau)
        else:
            ket_qua = rank.rank_related(yeu_cau)
        ra[goc.id] = [r.heritage_id for r in ket_qua]
    return ra


def tao_mau(di_san: list[dict]) -> dict:
    return {
        "huongDan": HUONG_DAN,
        "nguoiGan1": "", "nguoiGan2": "",
        "diSan": [{"id": d["id"], "slug": d["slug"], "ten": d["name"], "nhanNguoi1": [], "nhanNguoi2": [], "thongNhat": []} for d in di_san],
    }


def doc_nhan(duong_dan: Path, ma_hop_le: set[int]) -> dict | None:
    """Đọc tệp nhãn; None nếu không có tệp. Sai cấu trúc (mã lạ, tự chọn chính nó, lặp) thì dừng với mã 2."""
    if not duong_dan.exists():
        return None
    du_lieu = json.loads(duong_dan.read_text(encoding="utf-8"))
    loi = []
    for muc in du_lieu.get("diSan", []):
        for khoa in ("nhanNguoi1", "nhanNguoi2", "thongNhat"):
            ds = muc.get(khoa) or []
            if len(set(ds)) != len(ds):
                loi.append(f"di sản {muc['id']}: {khoa} có mã lặp")
            for ma in ds:
                if ma not in ma_hop_le:
                    loi.append(f"di sản {muc['id']}: {khoa} có mã {ma} không nằm trong 20 di sản")
                elif ma == muc["id"]:
                    loi.append(f"di sản {muc['id']}: {khoa} chọn chính nó")
            if ds and not 3 <= len(ds) <= 5:
                loi.append(f"di sản {muc['id']}: {khoa} có {len(ds)} mã, cần 3 đến 5")
    if loi:
        print("Tệp nhãn sai cấu trúc:\n  " + "\n  ".join(loi), file=sys.stderr)
        sys.exit(2)
    return du_lieu


def tinh_trang_nhan(nhan: dict | None) -> str:
    if nhan is None:
        return "khong_co_tep"
    muc = nhan["diSan"]
    co1 = sum(1 for m in muc if m.get("nhanNguoi1"))
    co2 = sum(1 for m in muc if m.get("nhanNguoi2"))
    co_tn = sum(1 for m in muc if m.get("thongNhat"))
    if co1 == co2 == co_tn == 0:
        return "trong"
    if co_tn == 0:
        return "chua_thong_nhat"
    return "co_thong_nhat" if co_tn == len(muc) else "thong_nhat_mot_phan"


def do_precision(xep: dict[int, dict[str, list[int]]], nhan: dict) -> dict:
    """precision@3 trung bình theo từng cách xếp, so với danh sách đã thống nhất và với từng người gán."""
    ra: dict = {}
    for ma_cach, _ in CACH_XEP:
        ket_qua = {}
        for khoa, ten in (("thongNhat", "thong_nhat"), ("nhanNguoi1", "nguoi_1"), ("nhanNguoi2", "nguoi_2")):
            gia_tri = [dg.precision_at_k(xep[m["id"]][ma_cach], m[khoa]) for m in nhan["diSan"] if m.get(khoa)]
            ket_qua[ten] = {"precision_at_3": dg.trung_binh(gia_tri), "so_di_san": len(gia_tri)}
        ra[ma_cach] = ket_qua
    return ra


def do_dong_thuan(nhan: dict) -> dict:
    muc = [m for m in nhan["diSan"] if m.get("nhanNguoi1") and m.get("nhanNguoi2")]
    if not muc:
        return {"so_di_san_ca_hai_da_gan": 0}
    ma_tat_ca = [m["id"] for m in nhan["diSan"]]
    a, b = [], []
    for m in muc:
        for ma in ma_tat_ca:
            if ma != m["id"]:
                a.append(ma in m["nhanNguoi1"])
                b.append(ma in m["nhanNguoi2"])
    return {
        "so_di_san_ca_hai_da_gan": len(muc),
        "jaccard_trung_binh": dg.trung_binh(dg.jaccard(m["nhanNguoi1"], m["nhanNguoi2"]) for m in muc),
        "kappa_cohen": dg.cohen_kappa(a, b),
        "so_nhan_trung_binh_nguoi_1": dg.trung_binh(len(m["nhanNguoi1"]) for m in muc),
        "so_nhan_trung_binh_nguoi_2": dg.trung_binh(len(m["nhanNguoi2"]) for m in muc),
    }


def viet_bao_cao(ten: dict[int, str], xep: dict[int, dict[str, list[int]]], trang_thai: str, do: dict | None, dong_thuan: dict | None, nguoi: tuple[str, str]) -> str:
    d = []
    d.append("# Đo gợi ý di sản liên quan (precision@3)\n")
    d.append(f"Ngày đo: {datetime.datetime.now():%d/%m/%Y %H:%M}. Hàm xếp: `rank_related` của dịch vụ AI chạy trực tiếp, không gọi mô hình ngôn ngữ. 20 di sản lấy từ API công khai của backend.\n")
    d.append("Hai cách: **chỉ thuộc tính** (loại hình, tỉnh, vùng, cấp xếp hạng, khoảng năm; phần giống chữ tắt) và **thuộc tính + TF-IDF** (dịch vụ như đang chạy). "
             "Hòa điểm thì xếp mã nhỏ trước, đúng như dịch vụ; vì cách chỉ thuộc tính có rất nhiều điểm hòa nên thứ tự trong ba mục đầu phụ thuộc mã di sản.\n")
    if do is None:
        mo_ta = {
            "khong_co_tep": "Chưa có tệp nhãn.",
            "trong": "Tệp nhãn có nhưng chưa ai gán (mọi danh sách rỗng).",
            "chua_thong_nhat": "Đã có nhãn của người gán nhưng chưa có danh sách thống nhất.",
        }.get(trang_thai, "Nhãn chưa đủ.")
        d.append(f"## Chưa đo được\n\n{mo_ta} **Không có số precision@3** cho tới khi hai người gán xong và thống nhất (xem README, mục Đánh giá mô hình). Dưới đây là ba di sản đứng đầu của hai cách để người gán nhãn đối chiếu sau khi đã gán xong.\n")
    else:
        d.append(f"## Kết quả (chỉ tiêu: precision@3 ≥ {NGUONG})\n")
        d.append(f"Người gán: {nguoi[0] or '(chưa ghi tên)'} và {nguoi[1] or '(chưa ghi tên)'}. Tình trạng nhãn: {trang_thai.replace('_', ' ')}.\n")
        d.append("| Cách xếp | So với danh sách thống nhất | Số di sản | Đạt chỉ tiêu | So với người 1 | So với người 2 |")
        d.append("|---|---|---|---|---|---|")
        for ma, ten_cach in CACH_XEP:
            r = do[ma]
            tn = r["thong_nhat"]
            dat = "Đạt" if tn["so_di_san"] and tn["precision_at_3"] >= NGUONG else ("Chưa đạt" if tn["so_di_san"] else "Chưa có nhãn thống nhất")
            d.append(f"| {ten_cach} | {tn['precision_at_3']:.3f} | {tn['so_di_san']} | {dat} | {r['nguoi_1']['precision_at_3']:.3f} | {r['nguoi_2']['precision_at_3']:.3f} |")
        d.append("")
        if dong_thuan and dong_thuan.get("so_di_san_ca_hai_da_gan"):
            kappa = dong_thuan["kappa_cohen"]
            d.append("### Đồng thuận giữa hai người gán\n")
            d.append(f"- Số di sản cả hai đã gán: {dong_thuan['so_di_san_ca_hai_da_gan']}")
            d.append(f"- Jaccard trung bình của hai danh sách: {dong_thuan['jaccard_trung_binh']:.3f}")
            d.append(f"- Kappa của Cohen trên các cặp (di sản, ứng viên): {'không xác định' if kappa is None else f'{kappa:.3f}'}")
            d.append(f"- Số nhãn trung bình mỗi di sản: người 1 {dong_thuan['so_nhan_trung_binh_nguoi_1']:.1f}, người 2 {dong_thuan['so_nhan_trung_binh_nguoi_2']:.1f}\n")
    d.append("## Ba di sản đứng đầu của hai cách\n")
    d.append("| Di sản | Chỉ thuộc tính | Thuộc tính + TF-IDF |")
    d.append("|---|---|---|")
    for ma in sorted(xep):
        cot = [" ; ".join(f"{ten[x]} ({x})" for x in xep[ma][c][:3]) or "(không có ứng viên)" for c, _ in CACH_XEP]
        d.append(f"| {ten[ma]} ({ma}) | {cot[0]} | {cot[1]} |")
    d.append("")
    return "\n".join(d)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None, help="thư mục ghi báo cáo Markdown và JSON (mặc định %%TEMP%%\\dsvhvn-danhgia-<giờ>)")
    ap.add_argument("--nhan", default=str(TEP_NHAN_MAC_DINH), help="tệp nhãn (mặc định cạnh script)")
    ap.add_argument("--tao-mau", action="store_true", help="dựng tệp nhãn trống từ 20 di sản của backend rồi thoát (không ghi đè tệp đã có)")
    args = ap.parse_args()

    backend = Backend()
    di_san = lay_di_san_cong_khai(backend)
    if not di_san and os.environ.get("ADMIN_PASSWORD"):
        # Backend tạm vừa dựng: di sản nạp sẵn ở trạng thái nháp, xuất bản để API công khai trả được.
        so = backend.xuat_ban_di_san(backend.dang_nhap_quan_tri())
        print(f"Đã xuất bản {so} di sản trên backend tạm.")
        di_san = lay_di_san_cong_khai(backend)
    if len(di_san) < 4:
        sys.exit(f"Backend chỉ có {len(di_san)} di sản đã xuất bản; cần xuất bản đủ 20 di sản trước khi đo.")
    ten = {d["id"]: d["name"] for d in di_san}

    duong_nhan = Path(args.nhan)
    if args.tao_mau:
        if duong_nhan.exists():
            sys.exit(f"{duong_nhan} đã có; xóa tay nếu thật sự muốn dựng lại (tránh mất nhãn đã gán).")
        duong_nhan.write_text(json.dumps(tao_mau(di_san), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Đã ghi tệp nhãn trống: {duong_nhan} ({len(di_san)} di sản)")
        return

    dac_trung = [dung_dac_trung(d) for d in di_san]
    xep = {cach: xep_hang(dac_trung, cach) for cach, _ in CACH_XEP}
    theo_di_san = {m: {cach: xep[cach][m] for cach, _ in CACH_XEP} for m in ten}

    nhan = doc_nhan(duong_nhan, set(ten))
    trang_thai = tinh_trang_nhan(nhan)
    do = dong_thuan = None
    nguoi = (str((nhan or {}).get("nguoiGan1") or ""), str((nhan or {}).get("nguoiGan2") or ""))
    if nhan is not None and trang_thai in ("co_thong_nhat", "thong_nhat_mot_phan"):
        do = do_precision(theo_di_san, nhan)
    if nhan is not None and trang_thai != "trong":
        dong_thuan = do_dong_thuan(nhan)

    thu_muc = Path(args.out or Path(os.environ.get("TEMP", ".")) / f"dsvhvn-danhgia-{datetime.datetime.now():%Y%m%d%H%M%S}")
    thu_muc.mkdir(parents=True, exist_ok=True)
    bao_cao = viet_bao_cao(ten, theo_di_san, trang_thai, do, dong_thuan, nguoi)
    (thu_muc / "di-san-lien-quan.md").write_text(bao_cao, encoding="utf-8")
    (thu_muc / "di-san-lien-quan.json").write_text(json.dumps({
        "tinh_trang_nhan": trang_thai, "precision_at_3": do, "dong_thuan": dong_thuan, "nguong": NGUONG,
        "ba_di_san_dau": {str(m): {c: theo_di_san[m][c][:3] for c, _ in CACH_XEP} for m in sorted(theo_di_san)},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(bao_cao)
    print(f"\nĐã ghi {thu_muc / 'di-san-lien-quan.md'} và {thu_muc / 'di-san-lien-quan.json'}")


if __name__ == "__main__":
    main()
