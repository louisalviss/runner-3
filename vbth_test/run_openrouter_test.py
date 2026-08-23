import json, os, pathlib, re, sys, time
import requests

ROOT = pathlib.Path(__file__).resolve().parent
INPUT = ROOT / "input"
OUTPUT = ROOT / "output"
OUTPUT.mkdir(parents=True, exist_ok=True)

API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite")
if not API_KEY:
    raise SystemExit("OPENROUTER_API_KEY missing")

STYLE = (ROOT / "style.md").read_text(encoding="utf-8")
SYSTEM = f"""Bạn là biên tập viên tiểu thuyết mạng Trung Quốc sang tiếng Việt.\n\n{STYLE}\n\nYÊU CẦU BẮT BUỘC:\n- Chỉ trả về toàn bộ chương đã biên tập, không giải thích, không markdown fence.\n- Không tóm tắt, không bỏ câu/sự kiện.\n- Giữ nguyên mọi số, %, tên, item, skill, cấp độ, điều kiện và quan hệ nhân quả.\n- Loại bỏ rác nguồn như dòng quảng cáo/offline Tàng Thư Viện.\n- Giữ tiêu đề chương nhưng bỏ marker kỹ thuật ===== CHAPTER .... =====.\n- Tiếng Việt tự nhiên, gọn, lạnh; ưu tiên câu ngắn/vừa.\n"""

num_pat = re.compile(r"(?<!\w)(?:\d+(?:[.,]\d+)?%?|\d+\s*[x×]\s*\d+)(?!\w)")

def nums(s):
    return num_pat.findall(s)

def call(src: str):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Biên tập nguyên chương sau:\n\n" + src},
        ],
        "temperature": 0.15,
        "max_tokens": 30000,
    }
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/louisalviss/runner-3",
            "X-Title": "VBTH editing test",
        },
        json=payload,
        timeout=300,
    )
    if r.status_code != 200:
        raise RuntimeError(f"OpenRouter HTTP {r.status_code}: {r.text[:1000]}")
    data = r.json()
    text = data["choices"][0]["message"]["content"]
    return text.strip() + "\n", data.get("usage", {}), data.get("model", MODEL), data.get("id")

summary = {"requested_model": MODEL, "chapters": []}
for path in sorted(INPUT.glob("ch*.txt")):
    src = path.read_text(encoding="utf-8")
    t0 = time.time()
    edited, usage, actual_model, req_id = call(src)
    elapsed = round(time.time() - t0, 3)
    out = OUTPUT / path.name
    out.write_text(edited, encoding="utf-8")

    src_nums = nums(src)
    out_nums = nums(edited)
    missing_nums = []
    tmp = list(out_nums)
    for x in src_nums:
        if x in tmp:
            tmp.remove(x)
        else:
            missing_nums.append(x)

    extra_nums = []
    tmp2 = list(src_nums)
    for x in out_nums:
        if x in tmp2:
            tmp2.remove(x)
        else:
            extra_nums.append(x)

    rec = {
        "chapter": path.stem,
        "source_chars": len(src),
        "output_chars": len(edited),
        "char_ratio": round(len(edited) / max(len(src), 1), 4),
        "elapsed_sec": elapsed,
        "actual_model": actual_model,
        "request_id": req_id,
        "usage": usage,
        "missing_numeric_tokens": missing_nums,
        "extra_numeric_tokens": extra_nums,
    }
    summary["chapters"].append(rec)
    print(json.dumps(rec, ensure_ascii=False))

(OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
