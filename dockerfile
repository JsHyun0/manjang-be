# Python 베이스 이미지(슬림)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 시스템 의존성(필요시 추가, 현재는 불필요)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     && rm -rf /var/lib/apt/lists/*

# 의존성 먼저 설치
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스 복사
COPY . .

# Cloud Run이 제공하는 PORT 환경변수에 바인딩
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]