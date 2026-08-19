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

# Official Gwen-TTS recommended generation config. The A/B test did not show a
# meaningful pronunciation advantage from tighter sampling, so production uses
# the model's recommended preset.
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

VOICE_CLONE_UI = r'''<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Gwen-TTS Voice Clone</title>
<style>
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#111;background:#f5f5f7}
*{box-sizing:border-box}body{margin:0;padding:18px 14px 48px}.wrap{max-width:720px;margin:auto}.card{background:#fff;border-radius:22px;padding:20px;box-shadow:0 8px 28px rgba(0,0,0,.07);margin-bottom:14px}
h1{font-size:28px;line-height:1.1;margin:0 0 7px}.sub{margin:0;color:#666;line-height:1.45}.badges{margin:14px 0 2px}.badge{display:inline-block;background:#eef7ee;border-radius:999px;padding:7px 10px;font-size:13px;margin:0 5px 7px 0}
h2{font-size:18px;margin:0 0 10px}.hint{font-size:13px;color:#777;line-height:1.45;margin:7px 0 12px}.row{display:grid;grid-template-columns:1fr 1fr;gap:9px}.row.one{grid-template-columns:1fr}
button{appearance:none;border:0;border-radius:14px;background:#111;color:#fff;font-size:16px;font-weight:700;padding:13px 12px;min-height:49px}button.alt{background:#ececef;color:#111}button.stop{background:#b42318}button:disabled{opacity:.4}
textarea{width:100%;border:1px solid #d7d7dc;border-radius:14px;padding:13px;font:inherit;font-size:16px;line-height:1.45;resize:vertical;background:#fff;color:#111}label{font-size:14px;font-weight:700;display:block;margin:14px 0 7px}input[type=file]{width:100%;font-size:15px;padding:11px;border:1px dashed #bbb;border-radius:12px;background:#fafafa}
audio{width:100%;margin-top:10px}.status{min-height:22px;font-size:14px;color:#555;line-height:1.4;margin-top:10px}.timer{font-variant-numeric:tabular-nums;font-size:14px;color:#b42318;font-weight:700;margin-top:9px}.privacy{font-size:12px;color:#777;line-height:1.4;margin-top:12px}.links{display:flex;gap:8px;margin-top:12px}.links a{flex:1;text-align:center;text-decoration:none;color:#111;background:#f0f0f2;border-radius:11px;padding:11px;font-size:13px}
</style>
</head>
<body><div class="wrap">
<div class="card">
<h1>Gwen‑TTS Voice Clone</h1>
<p class="sub">Thu 10–20 giây giọng mẫu, nhập đúng câu đã nói, rồi cho model đọc văn bản mới bằng cùng giọng.</p>
<div class="badges"><span class="badge">NVIDIA L4</span><span class="badge">BF16</span><span class="badge">Vietnamese</span><span class="badge">Zero‑shot</span></div>
</div>

<div class="card">
<h2>1 · Giọng mẫu</h2>
<p class="hint">Thu nơi yên tĩnh, nói tự nhiên, không nhạc nền. 10–20 giây là đủ cho lần test đầu.</p>
<div class="row">
<button id="record">● Bắt đầu thu</button>
<button id="stop" class="stop" disabled>■ Dừng</button>
</div>
<div id="timer" class="timer"></div>
<audio id="refPlayer" controls playsinline preload="none"></audio>
<label for="file">Hoặc chọn file audio</label>
<input id="file" type="file" accept="audio/*">
<div id="refStatus" class="status">Chưa có audio reference.</div>
</div>

<div class="card">
<h2>2 · Transcript chính xác</h2>
<p class="hint">Gõ đúng từng chữ bạn vừa nói trong đoạn reference. Sai transcript sẽ làm clone và phát âm kém hơn.</p>
<textarea id="refText" rows="4" placeholder="Ví dụ: Hôm nay trời khá dễ chịu, tôi đang thử một hệ thống tạo giọng nói tiếng Việt."></textarea>
</div>

<div class="card">
<h2>3 · Văn bản cần đọc</h2>
<textarea id="text" rows="6">Buổi sáng, thành phố vẫn còn yên tĩnh. Ánh nắng đầu ngày chiếu qua khung cửa, làm căn phòng sáng lên một cách dịu dàng.</textarea>
<div class="row one" style="margin-top:12px"><button id="generate">Tạo giọng của tôi</button></div>
<div id="genStatus" class="status">Sẵn sàng.</div>
<audio id="resultPlayer" controls playsinline preload="none"></audio>
<p class="privacy">Audio reference được gửi qua HTTPS, chuyển tạm sang WAV trên server và xóa sau khi request kết thúc. Endpoint hiện vẫn là bản thử nghiệm public.</p>
<div class="links"><a href="/health">Health</a><a href="/demo">Demo có sẵn</a></div>
</div>
</div>
<script>
const recBtn=document.getElementById('record'), stopBtn=document.getElementById('stop');
const refPlayer=document.getElementById('refPlayer'), resultPlayer=document.getElementById('resultPlayer');
const refStatus=document.getElementById('refStatus'), genStatus=document.getElementById('genStatus');
const fileInput=document.getElementById('file'), timerEl=document.getElementById('timer');
const refText=document.getElementById('refText'), text=document.getElementById('text'), genBtn=document.getElementById('generate');
let recorder=null, stream=null, chunks=[], referenceBlob=null, referenceName='reference.m4a', referenceUrl=null, resultUrl=null, timer=null, started=0;
function setReference(blob,name){referenceBlob=blob;referenceName=name||'reference.m4a';if(referenceUrl)URL.revokeObjectURL(referenceUrl);referenceUrl=URL.createObjectURL(blob);refPlayer.src=referenceUrl;refStatus.textContent='Reference sẵn sàng · '+(blob.size/1024).toFixed(0)+' KB';}
function chooseMime(){const list=['audio/mp4','audio/webm;codecs=opus','audio/webm'];for(const m of list){if(window.MediaRecorder&&MediaRecorder.isTypeSupported&&MediaRecorder.isTypeSupported(m))return m;}return '';}
function extFor(m){if((m||'').includes('mp4'))return '.m4a';if((m||'').includes('webm'))return '.webm';return '.audio';}
recBtn.addEventListener('click',async()=>{
  try{
    stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false}});
    const mime=chooseMime();recorder=mime?new MediaRecorder(stream,{mimeType:mime}):new MediaRecorder(stream);chunks=[];
    recorder.ondataavailable=e=>{if(e.data&&e.data.size)chunks.push(e.data)};
    recorder.onstop=()=>{const type=recorder.mimeType||mime||'audio/mp4';const blob=new Blob(chunks,{type});setReference(blob,'iphone-reference'+extFor(type));stream.getTracks().forEach(t=>t.stop());clearInterval(timer);timerEl.textContent='Đã thu '+Math.round((Date.now()-started)/1000)+' giây';recBtn.disabled=false;stopBtn.disabled=true;};
    recorder.start();started=Date.now();recBtn.disabled=true;stopBtn.disabled=false;refStatus.textContent='Đang thu…';
    timer=setInterval(()=>{timerEl.textContent='● '+Math.round((Date.now()-started)/1000)+' giây'},500);
  }catch(e){refStatus.textContent='Không mở được microphone: '+e.message+' · Hãy dùng Chọn file audio bên dưới.'}
});
stopBtn.addEventListener('click',()=>{if(recorder&&recorder.state!=='inactive')recorder.stop()});
fileInput.addEventListener('change',()=>{const f=fileInput.files&&fileInput.files[0];if(f)setReference(f,f.name)});
genBtn.addEventListener('click',async()=>{
  const transcript=refText.value.trim(), out=text.value.trim();
  if(!referenceBlob){genStatus.textContent='Cần thu hoặc chọn một file giọng mẫu.';return}
  if(!transcript){genStatus.textContent='Cần nhập transcript chính xác của giọng mẫu.';return}
  if(!out){genStatus.textContent='Cần nhập văn bản cần đọc.';return}
  genBtn.disabled=true;genStatus.textContent='Đang khởi động GPU và clone giọng… Lần đầu có thể chậm.';
  try{
    const fd=new FormData();fd.append('ref_audio',referenceBlob,referenceName);fd.append('ref_text',transcript);fd.append('text',out);fd.append('language','Vietnamese');
    const r=await fetch('/tts-upload',{method:'POST',body:fd});
    if(!r.ok){let msg='HTTP '+r.status;try{const j=await r.json();msg=j.detail||msg}catch(_){ }throw new Error(msg)}
    const b=await r.blob();if(resultUrl)URL.revokeObjectURL(resultUrl);resultUrl=URL.createObjectURL(b);resultPlayer.src=resultUrl;genStatus.textContent='Xong · nhấn Play để nghe giọng clone.';
    try{await resultPlayer.play()}catch(_){ }
  }catch(e){genStatus.textContent='Lỗi: '+e.message}
  finally{genBtn.disabled=false}
});
</script></body></html>'''


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
    """Write arbitrary browser audio, decode with ffmpeg, return (input_path, wav_path)."""
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
            raise ValueError("Không đọc được file audio reference. " + (p.stderr[-300:] if p.stderr else ""))
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

    api = FastAPI(title="Runner3 Gwen-TTS", version="0.5")

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
            "ui": "voice-clone-studio",
            "version": "0.5",
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
            return Response(content=audio, media_type="audio/wav", headers={"Content-Disposition": 'inline; filename="gwen-tts.wav"'})
        finally:
            for pth in (src_path, wav_path):
                if pth:
                    try:
                        os.unlink(pth)
                    except OSError:
                        pass

    return api
