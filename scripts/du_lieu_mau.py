"""Dữ liệu mẫu (một di sản có thật) để thử dịch vụ AI bằng lời gọi thật. Chữ do nhóm tự viết, ngắn gọn, đúng dữ kiện phổ thông."""
from __future__ import annotations

NOI_DUNG = """## Lịch sử hình thành

Năm 1010, vua Lý Thái Tổ quyết định dời đô từ Hoa Lư ra vùng Đại La và đổi tên thành Thăng Long. Từ đó, nơi đây trở thành trung tâm quyền lực của nhiều triều đại: nhà Lý, nhà Trần, nhà Lê sơ, nhà Mạc và nhà Lê trung hưng. Đến năm 1802, nhà Nguyễn chọn Huế làm kinh đô, Thăng Long không còn là kinh đô nhưng vẫn là một đô thị quan trọng của miền Bắc.

## Khu di tích

Hoàng thành Thăng Long nằm ở trung tâm thành phố Hà Nội ngày nay, gồm khu khảo cổ học tại số 18 Hoàng Diệu và khu Thành cổ Hà Nội. Các nhà khảo cổ đã phát hiện nhiều lớp văn hóa chồng lên nhau, từ thời Đại La đến thời Lý, Trần, Lê và Nguyễn, cùng hàng nghìn hiện vật gốm sứ, gạch ngói và dấu tích cung điện. Những công trình còn lại trên mặt đất gồm Đoan Môn, Cột cờ Hà Nội, Cửa Bắc và Hậu Lâu.

## Giá trị

Tháng 7 năm 2010, đúng dịp kỷ niệm một nghìn năm Thăng Long, khu trung tâm Hoàng thành được UNESCO ghi danh là Di sản thế giới. Di sản được công nhận vì là minh chứng cho sự giao lưu văn hóa lâu dài, cho truyền thống văn hiến của người Việt và cho sự tiếp nối liên tục của một trung tâm quyền lực suốt hơn mười thế kỷ."""

MO_TA_NGAN = "Trung tâm quyền lực của các triều đại Việt Nam suốt hơn mười thế kỷ, được UNESCO ghi danh là Di sản thế giới năm 2010."

DONG_THOI_GIAN = [
    (101, "Thời Lý", "Dời đô ra Thăng Long", "Vua Lý Thái Tổ dời đô từ Hoa Lư ra Đại La và đổi tên là Thăng Long.", 1010, "1010"),
    (102, "Thời Trần", "Xây dựng và tu bổ thành", "Nhà Trần tiếp tục xây dựng và mở rộng kinh thành Thăng Long.", 1230, "Năm 1230"),
    (103, "Thời Lê", "Điện Kính Thiên được xây dựng", "Điện Kính Thiên là nơi vua nhà Lê thiết triều.", 1428, "Năm 1428"),
    (104, "Thời Nguyễn", "Kinh đô dời về Huế", "Nhà Nguyễn chọn Huế làm kinh đô.", 1802, "Năm 1802"),
    (105, "Hiện đại", "Khai quật khu 18 Hoàng Diệu", "Các nhà khảo cổ phát hiện nhiều lớp văn hóa chồng lên nhau.", 2002, "Năm 2002"),
    (106, "Hiện đại", "UNESCO ghi danh", "Khu trung tâm Hoàng thành được ghi danh là Di sản thế giới.", 2010, "Tháng 7 năm 2010"),
]

ANH = [
    (9001, "/media/hoang-thanh/doan-mon.jpg", "Đoan Môn, cổng phía nam của Hoàng thành"),
    (9002, "/media/hoang-thanh/dien-kinh-thien.jpg", "Nền điện Kính Thiên với thềm rồng đá"),
    (9003, "/media/hoang-thanh/cot-co.jpg", "Cột cờ Hà Nội"),
    (9004, "/media/hoang-thanh/khao-co.jpg", "Hố khai quật khảo cổ tại 18 Hoàng Diệu"),
    (9005, "/media/hoang-thanh/cua-bac.jpg", "Cửa Bắc với vết đạn pháo còn lại"),
]

NGUON = [
    {"title": "Cục Di sản văn hóa - Hoàng thành Thăng Long (dsvh.gov.vn, truy cập 10/2026)", "url": "https://dsvh.gov.vn"},
]


def di_san(heritage_id: int = 1) -> dict:
    return {
        "heritageId": heritage_id,
        "name": "Hoàng thành Thăng Long",
        "shortDescription": MO_TA_NGAN,
        "content": NOI_DUNG,
        "timeline": [
            {"eventId": e[0], "phase": e[1], "name": e[2], "description": e[3], "startYear": e[4], "dateLabel": e[5]}
            for e in DONG_THOI_GIAN
        ],
        "sources": NGUON,
        "images": [{"mediaId": a[0], "url": a[1], "caption": a[2]} for a in ANH],
    }


def van_ban_di_san() -> dict:
    return {
        "name": "Hoàng thành Thăng Long",
        "shortDescription": MO_TA_NGAN,
        "content": NOI_DUNG,
        "timelines": [
            {"id": 11, "name": "Thời Lý", "description": "Kinh thành Thăng Long được lập năm 1010."},
            {"id": 12, "name": "Thời Hậu Lê", "description": "Điện Kính Thiên được xây dựng."},
        ],
        "events": [
            {"id": 101, "timelineId": 11, "name": "Dời đô ra Thăng Long", "description": "Vua Lý Thái Tổ dời đô từ Hoa Lư ra Đại La."},
            {"id": 103, "timelineId": 12, "name": "Xây điện Kính Thiên", "description": "Nơi vua nhà Lê thiết triều."},
        ],
        "media": [{"id": a[0], "caption": a[2]} for a in ANH[:3]],
    }
