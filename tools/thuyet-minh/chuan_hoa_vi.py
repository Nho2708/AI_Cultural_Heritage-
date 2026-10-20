"""Chuẩn hóa văn bản tiếng Việt trước khi đưa vào mô hình đọc (VieNeu-TTS).

Mục tiêu: viết lại mọi thứ mà mô hình đọc hay đọc sai (số, ngày, số La Mã, đơn vị, chữ viết tắt, mã tháp,
ký tự markdown...) thành chữ tiếng Việt đúng như một thuyết minh viên bảo tàng sẽ đọc. Chỉ dùng cho văn bản đưa
vào máy đọc; câu hiển thị cho người dùng vẫn là câu gốc.

Các quy tắc đều dựa trên bảng tra (dict) để sau này bổ sung từ điển phát âm tên di sản mà không phải sửa logic.
Chỉ dùng thư viện chuẩn, chạy được với mọi Python >= 3.11.

Dùng thử:  python -X utf8 chuan_hoa_vi.py "Khu đền tháp Mỹ Sơn được xếp hạng ngày 10/5/2012."
"""
from __future__ import annotations

import re
import sys

# ----------------------------------------------------------------------------
# 1. Bảng tra (dữ liệu) — có thể bổ sung tự do
# ----------------------------------------------------------------------------

CHU_SO = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
HANG_LON = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ"]

# Tên chữ cái La-tinh theo cách đọc phổ thông ở Việt Nam
TEN_CHU_CAI = {
    "A": "a", "B": "bê", "C": "xê", "D": "dê", "E": "e", "F": "ép", "G": "giê",
    "H": "hát", "I": "i", "J": "gi", "K": "ca", "L": "e-lờ", "M": "em-mờ",
    "N": "en-nờ", "O": "o", "P": "pê", "Q": "quy", "R": "e-rờ", "S": "ét",
    "T": "tê", "U": "u", "V": "vê", "W": "vê kép", "X": "ích", "Y": "i dài",
    "Z": "dét",
}

# Chữ viết tắt (so khớp đúng chữ hoa/thường, nguyên từ)
VIET_TAT = {
    "UNESCO": "U-nét-xcô",
    "ASEAN": "A-xê-an",
    "ICOMOS": "I-cô-mốt",
    "UBND": "ủy ban nhân dân",
    "HĐND": "hội đồng nhân dân",
    "BVHTTDL": "Bộ Văn hóa, Thể thao và Du lịch",
    "BVHTT": "Bộ Văn hóa Thông tin",
    "TTg": "Thủ tướng Chính phủ",
    "CP": "Chính phủ",
    "QĐ": "quyết định",
    "NĐ": "nghị định",
    "TT": "thông tư",
    "TW": "trung ương",
    "GS.": "giáo sư",
    "PGS.": "phó giáo sư",
    "TS.": "tiến sĩ",
    "ThS.": "thạc sĩ",
    "KTS.": "kiến trúc sư",
    "TP.": "thành phố",
    "Tp.": "thành phố",
    "TP.HCM": "thành phố Hồ Chí Minh",
    "TPHCM": "thành phố Hồ Chí Minh",
    "Tp.HCM": "thành phố Hồ Chí Minh",
    "TX.": "thị xã",
    "TT.": "thị trấn",
}

# Chữ cái đơn + dấu chấm đứng trước một tên có dấu tiếng Việt → đơn vị hành chính
DIA_GIOI = {"P.": "phường", "Q.": "quận", "H.": "huyện", "X.": "xã"}

# Cơ quan ban hành trong số hiệu văn bản (phần sau dấu "/")
CO_QUAN_VAN_BAN = {
    "QĐ-TTg": "của Thủ tướng Chính phủ",
    "QĐ-BVHTTDL": "của Bộ Văn hóa, Thể thao và Du lịch",
    "QĐ-BVHTT": "của Bộ Văn hóa Thông tin",
    "QĐ-UBND": "của Ủy ban nhân dân",
    "NĐ-CP": "của Chính phủ",
    "QĐ-BVH": "của Bộ Văn hóa",
    "QĐ": "",
}

