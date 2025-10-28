# 1) 경량 이미지
FROM python:3.11-slim

# 2) ffmpeg 설치 (yt-dlp 변환용)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates &&     rm -rf /var/lib/apt/lists/*

# 3) 앱 디렉토리
WORKDIR /app

# 4) 파이썬 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5) 소스 복사
COPY app.py .

# 6) 환경변수 기본값 (PaaS에서 덮어쓰기)
ENV PORT=8080
ENV API_KEY=

# 7) 실행
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
