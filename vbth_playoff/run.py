import json, os, subprocess, time, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
API='https://openrouter.ai/api/v1/chat/completions'; KEY=os.environ['OPENROUTER_API_KEY']
raw=subprocess.check_output(['git','show','88af9c6b09ae42c5cd2fd8f93089c5ed42bda1a9:vbth_test/input/ch0009.txt'],text=True)
# Long enough to expose long-form drift, but cheaper than a full chapter.
cut=9000
chunk=raw[:cut]
if '\n\n' in chunk: chunk=chunk[:chunk.rfind('\n\n')]
system='''Biên tập văn convert thành tiếng Việt tự nhiên, lạnh, gọn. Không tóm tắt. Giữ 1:1 tất cả sự kiện, phủ định/đối lập, nhân quả, con số, %, đơn vị, tên riêng, chức danh, binh chủng, vũ khí, kỹ năng, vật phẩm. CẤM đổi loại danh từ: búa vẫn là búa, rìu vẫn là rìu, côn vẫn là côn; không tự dịch/đổi tên skill/item/chức danh. Dùng hắn nhất quán cho nam. Không thêm suy diễn. Canonical: Kỵ Sĩ Trừng Phạt Skinner; Dấu Ấn Mộng Yểm; Mộng Yểm Không Gian; Knights of the Round. Trả duy nhất văn đã biên tập.'''
models=[('deepseek/deepseek-v4-flash-0731','deepseek_v4_flash'),('google/gemini-3.7-flash','gemini37_flash')]
out=Path('vbth_playoff');
def run(x):
 mid,tag=x; p={'model':mid,'messages':[{'role':'system','content':system},{'role':'user','content':chunk}],'temperature':0.1,'max_tokens':7000,'usage':{'include':True},'reasoning':{'effort':'none'}}
 req=urllib.request.Request(API,data=json.dumps(p).encode(),headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json','HTTP-Referer':'https://github.com/louisalviss/runner-3','X-Title':'VBTH extended playoff'})
 t=time.time(); text=''; u={}; err=''; actual=''; status='error'
 try:
  with urllib.request.urlopen(req,timeout=160) as r: obj=json.loads(r.read())
  text=obj['choices'][0]['message'].get('content') or ''; u=obj.get('usage') or {}; actual=obj.get('model',''); status='ok'
 except Exception as e: err=str(e)
 (out/f'{tag}.txt').write_text(text,encoding='utf-8')
 low=text.lower()
 return {'tag':tag,'status':status,'actual_model':actual,'source_chars':len(chunk),'output_chars':len(text),'ratio':round(len(text)/len(chunk),4) if chunk else 0,'elapsed_sec':round(time.time()-t,3),'usage':u,'checks':{'canonical_skinner':'Kỵ Sĩ Trừng Phạt Skinner' in text,'has_bua':'búa' in low,'has_riu':'rìu' in low,'polarity':(('không kinh sợ' in low or 'không sợ' in low) and ('mừng' in low or 'vui' in low)),'n8':'8' in text,'n30':'30%' in text,'n15':'15%' in text,'n10':'10' in text},'error':err}
with ThreadPoolExecutor(max_workers=2) as ex: res=[f.result() for f in as_completed([ex.submit(run,m) for m in models])]
(out/'summary.json').write_text(json.dumps({'models':res},ensure_ascii=False,indent=2),encoding='utf-8')