DON_VI = {
    "km²": "ki-lô-mét vuông", "km2": "ki-lô-mét vuông",
    "m²": "mét vuông", "m2": "mét vuông",
    "ha": "héc-ta", "km": "ki-lô-mét", "m": "mét", "cm": "xen-ti-mét",
    "mm": "mi-li-mét", "kg": "ki-lô-gam", "%": "phần trăm", "°C": "độ C",
}

# Từ điển phát âm tên riêng nước ngoài (bổ sung dần cho tên di sản)
PHAT_AM = {
    "Parmentier": "Pác-măng-chi-ê",
    "Stern": "Xtéc-nơ",
    "Paris": "Pa-ri",
    "Ganesa": "Ga-nê-sa",
    "Ganesha": "Ga-nê-sa",
    "Champa": "Chăm-pa",
    "Sanskrit": "Xan-xcơ-rít",
    "Finot": "Phi-nô",
    "Boisselier": "Boa-xơ-li-ê",
    "Kazik": "Ca-dích",
}

# Từ đứng trước một chữ cái đơn cho biết đó là mã/tên nhóm (tháp A, nhóm B...)
TU_BAO_MA_CHU = {"tháp", "nhóm", "khu", "chữ", "cái", "lô", "khối", "dãy", "tòa",
                 "tầng", "hạng", "loại", "cụm", "mã", "cổng", "đài"}

# ----------------------------------------------------------------------------
# 2. Đọc số
# ----------------------------------------------------------------------------


def _doc_ba_so(h: int, t: int, u: int, day_du: bool) -> str:
    """Đọc nhóm ba chữ số. day_du=True khi nhóm không đứng đầu (đọc 'không trăm')."""
    phan = []
    if h > 0 or day_du:
        phan.append(CHU_SO[h] + " trăm")
    if t == 0:
        if u > 0:
            phan.append(("linh " if (h > 0 or day_du) else "") + CHU_SO[u])
    elif t == 1:
        if u == 0:
            phan.append("mười")
        elif u == 5:
            phan.append("mười lăm")
        else:
            phan.append("mười " + CHU_SO[u])
    else:
        goc = CHU_SO[t] + " mươi"
        if u == 0:
            phan.append(goc)
        elif u == 1:
            phan.append(goc + " mốt")
        elif u == 4:
            phan.append(goc + " tư")
        elif u == 5:
            phan.append(goc + " lăm")
        else:
            phan.append(goc + " " + CHU_SO[u])
    return " ".join(phan)


