import json, os, pathlib, urllib.request

MODEL = os.getenv('CF_MODEL', '@cf/qwen/qwen3-30b-a3b-fp8')
ACCOUNT = os.environ['CLOUDFLARE_ACCOUNT_ID']
TOKEN = os.environ['CLOUDFLARE_API_TOKEN']

SYSTEM = '''Bạn là biên tập viên truyện mạng Trung-Việt. Nhiệm vụ: biên tập bản convert thành tiếng Việt tự nhiên, gọn, rõ, giữ nguyên hoàn toàn tình tiết, tên riêng, số liệu, skill, item, cấp độ và logic hệ thống. Không sáng tác, không lược bỏ thông tin, không văn vẻ hóa. Ưu tiên câu Việt tự nhiên. Trả về đúng phần văn bản đã biên tập, không giải thích.'''

STYLE = '''Phong cách chuẩn đã duyệt: câu ngắn vừa phải, nhịp lạnh/thực dụng, giảm Hán-Việt gượng và cấu trúc Trung văn; giữ thuật ngữ hệ thống nhất quán. Ví dụ: “Vết thương của Yagami Iori rõ ràng không thể chữa bằng dược phẩm trong Mộng Yểm Không Gian.”'''

def call_cf(text, glossary=''):
    url = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/{MODEL}'
    prompt = SYSTEM + '\n\n' + STYLE + '\n\nGLOSSARY KHÓA:\n' + glossary + '\n\nVĂN BẢN:\n' + text
    data = json.dumps({'messages':[{'role':'user','content':prompt}], 'temperature':0.2, 'max_tokens':8192}).encode()
    req = urllib.request.Request(url, data=data, headers={'Authorization':f'Bearer {TOKEN}','Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=180) as r:
        obj=json.loads(r.read().decode())
    if not obj.get('success'):
        raise RuntimeError(obj)
    res=obj['result']
    return res.get('response') or res.get('text') or json.dumps(res, ensure_ascii=False)

def main():
    src=pathlib.Path(os.environ.get('INPUT_DIR','story_pipeline/benchmark_input'))
    out=pathlib.Path(os.environ.get('OUTPUT_DIR','story_pipeline/benchmark_output'))
    out.mkdir(parents=True, exist_ok=True)
    glossary_path=pathlib.Path('story_pipeline/config/cloudflare_glossary.txt')
    glossary=glossary_path.read_text(encoding='utf-8') if glossary_path.exists() else ''
    files=sorted(src.glob('*.txt'))[:3]
    if not files:
        raise SystemExit('No benchmark_input/*.txt files')
    report=[]
    for f in files:
        raw=f.read_text(encoding='utf-8').strip()
        edited=call_cf(raw, glossary)
        (out/f.name).write_text(edited.strip()+'\n', encoding='utf-8')
        report.append({'file':f.name,'raw_chars':len(raw),'edited_chars':len(edited)})
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))

if __name__=='__main__': main()
