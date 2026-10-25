# syntax=docker/dockerfile:1
# Ảnh Dịch vụ AI cho máy chủ Google Cloud, dựng bằng: docker build -t dsvhvn-ai .
# Khóa mô hình và khóa nội bộ truyền bằng biến môi trường lúc chạy (env_file của Docker Compose trên máy chủ), không nằm trong ảnh.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/dich-vu-ai
COPY requirements.txt requirements-giong.txt ./
RUN pip install -r requirements.txt
# Gói giọng đọc tiếng Việt tự host (POST /v1/tts). --no-deps vì tệp đã liệt kê đủ gói cần khi chạy (xem đầu requirements-giong.txt).
RUN pip install --no-deps -r requirements-giong.txt

COPY app ./app
RUN useradd --system --no-create-home --uid 10002 dichvuai
# Mô hình giọng đọc (~530 MB) tải từ Hugging Face về đây ở lần chạy đầu. Gắn /srv/mo-hinh là volume để các lần triển khai sau không tải lại:
# volume đặt tên mới tạo thừa hưởng quyền sở hữu của thư mục này, còn gắn thư mục của máy chủ thì phải chown cho uid 10002.
RUN mkdir -p /srv/mo-hinh && chown dichvuai /srv/mo-hinh
USER dichvuai
VOLUME /srv/mo-hinh

# Nghe mọi giao diện trong container để API ở container khác gọi được; máy chủ chỉ mở cổng ra 127.0.0.1.
ENV AI_HOST=0.0.0.0 \
    AI_PORT=8000
# Giọng đọc bật sẵn trong ảnh: mô hình nạp ở luồng nền nên /health trả 200 ngay (trường "tts" cho biết loading, ready hay error).
# Tắt bằng GIONG_DOC_BAT=0; GIONG_DOC_LUONG (số luồng, mặc định 2) và GIONG_DOC_DO_CHINH_XAC (auto, int8 hoặc fp32) chỉnh thêm.
ENV HF_HOME=/srv/mo-hinh \
    HF_HUB_DISABLE_TELEMETRY=1 \
    GIONG_DOC_BAT=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]
CMD ["python", "-m", "app.serve"]
