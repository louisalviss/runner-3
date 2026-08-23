import json, os, pathlib, urllib.request, urllib.error

MODEL = os.getenv('CF_MODEL', '@cf/openai/gpt-oss-120b')
ACCOUNT = os.environ['CLOUDFLARE_ACCOUNT_ID']
TOKEN = os.environ['CLOUDFLARE_API_TOKEN']

SYSTEM = '''Bạn là biên tập viên tiếng Việt cấp xuất bản cho truyện mạng Trung Quốc đã qua máy convert.

Nhiệm vụ là VIẾT LẠI SÂU thành tiếng Việt tự nhiên, không phải chỉ sửa vài từ. Được phép tách/gộp/đảo câu trong cùng đoạn để loại bỏ hoàn toàn cú pháp Trung văn, nhưng phải giữ nguyên 100% nội dung thực tế.

QUY TẮC BẮT BUỘC:
- Giữ nguyên tình tiết, quan hệ nhân quả, chủ thể hành động, tên riêng, số liệu, tỷ lệ, cấp độ, skill, item, hiệu ứng, điều kiện và logic hệ thống.
- Không thêm suy nghĩ, cảm xúc, miêu tả, giải thích hoặc thông tin không có trong nguồn.
- Không lược bỏ chi tiết.
- Thuật ngữ khóa phải giữ đúng như glossary.
- Ưu tiên câu Việt gọn, rõ, lạnh và thực dụng; combat phải nhanh, dễ hình dung.
- Loại bỏ các cấu trúc convert kiểu: “mười phần”, “sử dụng về sau”, “kỹ năng phóng thích”, “đối hắn vô hiệu”, “không gian trong đó dược vật”, “hạ thấp 20%”, “chói tai ... thanh âm”.
- Nếu câu nguồn gượng, hãy hiểu nghĩa rồi diễn đạt lại bằng tiếng Việt tự nhiên; tuyệt đối không bám thứ tự từ của bản convert.
- Chỉ trả về văn bản đã biên tập. Không mở đầu, không giải thích, không nhận xét.'''

STYLE = '''CHUẨN PHONG CÁCH ĐÃ DUYỆT:

Ví dụ 1
Convert: “Yagami Iori thương thế hiển nhiên là không thể dùng không gian trong đó dược vật tiến hành điều trị, vì nghiệm chứng điểm này, Phương Lâm trực tiếp thử qua cầm bình tím lớn đối với hắn...”
Biên tập đúng: “Vết thương của Yagami Iori rõ ràng không thể chữa bằng dược phẩm trong Mộng Yểm Không Gian. Để xác nhận, Phương Lâm đã thử dùng một bình thuốc tím cỡ lớn lên hắn. Kết quả rất rõ ràng: vật phẩm vô hiệu.”

Ví dụ 2
Convert: “Mắt thấy ba cỗ trước tụ sau tán chói mắt ánh sáng từ trên xuống dưới lao thẳng tới mà xuống, giống như một cái đảo ngược cái phễu...”
Biên tập đúng: “Ba luồng sáng chói mắt từ trên cao bổ xuống. Chúng tách ra rồi lại hội tụ ngay trên đầu Số 11, tạo thành một cơn lốc băng xanh nhạt khổng lồ.”

Mục tiêu: đọc như truyện Việt được biên tập tử tế, không còn mùi convert, nhưng dữ kiện phải khớp nguồn 1:1.'''

OUT = pathlib.Path(os.environ.get('OUTPUT_DIR','story_pipeline/benchmark_output'))
OUT.mkdir(parents=True, exist_ok=True)


def call_cf(text, glossary=''):
    url = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/{MODEL}'
    payload = {
        'messages': [
            {'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': STYLE + '\n\nGLOSSARY KHÓA:\n' + glossary + '\n\nVĂN BẢN CẦN BIÊN TẬP:\n' + text},
        ],
        'temperature': 0.15,
        'max_tokens': 4096,
    }
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            'Authorization': f'Bearer {TOKEN}',
            'Content-Type': 'application/json',
            'User-Agent': 'runner-3-story-editor/1.1',
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
    err = out / 'cloudflare_error.json'
    if err.exists():
        err.unlink()
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
        report.append({'file': f.name, 'model': MODEL, 'raw_chars': len(raw), 'edited_chars': len(edited)})
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__':
    main()
