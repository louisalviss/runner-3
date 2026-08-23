import json, os, re, subprocess, time, urllib.request
from pathlib import Path
API='https://openrouter.ai/api/v1/chat/completions'; KEY=os.environ['OPENROUTER_API_KEY']
raw=subprocess.check_output(['git','show','88af9c6b09ae42c5cd2fd8f93089c5ed42bda1a9:vbth_test/input/ch0009.txt'],text=True)
system='''Bạn là biên tập viên chính cho tiểu thuyết Vương Bài Tiến Hóa. Viết lại prose convert thành tiếng Việt tự nhiên, lạnh, gọn, dễ đọc. KHÔNG tóm tắt; giữ dữ kiện/cốt truyện 1:1. Có thể tách/gộp/đảo câu trong cùng ý để tự nhiên. Nhịp chiến đấu nhanh, hình ảnh rõ. BẤT BIẾN: giữ đúng mọi con số, %, đơn vị, cấp độ, điều kiện skill, item, tên riêng, phủ định/đối lập và quan hệ nhân quả. Không thêm POV, cảm xúc, giải thích hoặc tình tiết. Không quy đổi đơn vị. Dùng “hắn” nhất quán cho nam khi phù hợp. Không tự đổi tên riêng/skill/item nếu chưa có mapping chắc chắn. Canonical: Mộng Yểm Không Gian; Dấu Ấn Mộng Yểm; Knights of the Round. Loại bỏ văn convert kiểu phảng phất/đang tại/phát giác/bạo lộ/nhưng mà/mười phần. Trả về duy nhất chương hoàn chỉnh đã biên tập, không markdown, không bình luận.'''
p={'model':'openai/gpt-5.6-luna','messages':[{'role':'system','content':system},{'role':'user','content':raw}],'temperature':0.12,'max_tokens':12000,'usage':{'include':True},'reasoning':{'effort':'none'}}
req=urllib.request.Request(API,data=json.dumps(p).encode(),headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json','HTTP-Referer':'https://github.com/louisalviss/runner-3','X-Title':'VBTH Luna final pilot'})
t=time.time()
with urllib.request.urlopen(req,timeout=180) as r: obj=json.loads(r.read())
text=obj['choices'][0]['message'].get('content') or ''
out=Path('vbth_luna_pilot'); (out/'ch0009_luna.txt').write_text(text,encoding='utf-8')
# Numeric literals only: cheap warning signal, not semantic QA.
num=lambda s: re.findall(r'(?<![A-Za-z])\d+(?:\.\d+)?%?',s)
sn=num(raw); on=num(text)
from collections import Counter
missing=list((Counter(sn)-Counter(on)).elements()); extra=list((Counter(on)-Counter(sn)).elements())
summary={'model':obj.get('model'),'source_chars':len(raw),'output_chars':len(text),'char_ratio':round(len(text)/len(raw),4),'elapsed_sec':round(time.time()-t,3),'usage':obj.get('usage') or {},'missing_numeric_literals':missing,'extra_numeric_literals':extra,'checks':{'polarity_not_afraid_and_glad':(('không kinh sợ' in text.lower() or 'không sợ' in text.lower()) and ('mừng' in text.lower() or 'vui' in text.lower())),'has_loạn_vũ':'Loạn Vũ' in text,'has_knights':'Knights of the Round' in text}}
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
