import os, tempfile, uuid, shlex, subprocess, glob
from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

APP_API_KEY = os.getenv("API_KEY", "")  # 배포 환경변수로 세팅
PORT = int(os.getenv("PORT", "8080"))  # PaaS 기본 포트를 따라감

app = FastAPI(title="YT -> MP3 (personal)")

# CORS: 필요한 도메인만 넣으세요 (개인용이면 대략 허용해도 무방)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _run(cmd: str):
    p = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip())
    return p.stdout

@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    # ✅ 이 두 경로는 누구나 접근 허용
    open_paths = {"/", "/healthz"}
    if APP_API_KEY and request.url.path not in open_paths:
        if request.headers.get("x-api-key") != APP_API_KEY:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/download")
def download(payload = Body(...)):
    url = (payload or {}).get("url", "").strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(400, "유효한 URL이 아닙니다.")

    workdir = tempfile.mkdtemp(prefix="ytmp3_")
    out_tpl = os.path.join(workdir, "%(title)s.%(ext)s")

    # yt-dlp로 mp3 추출(최상 음질: --audio-quality 0)
    cmd = f'yt-dlp -x --audio-format mp3 --audio-quality 0 -o "{out_tpl}" {shlex.quote(url)}'
    try:
        _run(cmd)
        mp3s = glob.glob(os.path.join(workdir, "*.mp3"))
        if not mp3s:
            raise HTTPException(500, "MP3 생성 실패")
        filepath = mp3s[0]
        # 안전한 파일명
        safe_name = f"{uuid.uuid4().hex}.mp3"
        return FileResponse(filepath, filename=safe_name, media_type="audio/mpeg")
    except RuntimeError as e:
        raise HTTPException(500, f"실패: {e}")

# 아주 간단한 테스트 UI 제공(선택)
@app.get("/", response_class=HTMLResponse)
def home():
    return '''
<!doctype html>
<html lang="ko">
<meta charset="utf-8">
<title>hello hona</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font-family:system-ui;max-width:720px;margin:40px auto;padding:0 16px;">
<h1>YouTube -> MP3</h1>
<input id="yt" placeholder="YouTube URL" style="width:100%;padding:10px;font-size:16px;" />
<input id="key" placeholder="API Key (배포시 설정)" style="width:100%;padding:10px;font-size:16px;margin-top:8px;" />
<button id="go" style="margin-top:12px;padding:10px 16px;font-size:16px;">Convert!</button>
<p id="s"></p>
<script>
  const go = document.getElementById('go');
  go.onclick = async () => {
    const url = document.getElementById('yt').value.trim();
    const key = document.getElementById('key').value.trim();
    const s = document.getElementById('s');
    if(!url){ alert('URL 입력'); return; }
    s.textContent = '변환 중...';
    try{
      const res = await fetch('/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': key },
        body: JSON.stringify({ url })
      });
      if(!res.ok){
        const t = await res.text();
        throw new Error(t);
      }
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'audio.mp3';
      a.click();
      URL.revokeObjectURL(a.href);
      s.textContent = '완료!';
    }catch(e){
      s.textContent = '오류: ' + e.message;
    }
  };
</script>
</body>
</html>
'''
