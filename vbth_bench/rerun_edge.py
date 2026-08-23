import json, os, subprocess, time, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
API='https://openrouter.ai/api/v1/chat/completions'; KEY=os.environ['OPENROUTER_API_KEY']
raw=subprocess.check_output(['git','show','88af9c6b09ae42c5cd2fd8f93089c5ed42bda1a9:vbth_test/input/ch0009.txt'],text=True)
def between(a,b):
 s=raw.index(a); e=raw.index(b,s); return raw[s:e].strip()
source='[ĐOẠN A]\n'+between('Rất nhanh, Skinner người bên cạnh tay','Skinner ngưng ngưng lại')+'\n\n[ĐOẠN B]\n'+between('Marseille thừa cơ hướng miệng','Hắn cho dù là cùng cấp với một cái tiểu BOSS')
system='''Bạn là biên tập viên tiểu thuyết tiếng Việt. Viết lại văn convert thành tiếng Việt tự nhiên, lạnh, gọn, dễ đọc. Không tóm tắt. Giữ 1:1 mọi sự kiện, quan hệ nhân quả, phủ định/đối lập, con số, %, đơn vị, tên riêng, tên kỹ năng/vật phẩm và điều kiện. Không thêm suy diễn. Dùng “hắn” nhất quán cho nhân vật nam khi phù hợp. Có thể tách/gộp câu nhưng không đổi nghĩa. Trả về duy nhất bản đã biên tập, giữ nhãn [ĐOẠN A]/[ĐOẠN B].'''
models=[('inclusionai/ling-3.0-flash:free','ling3_free_retry'),('google/gemma-4-31b-it:free','gemma4_31b_free_retry'),('inclusionai/ling-3.0-flash','ling3_paid_none'),('qwen/qwen3.7-flash','qwen37_flash_none')]
out=Path('vbth_bench/results_v3'); out.mkdir(parents=True,exist_ok=True)
def run(x):
 mid,tag=x; p={'model':mid,'messages':[{'role':'system','content':system},{'role':'user','content':source}],'temperature':0.15,'max_tokens':1800,'usage':{'include':True}}
 if mid in {'inclusionai/ling-3.0-flash','qwen/qwen3.7-flash'}: p['reasoning']={'effort':'none'}
 req=urllib.request.Request(API,data=json.dumps(p).encode(),headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json','HTTP-Referer':'https://github.com/louisalviss/runner-3','X-Title':'VBTH edge rerun'})
 t=time.time(); text=''; u={}; actual=''; err=''; status='error'
 try:
  with urllib.request.urlopen(req,timeout=55) as r: obj=json.loads(r.read())
  text=obj['choices'][0]['message'].get('content') or ''; u=obj.get('usage') or {}; actual=obj.get('model',''); status='ok'
 except Exception as e: err=str(e)
 (out/f'{tag}.txt').write_text(text,encoding='utf-8')
 low=text.lower(); nums=['8','30%','1','15%','10']
 return {'tag':tag,'requested_model':mid,'actual_model':actual,'status':status,'elapsed_sec':round(time.time()-t,3),'chars':len(text),'usage':u,'numeric_checks':{z:(z in text) for z in nums},'polarity_hint':(('không kinh sợ' in low or 'không hề sợ' in low or 'không sợ' in low) and ('mừng' in low or 'vui' in low)),'error':err}
with ThreadPoolExecutor(max_workers=4) as ex: res=[f.result() for f in as_completed([ex.submit(run,m) for m in models])]
order={t:i for i,(_,t) in enumerate(models)}; res.sort(key=lambda r:order[r['tag']])
(out/'summary.json').write_text(json.dumps({'models':res},ensure_ascii=False,indent=2),encoding='utf-8')