def so_thanh_chu(n: int) -> str:
    """Số nguyên không âm → chữ tiếng Việt. 1484 → 'một nghìn bốn trăm tám mươi tư'."""
    if n == 0:
        return "không"
    nhom = []
    while n > 0:
        nhom.append(n % 1000)
        n //= 1000
    phan = []
    for i in range(len(nhom) - 1, -1, -1):
        g = nhom[i]
        day_du = i != len(nhom) - 1
        if g == 0 and i > 0:
            continue
        if g == 0 and i == 0:
            continue
        chu = _doc_ba_so(g // 100, (g // 10) % 10, g % 10, day_du)
        if HANG_LON[i]:
            chu += " " + HANG_LON[i]
        phan.append(chu)
    return " ".join(phan)


def chuoi_so_thanh_chu(s: str) -> str:
    """Đọc số viết theo kiểu Việt Nam: '.' ngăn nghìn, ',' là dấu phẩy thập phân.
    '5.717,878' → 'năm nghìn bảy trăm mười bảy phẩy tám bảy tám'."""
    s = s.strip()
    nguyen, _, thap = s.partition(",")
    nguyen = nguyen.replace(".", "")
    if not nguyen.isdigit():
        return s
    chu = so_thanh_chu(int(nguyen))
    if thap:
        chu += " phẩy " + " ".join(CHU_SO[int(c)] for c in thap if c.isdigit())
    return chu


def so_thu_tu(n: int) -> str:
    if n == 1:
        return "nhất"
    if n == 4:
        return "tư"
    return so_thanh_chu(n)


_LA_MA = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def la_ma_thanh_so(s: str) -> int:
    tong = 0
    for i, ch in enumerate(s):
        v = _LA_MA[ch]
        if i + 1 < len(s) and _LA_MA[s[i + 1]] > v:
            tong -= v
        else:
            tong += v
    return tong


def thang_thanh_chu(m: int) -> str:
    return "tư" if m == 4 else so_thanh_chu(m)


# ----------------------------------------------------------------------------
# 3. Các bước xử lý
# ----------------------------------------------------------------------------

_SO_VN = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?"


def bo_markdown(vb: str) -> str:
    vb = vb.replace("\r\n", "\n").replace("\r", "\n")
    vb = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", vb)           # ảnh
    vb = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", vb)         # liên kết
    vb = re.sub(r"<[^>\n]{1,200}>", " ", vb)                 # thẻ HTML
    vb = vb.replace("&nbsp;", " ").replace("&amp;", "&")
    def dong_rieng(m):
        # tiêu đề / đầu mục thành một câu riêng, kết thúc bằng dấu chấm
        noi_dung = m.group(1).strip()
        if noi_dung and noi_dung[-1] not in ".!?:;":
            noi_dung += "."
        return noi_dung
    vb = re.sub(r"^\s{0,3}#{1,6}\s*(.*)$", dong_rieng, vb, flags=re.MULTILINE)              # tiêu đề
    vb = re.sub(r"^\s*(?:[-*+•]|\d{1,2}[.)])\s+(.*)$", dong_rieng, vb, flags=re.MULTILINE)  # đầu mục
    vb = re.sub(r"^\s*>\s?", "", vb, flags=re.MULTILINE)             # trích dẫn
    vb = re.sub(r"^\s*(?:[-*_]\s*){3,}$", "", vb, flags=re.MULTILINE)  # kẻ ngang
    vb = re.sub(r"(\*\*|__)(.+?)\1", r"\2", vb, flags=re.DOTALL)  # đậm
    vb = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", vb)  # nghiêng
    vb = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"\1", vb)
    vb = vb.replace("`", "")
    vb = re.sub(r"\[\s*\d{1,3}\s*\]", "", vb)                # chú thích [1]
    vb = re.sub(r"\[(?:note|ghi chú)[^\]]*\]", "", vb, flags=re.IGNORECASE)
    return vb


def tach_doan(vb: str) -> list[str]:
    doan = re.split(r"\n\s*\n", vb)
    ket = []
    for d in doan:
        d = re.sub(r"\s+", " ", d).strip()
        if d:
            ket.append(d)
    return ket


def bo_ngoac_tieng_anh(vb: str) -> str:
    """Bỏ phần trong ngoặc chỉ gồm chữ La-tinh không dấu, từ hai từ trở lên
    (vd. '(My Son Sanctuary)') — thuyết minh viên thường bỏ qua."""
    def thay(m):
        ruot = m.group(1).strip()
        tu = ruot.split()
        if len(tu) >= 2 and all(re.fullmatch(r"[A-Za-z][A-Za-z'.-]*", t) for t in tu):
            return ""
        return m.group(0)
    return re.sub(r"\(([^()]*)\)", thay, vb)


