# syntax=docker/dockerfile:1
# Ảnh Dịch vụ AI cho máy chủ Google Cloud, dựng bằng: docker build -t dsvhvn-ai .
# Khóa mô hình và khóa nội bộ truyền bằng biến môi trường lúc chạy (env_file của Docker Compose trên máy chủ), không nằm trong ảnh.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/dich-vu-ai
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
RUN useradd --system --no-create-home --uid 10002 dichvuai
USER dichvuai

# Nghe mọi giao diện trong container để API ở container khác gọi được; máy chủ chỉ mở cổng ra 127.0.0.1.
ENV AI_HOST=0.0.0.0 \
    AI_PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]
CMD ["python", "-m", "app.serve"]
