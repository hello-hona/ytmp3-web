import os, tempfile, uuid, shlex, subprocess, glob, re
from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

APP_API_KEY = os.getenv("API_KEY", "")
PORT = int(os.getenv("PORT", "8080"))

app = FastAPI(title="YT to MP3 (personal)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 미들웨어: /, /healthz는 오픈, 그 외는 API Key 필수 ─────────────────────
@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    # 여기에 index.html을 추가
    open_paths = {"/", "/healthz", "/index.html"}
    # 정적 파일도 쓸 거면 /static 같은 prefix도 허용
    if (APP_API_KEY
        and request.url.path not in open_paths
        and not request.url.path.startswith("/static")):
        if request.headers.get("x-api-key") != APP_API_KEY:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/healthz")
def healthz():
    return {"ok": True}

# ── 홈: 간단 안내 페이지 ────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!doctype html>
<html lang="ko">
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>YouTube → MP3 (웹 UI)</title>
<body style="font-family:system-ui;max-width:760px;margin:36px auto;padding:0 16px;">
  <h1 style="margin-bottom:12px;">YouTube → MP3</h1>

  <label>API Key
    <input id="key" type="password" placeholder="API Key"
           style="width:100%;padding:10px;margin:6px 0 12px 0;">
  </label>

  <label>YouTube URL
    <input id="url" type="url" placeholder="https://www.youtube.com/watch?v=..."
           style="width:100%;padding:10px;margin:6px 0 16px 0;">
  </label>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
    <label>Audio format
      <select id="fmt" style="width:100%;padding:10px;">
        <option value="mp3">mp3</option>
        <option value="m4a">m4a</option>
        <option value="flac">flac</option>
        <option value="wav">wav</option>
        <option value="opus">opus</option>
      </select>
    </label>
    <label>Audio quality (0=best)
      <select id="aq" style="width:100%;padding:10px;">
        <option value="0">0 (best)</option>
        <option value="1">1</option><option value="2">2</option>
        <option value="3">3</option><option value="4">4</option>
        <option value="5">5</option><option value="6">6</option>
        <option value="7">7</option><option value="8">8</option>
        <option value="9">9</option><option value="10">10</option>
      </select>
    </label>
  </div>

  <div style="margin-top:14px;">
    <label style="display:block;margin:6px 0;">
      <input type="checkbox" id="embedMeta"> 메타데이터 임베드 (--embed-metadata)
    </label>
    <label style="display:block;margin:6px 0;">
      <input type="checkbox" id="embedThumb"> 썸네일 임베드 (--embed-thumbnail)
    </label>
    <div style="display:flex;gap:8px;align-items:center;margin:6px 0;">
      <label><input type="checkbox" id="convThumb"> 썸네일 변환 (--convert-thumbnails)</label>
      <select id="thumbFmt" style="padding:8px;">
        <option value="jpg">jpg</option>
        <option value="png">png</option>
        <option value="webp">webp</option>
      </select>
    </div>
  </div>

  <button id="go" style="margin-top:14px;padding:12px 16px;font-size:16px;">Convert & Download</button>
  <span id="status" style="margin-left:10px;color:#666;"></span>

  <script>
    const keyEl = document.getElementById('key');
    keyEl.value = localStorage.getItem('apiKey') || '';
    keyEl.addEventListener('change', () => localStorage.setItem('apiKey', keyEl.value));

    async function convert() {
      const key = keyEl.value.trim();
      const url = document.getElementById('url').value.trim();
      const fmt = document.getElementById('fmt').value;
      const aq  = document.getElementById('aq').value;
      const embedMeta  = document.getElementById('embedMeta').checked;
      const embedThumb = document.getElementById('embedThumb').checked;
      const convThumb  = document.getElementById('convThumb').checked;
      const thumbFmt   = document.getElementById('thumbFmt').value;
      const status = document.getElementById('status');

      if (!url) { alert('YouTube URL을 입력하세요'); return; }
      if (!key) { alert('API Key를 입력하세요'); return; }

      const args = ["--audio-format", fmt, "--audio-quality", aq];
      if (embedMeta)  args.push("--embed-metadata");
      if (embedThumb) args.push("--embed-thumbnail");
      if (convThumb)  args.push("--convert-thumbnails", thumbFmt);

      status.textContent = "변환 중...";

      try{
        const res = await fetch("/cli", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-API-Key": key },
          body: JSON.stringify({ url, args })
        });
        if (!res.ok) throw new Error(await res.text());
        const blob = await res.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "audio.mp3";
        a.click();
        URL.revokeObjectURL(a.href);
        status.textContent = "완료!";
      }catch(e){
        status.textContent = "오류: " + e.message;
      }
    }
    document.getElementById('go').addEventListener('click', convert);
  </script>