def xu_ly_so_hieu_van_ban(vb: str) -> str:
    """'Quyết định 1272/QĐ-TTg' → 'Quyết định số một nghìn ... của Thủ tướng Chính phủ'."""
    def thay(m):
        truoc, so, duoi = m.group(1) or "", m.group(2), m.group(3)
        co_quan = CO_QUAN_VAN_BAN.get(duoi)
        if co_quan is None:
            # chưa có trong bảng: đọc từng phần theo bảng viết tắt hoặc tên chữ cái
            phan = []
            for p in duoi.split("-"):
                if p in VIET_TAT:
                    phan.append(VIET_TAT[p])
                else:
                    phan.append(" ".join(TEN_CHU_CAI.get(c, c) for c in p))
            co_quan = " ".join(phan)
        dau = "" if truoc.strip().lower() == "số" else "số "
        ket = (truoc + dau + so_thanh_chu(int(so)) + (" " + co_quan if co_quan else "")).strip()
        return " " + ket if m.group(0).startswith(" ") else ket
    return re.sub(r"(\bsố\s+)?(\d{1,6})/([A-ZĐa-z]{1,8}(?:-[A-Za-zĐ]{1,10})+)\b", thay, vb)


def xu_ly_ngay_thang(vb: str) -> str:
    def ngay(m):
        d, mo, y = int(m.group(2)), int(m.group(3)), int(m.group(4))
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            return m.group(0)
        dau = "Ngày" if (m.group(1) or "").startswith("N") else "ngày"
        return f"{dau} {so_thanh_chu(d)} tháng {thang_thanh_chu(mo)} năm {so_thanh_chu(y)}"
    vb = re.sub(r"([Nn]gày\s+)?(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", ngay, vb)

    def thang(m):
        mo, y = int(m.group(2)), int(m.group(3))
        if not 1 <= mo <= 12:
            return m.group(0)
        dau = "Tháng" if (m.group(1) or "").startswith("T") else "tháng"
        return f"{dau} {thang_thanh_chu(mo)} năm {so_thanh_chu(y)}"
    vb = re.sub(r"([Tt]háng\s+)?(?<!\d)(\d{1,2})/(\d{4})(?!\d)", thang, vb)
    return vb


def xu_ly_the_ky_la_ma(vb: str) -> str:
    def thay(m):
        goc, a, b = m.group(1), m.group(2), m.group(3)
        chu = goc + " " + so_thanh_chu(la_ma_thanh_so(a))
        if b:
            chu += " đến " + so_thanh_chu(la_ma_thanh_so(b))
        return chu
    return re.sub(r"\b([Tt]hế k[ỷỉ]|[Tt]hiên niên k[ỷỉ]|[Tt]hập niên|[Tt]hập kỷ)\s+([IVXLCDM]+)"
                  r"(?:\s*[–—-]\s*([IVXLCDM]+))?(?![A-Za-z])", thay, vb)


def xu_ly_khoang_nam(vb: str) -> str:
    """'Năm 1903–1904' → 'Từ năm ... đến năm ...'; '(1903–1904)' → 'từ năm ... đến năm ...'."""
    def nam(m):
        tu, y1, y2 = m.group(1), so_thanh_chu(int(m.group(2))), so_thanh_chu(int(m.group(3)))
        if tu is None:
            return f"từ năm {y1} đến năm {y2}"
        if tu.lower().startswith("từ"):
            return f"{tu}{y1} đến năm {y2}"
        return ("Từ " if tu[0].isupper() else "từ ") + f"năm {y1} đến năm {y2}"
    vb = re.sub(r"((?:[Tt]ừ\s+)?[Nn]ăm\s+)?(?<!\d)(\d{4})\s*[–—-]\s*(\d{4})(?!\d)", nam, vb)

    def khoang(m):
        return f"{chuoi_so_thanh_chu(m.group(1))} đến {chuoi_so_thanh_chu(m.group(2))}"
    return re.sub(rf"(?<![\d.,])({_SO_VN})\s*[–—-]\s*({_SO_VN})(?![\d])", khoang, vb)


def xu_ly_viet_tat(vb: str) -> str:
    khoa = sorted(VIET_TAT, key=len, reverse=True)
    mau = "|".join(re.escape(k) for k in khoa)
    return re.sub(rf"(?<![\w])({mau})(?![\w])", lambda m: VIET_TAT[m.group(1)], vb)


