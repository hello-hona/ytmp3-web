# YT -> MP3 개인용 (FastAPI)

## 로컬 테스트 (Docker)
```bash
docker build -t ytmp3 .
docker run --rm -p 8080:8080 -e API_KEY=devkey ytmp3
# 브라우저에서 http://localhost:8080 열기
```

## API
- `GET /healthz` → `{ "ok": true }`
- `POST /download`  
  Body: `{ "url": "https://www.youtube.com/watch?v=..." }`  
  Header: `X-API-Key: <API_KEY>`

## 배포(예시: Render)
1. GitHub에 이 폴더를 올린 뒤
2. Render Dashboard → New → Web Service → Docker로 배포
3. Port: 8080
4. Environment Variables: `API_KEY`, `CORS_ALLOW_ORIGINS` 설정
5. 배포 후 제공된 URL 접속
