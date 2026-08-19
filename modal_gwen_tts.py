import base64
import io
import os
import subprocess
import tempfile
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

# Official Gwen-TTS recommended generation config.
GENERATION_CONFIG_NATURAL = dict(
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

# Experimental pronunciation-focused preset. Same model/reference; only sampling
# is tightened so A/B can show whether randomness is causing slurred phonemes.
GENERATION_CONFIG_CLEAR = dict(
    temperature=0.15,
    top_k=15,
    top_p=0.85,
    max_new_tokens=4096,
    repetition_penalty=2.0,
    subtalker_do_sample=True,
    subtalker_temperature=0.05,
    subtalker_top_k=15,
    subtalker_top_p=0.9,
)

GENERATION_CONFIGS = {
    "natural": GENERATION_CONFIG_NATURAL,
    "clear": GENERATION_CONFIG_CLEAR,
}

DEMO_REF_URL = "https://raw.githubusercontent.com/ggroup-ai-lab/gwen-tts/main/data/ref_audio/khanh_toan.wav"
DEMO_REF_TEXT = "việt nam đang kiêu hãnh bước vào kỷ nguyên vươn mình rực rỡ với khát vọng mãnh liệt, trí tuệ đổi mới, tinh thần đoàn kết."
# Pure Vietnamese test sentence: no English acronyms, GPU names or digits.
DEMO_TEXT = "Buổi sáng, thành phố vẫn còn yên tĩnh. Ánh nắng đầu ngày chiếu qua khung cửa, làm căn phòng sáng lên một cách dịu dàng."

DEMO_UI = r'''<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Runner3 Gwen-TTS</title>
<style>
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#111;background:#f6f6f7}
*{box-sizing:border-box} body{margin:0;padding:24px 18px 48px}.wrap{max-width:680px;margin:0 auto}.card{background:#fff;border-radius:22px;padding:22px;box-shadow:0 8px 30px rgba(0,0,0,.08)}
h1{font-size:28px;margin:0 0 8px}.sub{color:#666;line-height:1.45;margin:0 0 18px}.badge{display:inline-block;background:#eef7ee;border-radius:999px;padding:7px 10px;font-size:13px;margin:0 6px 10px 0}
.buttons{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:8px}button{appearance:none;border:0;border-radius:14px;background:#111;color:#fff;font-size:16px;font-weight:700;padding:14px 12px;min-height:52px}button.secondary{background:#e9e9ec;color:#111}button:disabled{opacity:.45}
#status{min-height:24px;margin:14px 0;color:#555;line-height:1.4}audio{width:100%;margin-top:8px}.links{display:flex;gap:10px;margin-top:18px}.links a{flex:1;text-align:center;text-decoration:none;color:#111;background:#f0f0f2;border-radius:12px;padding:12px;font-size:14px}
.test{font-size:15px;line-height:1.55;background:#f7f7f8;border-radius:14px;padding:14px;margin:12px 0 16px}.small{font-size:13px;color:#777;margin-top:16px;line-height:1.45}
</style>
</head>
<body><div class="wrap"><div class="card">
<h1>Gwen‑TTS Vietnamese A/B</h1>
<p class="sub">Cùng một giọng mẫu và cùng một câu. Chỉ khác cách sampling để kiểm tra nguyên nhân phát âm ngọng.</p>
<div><span class="badge">NVIDIA L4</span><span class="badge">BF16</span><span class="badge">24 kHz WAV</span></div>
<div class="test">“Buổi sáng, thành phố vẫn còn yên tĩnh. Ánh nắng đầu ngày chiếu qua khung cửa, làm căn phòng sáng lên một cách dịu dàng.”</div>
<div class="buttons">
  <button class="secondary" data-mode="natural">A · Natural</button>
  <button data-mode="clear">B · Clear Vietnamese</button>
</div>
<div id="status">Nghe A rồi B. Nếu B rõ hơn, ta dùng Clear cho audiobook.</div>
<audio id="player" controls playsinline preload="none"></audio>
<div class="links"><a href="/health">Health</a><a href="/demo?mode=clear">Clear WAV</a></div>
<div class="small">Natural dùng config chính thức của Gwen-TTS. Clear giảm độ ngẫu nhiên để ưu tiên phát âm ổn định hơn. Đây là A/B thử nghiệm, không mặc định coi Clear tốt hơn.</div>
</div></div>
<script>
const buttons=[...document.querySelectorAll('button[data-mode]')], status=document.getElementById('status'), player=document.getElementById('player');
let currentUrl=null;
async function run(mode){
  buttons.forEach(b=>b.disabled=true);
  status.textContent=(mode==='clear'?'B · Clear':'A · Natural')+' — đang khởi động GPU / sinh giọng…';
  try{
    const r=await fetch('/demo?mode='+encodeURIComponent(mode)+'&ts='+Date.now(),{cache:'no-store'});
    if(!r.ok) throw new Error('HTTP '+r.status);
    const b=await r.blob();
    if(currentUrl) URL.revokeObjectURL(currentUrl);
    currentUrl=URL.createObjectURL(b); player.src=currentUrl;
    status.textContent=(mode==='clear'?'B · Clear':'A · Natural')+' — xong.';
    try{await player.play()}catch(e){status.textContent+=' Nhấn Play để nghe.'}
  }catch(e){status.textContent='Lỗi: '+e.message+' — thử lại sau vài giây.'}
  finally{buttons.forEach(b=>b.disabled=false)}
}
buttons.forEach(b=>b.addEventListener('click',()=>run(b.dataset.mode)));
</script></body></html>'''


def _gpu_info() -> str:
    return subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ],
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