def xu_ly_chu_cai_dau_ten(vb: str) -> str:
    """'H. Parmentier' → 'hát Parmentier'; 'H. Thanh Trì' → 'huyện Thanh Trì'."""
    def thay(m):
        chu, ten = m.group(1), m.group(2)
        co_dau = re.search(r"[^\x00-\x7F]", ten) is not None
        if co_dau and chu + "." in DIA_GIOI:
            return DIA_GIOI[chu + "."] + " " + ten
        return TEN_CHU_CAI[chu] + " " + ten
    return re.sub(r"(?<![\w])([A-Z])\.\s+([A-ZÀ-Ỹ][\w'-]*(?:\s+[A-ZÀ-Ỹ][\w'-]*)?)", thay, vb)


def xu_ly_ma_chu_so(vb: str) -> str:
    """'tháp E5' → 'tháp e năm'."""
    return re.sub(r"(?<![\w])([A-Z])(\d{1,3})(?![\w])",
                  lambda m: TEN_CHU_CAI[m.group(1)] + " " + so_thanh_chu(int(m.group(2))), vb)


def xu_ly_chu_cai_don(vb: str) -> str:
    """Chữ cái đơn trong danh sách mã (A, A', B, C...) → tên chữ cái."""
    mau = re.compile(r"(?<![\w-])([A-Z])(['’]?)(?![\w'’-])")

    def thay(m):
        chu, pham = m.group(1), m.group(2)
        truoc = vb[:m.start()]
        sau = vb[m.end():]
        tu_truoc = re.findall(r"[\wÀ-ỹ]+|[,;:.]", truoc[-40:])
        tu_truoc = tu_truoc[-1].lower() if tu_truoc else ""
        sau_chuoi = sau.lstrip()
        dieu_kien = (
            pham
            or sau_chuoi == "" or sau_chuoi[0] in ",.;:)–—-"
            or re.match(r"(và|hoặc|hay|cùng)\b", sau_chuoi)
            or truoc.rstrip().endswith(",")
            or tu_truoc in TU_BAO_MA_CHU
        )
        if not dieu_kien:
            return m.group(0)
        return TEN_CHU_CAI[chu] + (" phẩy" if pham else "")
    return mau.sub(thay, vb)


def xu_ly_thu_tu(vb: str) -> str:
    return re.sub(r"\b(thứ|hạng|đời|khóa|lần)\s+(\d{1,4})\b",
                  lambda m: m.group(1) + " " + (so_thu_tu(int(m.group(2))) if m.group(1) == "thứ"
                                                 else so_thanh_chu(int(m.group(2)))), vb)


def xu_ly_don_vi(vb: str) -> str:
    khoa = sorted(DON_VI, key=len, reverse=True)
    mau = "|".join(re.escape(k) for k in khoa)
    return re.sub(rf"({_SO_VN})\s*({mau})(?![A-Za-zÀ-ỹ0-9])",
                  lambda m: chuoi_so_thanh_chu(m.group(1)) + " " + DON_VI[m.group(2)], vb)


def xu_ly_so_con_lai(vb: str) -> str:
    vb = re.sub(rf"(?<![\d.,])({_SO_VN})(?![\d])", lambda m: chuoi_so_thanh_chu(m.group(1)), vb)
    # số thập phân kiểu quốc tế còn sót (3.5) → đọc 'phẩy'
    vb = re.sub(r"(?<!\d)(\d+)\.(\d{1,2})(?!\d)",
                lambda m: so_thanh_chu(int(m.group(1))) + " phẩy " + " ".join(CHU_SO[int(c)] for c in m.group(2)), vb)
    vb = re.sub(r"\d+", lambda m: so_thanh_chu(int(m.group(0))), vb)
    return vb