</body>
</html>
"""

# ── yt-dlp 화이트리스트 ───────────────────────────────────────────────
ALLOWED = {
    "--audio-format":   {"arity": 1, "choices": {"mp3","m4a","flac","wav","opus"}},
    "--audio-quality":  {"arity": 1, "pattern": r"^(?:0|[1-9]|10)$"},  # 0=best
    "--embed-thumbnail":{"arity": 0},
    "--convert-thumbnails": {"arity": 1, "choices": {"jpg","png","webp"}},
    "--embed-metadata": {"arity": 0},
}

def _validate_args(raw_args):
    args = []
    i = 0
    while i < len(raw_args):
        flag = raw_args[i]
        spec = ALLOWED.get(flag)
        if not spec:
            raise HTTPException(400, f"허용되지 않은 옵션: {flag}")
        arity = spec.get("arity", 0)
        vals = []
        for j in range(arity):
            if i+1+j >= len(raw_args):
                raise HTTPException(400, f"{flag} 옵션에 값이 필요합니다")
            vals.append(raw_args[i+1+j])
        if "choices" in spec and vals and vals[0] not in spec["choices"]:
            raise HTTPException(400, f"{flag} 값 허용범위 아님: {vals[0]}")
        if "pattern" in spec and vals and not re.match(spec["pattern"], vals[0]):
            raise HTTPException(400, f"{flag} 값 형식 오류: {vals[0]}")
        args.append(flag); args.extend(vals)
        i += 1 + arity
    return args

# ── /cli: 쉘 감각 API (웹에서 버튼-클릭으로도 호출) ─────────────────────
@app.post("/cli")
def cli(body = Body(...)):
    url = (body or {}).get("url","").strip()
    raw_args = (body or {}).get("args", [])
    if not url.startswith(("http://","https://")):
        raise HTTPException(400, "유효한 URL")

    # 허용 옵션만 통과
    safe = _validate_args(raw_args)

    # 출력경로 사용자는 금지, 서버가 강제 지정
    if "-o" in safe or "--output" in safe:
        raise HTTPException(400, "출력 경로 옵션은 허용되지 않습니다")

    workdir = tempfile.mkdtemp(prefix="ytmp3_")
    out_tpl = os.path.join(workdir, "%(title)s.%(ext)s")

    # 강제: 오디오 추출
    safe = ["-x"] + safe + ["-o", out_tpl]

    # 기본 보정 인자(효과는 영상별 상이)
    ua = os.getenv("YTDLP_UA",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36")
    if "--user-agent" not in safe:
        safe += ["--user-agent", ua]
    if "--extractor-args" not in safe:
        safe += ["--extractor-args", "youtube:player_client=android"]
    if "--geo-bypass" not in safe:
        safe += ["--geo-bypass"]

    # 서버 저장 쿠키 자동 사용 (YTDLP_COOKIES)
    cookies_text = os.getenv("YTDLP_COOKIES", "").strip()
    if cookies_text:
        cookie_file = os.path.join(workdir, "cookies.txt")
        with open(cookie_file, "w", encoding="utf-8") as f:
            f.write(cookies_text)
        safe += ["--cookies", cookie_file]

    # 실행
    cmd = ["yt-dlp"] + safe + [url]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise HTTPException(500, f"실패:\n{p.stderr}")

    mp3s = glob.glob(os.path.join(workdir, "*.mp3"))
    if not mp3s:
        raise HTTPException(500, "결과 파일이 없습니다")
    return FileResponse(mp3s[0], filename=f"{uuid.uuid4().hex}.mp3", media_type="audio/mpeg")