def _generation_config(mode: str) -> dict:
    mode = (mode or "clear").strip().lower()
    if mode not in GENERATION_CONFIGS:
        raise ValueError("mode must be 'natural' or 'clear'")
    return GENERATION_CONFIGS[mode]


def _synth(
    text: str,
    ref_audio_path: str,
    ref_text: str,
    language: str = "Vietnamese",
    mode: str = "clear",
) -> bytes:
    import soundfile as sf

    model = _load_model()
    wavs, sr = model.generate_voice_clone(
        text=text,
        language=language,
        ref_audio=ref_audio_path,
        ref_text=ref_text,
        **_generation_config(mode),
    )
    out = io.BytesIO()
    sf.write(out, wavs[0], sr, format="WAV", subtype="PCM_16")
    return out.getvalue()


@app.function(
    gpu="L4",
    image=image,
    timeout=900,
    scaledown_window=300,
    volumes={"/cache": model_cache},
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import HTMLResponse, Response
    from pydantic import BaseModel, Field
    import requests

    api = FastAPI(title="Runner3 Gwen-TTS", version="0.4")

    class TTSRequest(BaseModel):
        text: str = Field(min_length=1, max_length=5000)
        ref_text: str = Field(min_length=1, max_length=3000)
        ref_audio_b64: Optional[str] = None
        ref_audio_url: Optional[str] = None
        language: str = "Vietnamese"
        mode: str = "clear"

    @api.get("/", response_class=HTMLResponse)
    @api.get("/ui", response_class=HTMLResponse)
    def ui():
        return HTMLResponse(DEMO_UI, headers={"Cache-Control": "no-store"})

    @api.get("/health")
    def health():
        return {
            "ok": True,
            "model": MODEL_ID,
            "model_loaded": _model is not None,
            "gpu": _gpu_info(),
            "attention": "sdpa",
            "dtype": "bfloat16",
            "modes": list(GENERATION_CONFIGS),
            "default_mode": "clear",
        }

    @api.get("/demo")
    def demo(mode: str = Query(default="clear", pattern="^(natural|clear)$")):
        r = requests.get(DEMO_REF_URL, timeout=30)
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(r.content)
            ref_path = f.name
        try:
            audio = _synth(DEMO_TEXT, ref_path, DEMO_REF_TEXT, mode=mode)
            return Response(
                content=audio,
                media_type="audio/wav",
                headers={
                    "Content-Disposition": f'inline; filename="gwen-demo-{mode}.wav"',
                    "Cache-Control": "no-store",
                    "X-Gwen-Mode": mode,
                },
            )
        finally:
            try:
                os.unlink(ref_path)
            except OSError:
                pass

    @api.post("/tts")
    def tts(req: TTSRequest):
        try:
            _generation_config(req.mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if bool(req.ref_audio_b64) == bool(req.ref_audio_url):
            raise HTTPException(status_code=400, detail="Provide exactly one of ref_audio_b64 or ref_audio_url")

        if req.ref_audio_b64:
            try:
                raw = base64.b64decode(req.ref_audio_b64, validate=True)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid ref_audio_b64: {exc}") from exc
        else:
            if not req.ref_audio_url.startswith("https://"):
                raise HTTPException(status_code=400, detail="ref_audio_url must use https://")
            r = requests.get(req.ref_audio_url, timeout=30)
            r.raise_for_status()
            raw = r.content

        if len(raw) > 30 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Reference audio is too large")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(raw)
            ref_path = f.name
        try:
            audio = _synth(req.text, ref_path, req.ref_text, req.language, req.mode)
            return Response(
                content=audio,
                media_type="audio/wav",
                headers={
                    "Content-Disposition": 'inline; filename="gwen-tts.wav"',
                    "X-Gwen-Mode": req.mode,
                },
            )
        finally:
            try:
                os.unlink(ref_path)
            except OSError:
                pass

    return api