def xu_ly_dau_cau(vb: str) -> str:
    vb = re.sub(r"\s*[–—]\s*", ", ", vb)                  # gạch ngang dài = ngắt
    vb = re.sub(r"(?<=\S)\s+-\s+(?=\S)", ", ", vb)         # ' - ' giữa hai từ
    vb = re.sub(r"[“”„\"«»]", ", ", vb)                    # ngoặc kép = ngắt
    vb = re.sub(r"(?<!\w)['‘’]|['‘’](?!\w)", ", ", vb)     # ngoặc đơn kiểu trích dẫn
    vb = re.sub(r"\s*\(\s*", ", ", vb)
    vb = re.sub(r"\s*\)\s*", ", ", vb)
    vb = re.sub(r"\s*:\s*", ", ", vb)
    vb = re.sub(r"\s*;\s*", ". ", vb)
    vb = vb.replace("…", ".").replace("...", ".")
    vb = re.sub(r"\s*/\s*", ", ", vb)
    vb = vb.replace("&", " và ").replace("°", " độ ")
    return vb


def ap_dung_phat_am(vb: str) -> str:
    if not PHAT_AM:
        return vb
    khoa = sorted(PHAT_AM, key=len, reverse=True)
    mau = "|".join(re.escape(k) for k in khoa)
    return re.sub(rf"(?<![\w])({mau})(?![\w])", lambda m: PHAT_AM[m.group(1)], vb)


def don_dep(vb: str) -> str:
    vb = re.sub(r"\s+", " ", vb).strip()
    for _ in range(3):
        vb = re.sub(r"\s*,(\s*,)+", ",", vb)               # ', ,' → ','
        vb = re.sub(r"\s*,\s*([.!?])", r"\1", vb)           # ', .' → '.'
        vb = re.sub(r"([.!?])\s*,", r"\1", vb)              # '. ,' → '.'
        vb = re.sub(r"\s+([,.!?])", r"\1", vb)
        vb = re.sub(r"([.!?])(\s*[.!?])+", r"\1", vb)
        vb = re.sub(r"([,.!?])(?=[^\s])", r"\1 ", vb)
    vb = re.sub(r"^[\s,.;:]+", "", vb)
    vb = re.sub(r"[\s,;:]+$", "", vb)
    vb = re.sub(r"\s+", " ", vb).strip()
    if vb and vb[-1] not in ".!?":
        vb += "."
    # viết hoa chữ đầu câu (sau dấu kết câu) cho dễ đọc, không ảnh hưởng giọng đọc
    vb = re.sub(r"(^|[.!?]\s+)([a-zà-ỹ])", lambda m: m.group(1) + m.group(2).upper(), vb)
    return vb


def chuan_hoa_doan(doan: str, bo_ngoac_anh: bool = True) -> str:
    vb = doan
    if bo_ngoac_anh:
        vb = bo_ngoac_tieng_anh(vb)
    vb = xu_ly_so_hieu_van_ban(vb)
    vb = xu_ly_ngay_thang(vb)
    vb = xu_ly_the_ky_la_ma(vb)
    vb = xu_ly_khoang_nam(vb)
    vb = xu_ly_viet_tat(vb)
    vb = xu_ly_chu_cai_dau_ten(vb)
    vb = xu_ly_ma_chu_so(vb)
    vb = xu_ly_thu_tu(vb)
    vb = xu_ly_don_vi(vb)
    vb = xu_ly_so_con_lai(vb)
    vb = xu_ly_chu_cai_don(vb)
    vb = xu_ly_dau_cau(vb)
    vb = ap_dung_phat_am(vb)
    return don_dep(vb)


def chuan_hoa(van_ban: str, bo_ngoac_anh: bool = True) -> str:
    """Văn bản (có thể có markdown, nhiều đoạn) → văn bản đọc được.
    Các đoạn cách nhau bằng một dòng trống; mỗi đoạn kết thúc bằng dấu câu."""
    vb = bo_markdown(van_ban)
    doan = [chuan_hoa_doan(d, bo_ngoac_anh) for d in tach_doan(vb)]
    return "\n\n".join(d for d in doan if d)


if __name__ == "__main__":
    print(chuan_hoa(" ".join(sys.argv[1:])))
