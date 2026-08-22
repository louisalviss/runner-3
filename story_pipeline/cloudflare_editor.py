import json, os, pathlib, urllib.request, urllib.error

MODEL = os.getenv('CF_MODEL', '@cf/qwen/qwen3-30b-a3b-fp8')
ACCOUNT = os.environ['CLOUDFLARE_ACCOUNT_ID']
TOKEN = os.environ['CLOUDFLARE_API_TOKEN']

SYSTEM = '''Bạn là biên tập viên truyện mạng Trung-Việt. Nhiệm vụ: biên tập bản convert thành tiếng Việt tự nhiên, gọn, rõ, giữ nguyên hoàn toàn tình tiết, tên riêng, số liệu, skill, item, cấp độ và logic hệ thống. Không sáng tác, không lược bỏ thông tin, không văn vẻ hóa. Ưu tiên câu Việt tự nhiên. Trả về đúng phần văn bản đã biên tập, không giải thích.'''

STYLE = '''Phong cách chuẩn đã duyệt: câu ngắn vừa phải, nhịp lạnh/thực dụng, giảm Hán-Việt gượng và cấu trúc Trung văn; giữ thuật ngữ hệ thống nhất quán. Ví dụ: “Vết thương của Yagami Iori rõ ràng không thể chữa bằng dược phẩm trong Mộng Yểm Không Gian.”'''

OUT = pathlib.Path(os.environ.get('OUTPUT_DIR','story_pipeline/benchmark_output'))
OUT.mkdir(parents=True, exist_ok=True)


def call_cf(text, glossary=''):
    url = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/{MODEL}'
    prompt = SYSTEM + '\n\n' + STYLE + '\n\nGLOSSARY KHÓA:\n' + glossary + '\n\nVĂN BẢN:\n' + text
    # Keep benchmark output modest; the three samples are short and this avoids model-side output-limit ambiguity.
    payload = {
        'messages': [
            {'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': STYLE + '\n\nGLOSSARY KHÓA:\n' + glossary + '\n\nVĂN BẢN:\n' + text},
        ],
        'temperature': 0.2,
        'max_tokens': 4096,
    }
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            'Authorization': f'Bearer {TOKEN}',
            'Content-Type': 'application/json',
            'User-Agent': 'runner-3-story-editor/1.0',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            body = r.read().decode('utf-8', errors='replace')
            obj = json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        diag = {'type': 'HTTPError', 'status': e.code, 'reason': str(e.reason), 'body': body, 'model': MODEL}
        (OUT/'cloudflare_error.json').write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding='utf-8')
        raise RuntimeError(f'Cloudflare HTTP {e.code}: {body[:1000]}') from e
    except Exception as e:
        diag = {'type': type(e).__name__, 'error': str(e), 'model': MODEL}
        (OUT/'cloudflare_error.json').write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding='utf-8')
        raise

    if not obj.get('success'):
        (OUT/'cloudflare_error.json').write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
        raise RuntimeError(obj)
    res = obj.get('result', {})
    # Workers AI /ai/run commonly returns response; tolerate OpenAI-like result shapes too.
    if isinstance(res, dict):
        if res.get('response'):
            return res['response']
        if res.get('text'):
            return res['text']
        choices = res.get('choices') or []
        if choices:
            msg = choices[0].get('message', {}) if isinstance(choices[0], dict) else {}
            if msg.get('content'):
                return msg['content']
    raise RuntimeError('Cloudflare returned success but no usable text response: ' + json.dumps(res, ensure_ascii=False)[:1000])


def main():
    src = pathlib.Path(os.environ.get('INPUT_DIR','story_pipeline/benchmark_input'))
    out = OUT
    glossary_path = pathlib.Path('story_pipeline/config/cloudflare_glossary.txt')
    glossary = glossary_path.read_text(encoding='utf-8') if glossary_path.exists() else ''
    files = sorted(src.glob('*.txt'))[:3]
    if not files:
        raise SystemExit('No benchmark_input/*.txt files')
    report = []
    for f in files:
        raw = f.read_text(encoding='utf-8').strip()
        edited = call_cf(raw, glossary)
        (out/f.name).write_text(edited.strip()+'\n', encoding='utf-8')
        report.append({'file': f.name, 'raw_chars': len(raw), 'edited_chars': len(edited)})
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__':
    main()
