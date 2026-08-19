import base64
import io
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import modal

app = modal.App("runner3-gwen-tts")
model_cache = modal.Volume.from_name("runner3-gwen-tts-cache", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1", "git")
    .run_commands(
        "python -m pip install --upgrade pip",
        "python -m pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124",
    )
    .pip_install(
        "qwen-tts==0.1.1",
        "fastapi[standard]>=0.115",
        "python-multipart>=0.0.9",
        "soundfile>=0.12",
        "requests>=2.32",
    )
    .env(
        {
            "HF_HOME": "/cache/huggingface",
            "HF_HUB_CACHE": "/cache/huggingface/hub",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
)

MODEL_ID = "g-group-ai-lab/gwen-tts-0.6B"
_model = None

GENERATION_CONFIG = dict(
    temperature=0.3,
    top_k=20,
    top_p=0.9,
    max_new_tokens=4096,
    repetition_penalty=2.0,
    subtalker_do_sample=True,
    subtalker_temperature=0.1,
    subtalker_top_k=20,
    subtalker_top_p=1.0,
)

DEMO_REF_URL = "https://raw.githubusercontent.com/ggroup-ai-lab/gwen-tts/main/data/ref_audio/khanh_toan.wav"
DEMO_REF_TEXT = "việt nam đang kiêu hãnh bước vào kỷ nguyên vươn mình rực rỡ với khát vọng mãnh liệt, trí tuệ đổi mới, tinh thần đoàn kết."
DEMO_TEXT = "Buổi sáng, thành phố vẫn còn yên tĩnh. Ánh nắng đầu ngày chiếu qua khung cửa, làm căn phòng sáng lên một cách dịu dàng."

VOICE_CLONE_UI = '''<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Gwen-TTS Voice Clone</title>
<style>
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#111;background:#f5f5f7}
*{box-sizing:border-box}body{margin:0;padding:18px 14px 48px}.wrap{max-width:720px;margin:auto}.card{background:#fff;border-radius:20px;padding:20px;box-shadow:0 6px 24px rgba(0,0,0,.07);margin-bottom:14px}
h1{font-size:27px;line-height:1.15;margin:0 0 8px}.sub{margin:0;color:#666;line-height:1.45}.badge{display:inline-block;background:#eef7ee;border-radius:999px;padding:7px 10px;font-size:13px;margin:12px 5px 0 0}
h2{font-size:18px;margin:0 0 8px}.hint{font-size:13px;color:#777;line-height:1.45;margin:0 0 12px}
label{font-size:14px;font-weight:700;display:block;margin:14px 0 7px}textarea,input[type=file]{width:100%;font:inherit;font-size:16px;border:1px solid #d7d7dc;border-radius:13px;background:#fff;color:#111}textarea{padding:13px;line-height:1.45;resize:vertical}input[type=file]{padding:12px;background:#fafafa}
button{width:100%;appearance:none;border:0;border-radius:14px;background:#111;color:#fff;font-size:17px;font-weight:700;padding:14px;min-height:52px}button:disabled{opacity:.45}.status{font-size:14px;color:#555;min-height:22px;line-height:1.4;margin-top:10px}audio{width:100%;margin-top:10px}.links{display:flex;gap:8px;margin-top:14px}.links a{flex:1;text-align:center;text-decoration:none;color:#111;background:#f0f0f2;border-radius:11px;padding:11px;font-size:13px}.privacy{font-size:12px;color:#777;line-height:1.4;margin-top:12px}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>Gwen‑TTS Voice Clone</h1>
    <p class="sub">Dùng 10–20 giây giọng mẫu để đọc một đoạn tiếng Việt mới bằng cùng giọng.</p>
    <span class="badge">NVIDIA L4</span><span class="badge">BF16</span><span class="badge">Zero-shot</span>
  </div>

  <form id="cloneForm" class="card">
    <h2>1 · Giọng mẫu</h2>
    <p class="hint">Trên iPhone, bấm bên dưới để thu/chọn audio. Nên dùng đoạn sạch, không nhạc nền.</p>
    <input id="refAudio" name="ref_audio" type="file" accept="audio/*" capture="microphone" required>
    <audio id="refPlayer" controls playsinline preload="metadata"></audio>

    <label for="refText">2 · Transcript chính xác</label>
    <textarea id="refText" name="ref_text" rows="4" maxlength="3000" required placeholder="Gõ đúng từng chữ đã nói trong audio mẫu."></textarea>

    <label for="outText">3 · Văn bản cần đọc</label>
    <textarea id="outText" name="text" rows="6" maxlength="5000" required>Buổi sáng, thành phố vẫn còn yên tĩnh. Ánh nắng đầu ngày chiếu qua khung cửa, làm căn phòng sáng lên một cách dịu dàng.</textarea>
    <input type="hidden" name="language" value="Vietnamese">

    <div style="margin-top:14px"><button id="generate" type="submit">Tạo giọng của tôi</button></div>
    <div id="status" class="status">Sẵn sàng.</div>
    <audio id="resultPlayer" controls playsinline preload="none"></audio>
    <p class="privacy">Reference được xử lý tạm thời để sinh giọng rồi xóa sau request. Đây vẫn là endpoint thử nghiệm public.</p>
    <div class="links"><a href="/health">Health</a><a href="/demo">Demo có sẵn</a></div>
  </form>
</div>
<script>
(function(){
  const form=document.getElementById('cloneForm');
  const file=document.getElementById('refAudio');
  const refPlayer=document.getElementById('refPlayer');
  const resultPlayer=document.getElementById('resultPlayer');
  const status=document.getElementById('status');
  const button=document.getElementById('generate');
  let refUrl=null,resultUrl=null;

  file.addEventListener('change',function(){
    const f=file.files&&file.files[0];
    if(!f)return;
    if(refUrl)URL.revokeObjectURL(refUrl);
    refUrl=URL.createObjectURL(f);
    refPlayer.src=refUrl;
    status.textContent='Giọng mẫu sẵn sàng · '+Math.round(f.size/1024)+' KB';
  });

  form.addEventListener('submit',async function(e){
    e.preventDefault();
    if(!file.files||!file.files[0]){status.textContent='Hãy thu hoặc chọn audio mẫu.';return;}
    button.disabled=true;
    status.textContent='Đang khởi động GPU và tạo giọng…';
    try{
      const fd=new FormData(form);
      const r=await fetch('/tts-upload',{method:'POST',body:fd,cache:'no-store'});
      if(!r.ok){
        let msg='HTTP '+r.status;
        try{const j=await r.json();if(j.detail)msg=j.detail}catch(_e){}
        throw new Error(msg);
      }
      const blob=await r.blob();
      if(resultUrl)URL.revokeObjectURL(resultUrl);
      resultUrl=URL.createObjectURL(blob);
      resultPlayer.src=resultUrl;
      status.textContent='Xong · nhấn Play để nghe.';
      try{await resultPlayer.play()}catch(_e){}
    }catch(err){
      status.textContent='Lỗi: '+err.message;
    }finally{
      button.disabled=false;
    }
  });
})();
</script>
</body>
</html>'''


def _gpu_info() -> str:
    return subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
        text=True,
    ).strip()


def _load_model():
    global _model
    if _model is not None:
        return _model
    import torch
    from qwen_tts import Qwen3TTSModel
    _model = Qwen3TTSModel.from_pretrained(
        MODEL_ID,
        device_map="cuda:0",
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
    )
    try:
        model_cache.commit()
    except Exception:
        pass
    return _model


def _synth(text: str, ref_audio_path: str, ref_text: str, language: str = "Vietnamese") -> bytes:
    import soundfile as sf
    model = _load_model()
    wavs, sr = model.generate_voice_clone(
        text=text,
        language=language,
        ref_audio=ref_audio_path,
        ref_text=ref_text,
        **GENERATION_CONFIG,
    )
    out = io.BytesIO()
    sf.write(out, wavs[0], sr, format="WAV", subtype="PCM_16")
    return out.getvalue()


def _convert_reference(raw: bytes, suffix: str = ".audio") -> tuple[str, str]:
    with tempfile.NamedTemporaryFile(suffix=suffix or ".audio", delete=False) as src:
        src.write(raw)
        src_path = src.name
    wav_fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(wav_fd)
    try:
        p = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src_path, "-vn", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", wav_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        if p.returncode != 0 or not os.path.exists(wav_path) or os.path.getsize(wav_path) < 1000:
            raise ValueError("Không đọc được file audio reference")
        return src_path, wav_path
    except Exception:
        for pth in (src_path, wav_path):
            try:
                os.unlink(pth)
            except OSError:
                pass
        raise


@app.function(
    gpu="L4",
    image=image,
    timeout=900,
    scaledown_window=300,
    volumes={"/cache": model_cache},
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.responses import HTMLResponse, Response
    from pydantic import BaseModel, Field
    import requests

    api = FastAPI(title="Runner3 Gwen-TTS", version="0.6")

    class TTSRequest(BaseModel):
        text: str = Field(min_length=1, max_length=5000)
        ref_text: str = Field(min_length=1, max_length=3000)
        ref_audio_b64: Optional[str] = None
        ref_audio_url: Optional[str] = None
        language: str = "Vietnamese"

    @api.get("/", response_class=HTMLResponse)
    @api.get("/ui", response_class=HTMLResponse)
    def ui():
        return HTMLResponse(VOICE_CLONE_UI, headers={"Cache-Control": "no-store"})

    @api.get("/health")
    def health():
        return {
            "ok": True,
            "model": MODEL_ID,
            "model_loaded": _model is not None,
            "gpu": _gpu_info(),
            "attention": "sdpa",
            "dtype": "bfloat16",
            "ui": "voice-clone-stable",
            "version": "0.6",
        }

    @api.get("/demo")
    def demo():
        r = requests.get(DEMO_REF_URL, timeout=30)
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(r.content)
            ref_path = f.name
        try:
            audio = _synth(DEMO_TEXT, ref_path, DEMO_REF_TEXT)
            return Response(content=audio, media_type="audio/wav", headers={"Content-Disposition": 'inline; filename="gwen-demo.wav"', "Cache-Control": "no-store"})
        finally:
            try:
                os.unlink(ref_path)
            except OSError:
                pass

    @api.post("/tts-upload")
    async def tts_upload(
        ref_audio: UploadFile = File(...),
        ref_text: str = Form(...),
        text: str = Form(...),
        language: str = Form("Vietnamese"),
    ):
        ref_text = ref_text.strip()
        text = text.strip()
        if not ref_text or len(ref_text) > 3000:
            raise HTTPException(status_code=400, detail="Transcript reference phải từ 1 đến 3000 ký tự")
        if not text or len(text) > 5000:
            raise HTTPException(status_code=400, detail="Văn bản cần đọc phải từ 1 đến 5000 ký tự")
        raw = await ref_audio.read()
        if not raw:
            raise HTTPException(status_code=400, detail="File audio rỗng")
        if len(raw) > 30 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Reference audio quá lớn, tối đa 30 MB")
        suffix = Path(ref_audio.filename or "reference.audio").suffix[:10] or ".audio"
        src_path = wav_path = None
        try:
            src_path, wav_path = _convert_reference(raw, suffix)
            audio = _synth(text, wav_path, ref_text, language)
            return Response(content=audio, media_type="audio/wav", headers={"Content-Disposition": 'inline; filename="gwen-voice-clone.wav"', "Cache-Control": "no-store"})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            for pth in (src_path, wav_path):
                if pth:
                    try:
                        os.unlink(pth)
                    except OSError:
                        pass

    @api.post("/tts")
    def tts(req: TTSRequest):
        if bool(req.ref_audio_b64) == bool(req.ref_audio_url):
            raise HTTPException(status_code=400, detail="Provide exactly one of ref_audio_b64 or ref_audio_url")
        if req.ref_audio_b64:
            try:
                raw = base64.b64decode(req.ref_audio_b64, validate=True)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid ref_audio_b64: {exc}") from exc
            suffix = ".audio"
        else:
            if not req.ref_audio_url.startswith("https://"):
                raise HTTPException(status_code=400, detail="ref_audio_url must use https://")
            r = requests.get(req.ref_audio_url, timeout=30)
            r.raise_for_status()
            raw = r.content
            suffix = Path(req.ref_audio_url.split("?", 1)[0]).suffix[:10] or ".audio"
        if len(raw) > 30 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Reference audio is too large")
        src_path = wav_path = None
        try:
            src_path, wav_path = _convert_reference(raw, suffix)
            audio = _synth(req.text, wav_path, req.ref_text, req.language)
            return Response(content=audio, media_type="audio/wav")
        finally:
            for pth in (src_path, wav_path):
                if pth:
                    try:
                        os.unlink(pth)
                    except OSError:
                        pass

    return api
