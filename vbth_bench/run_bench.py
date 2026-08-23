import json, os, subprocess, time, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

API='https://openrouter.ai/api/v1/chat/completions'
KEY=os.environ['OPENROUTER_API_KEY']
SRC_COMMIT='88af9c6b09ae42c5cd2fd8f93089c5ed42bda1a9'
SRC_PATH='vbth_test/input/ch0009.txt'
raw=subprocess.check_output(['git','show',f'{SRC_COMMIT}:{SRC_PATH}'], text=True)

def between(a,b):
    s=raw.index(a); e=raw.index(b,s)
    return raw[s:e].strip()

case1=between('Rất nhanh, Skinner người bên cạnh tay', 'Skinner ngưng ngưng lại')
case2=between('Marseille thừa cơ hướng miệng', 'Hắn cho dù là cùng cấp với một cái tiểu BOSS')
source='[ĐOẠN A]\n'+case1+'\n\n[ĐOẠN B]\n'+case2
system='''Bạn là biên tập viên tiểu thuyết tiếng Việt. Viết lại văn convert thành tiếng Việt tự nhiên, lạnh, gọn, dễ đọc. Không tóm tắt. Giữ 1:1 mọi sự kiện, quan hệ nhân quả, phủ định/đối lập, con số, %, đơn vị, tên riêng, tên kỹ năng/vật phẩm và điều kiện. Không thêm suy diễn. Dùng “hắn” nhất quán cho nhân vật nam khi phù hợp. Có thể tách/gộp câu nhưng không đổi nghĩa. Trả về duy nhất bản đã biên tập, giữ nhãn [ĐOẠN A]/[ĐOẠN B].'''
models=[
 ('inclusionai/ling-3.0-flash:free','ling3_free'),
 ('google/gemma-4-31b-it:free','gemma4_31b_free'),
 ('nvidia/nemotron-3-super-120b-a12b:free','nemotron3_super_free'),
 ('dots-studio/dots-3-note-preview:free','dots3_note_free'),
 ('poolside/laguna-s-2.1:free','laguna_s_free'),
 ('stealth/ox-alpha','ox_alpha_free'),
 ('inclusionai/ling-3.0-flash','ling3_paid'),
 ('qwen/qwen3.7-flash','qwen37_flash'),
 ('deepseek/deepseek-v4-flash-0731','deepseek_v4_flash'),
 ('stepfun/step-3.5-flash','step35_flash'),
 ('openai/gpt-5.6-luna','gpt56_luna'),
 ('deepseek/deepseek-v4-pro','deepseek_v4_pro'),
 ('google/gemini-3.7-flash','gemini37_flash'),
 ('anthropic/claude-haiku-4.5','claude_haiku45'),
]
low_reason={'qwen/qwen3.7-flash','deepseek/deepseek-v4-flash-0731','deepseek/deepseek-v4-pro','google/gemini-3.7-flash','openai/gpt-5.6-luna'}
outdir=Path('vbth_bench/results_v2'); outdir.mkdir(parents=True, exist_ok=True)

def run(item):
    mid,tag=item
    payload={'model':mid,'messages':[{'role':'system','content':system},{'role':'user','content':source}], 'temperature':0.15,'max_tokens':1800,'usage':{'include':True}}
    if mid in low_reason: payload['reasoning']={'effort':'low'}
    req=urllib.request.Request(API,data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json','HTTP-Referer':'https://github.com/louisalviss/runner-3','X-Title':'VBTH minimal benchmark'})
    t=time.time(); text=''; usage={}; actual=''; err=''; status='error'
    try:
        with urllib.request.urlopen(req,timeout=55) as r: obj=json.loads(r.read())
        text=obj['choices'][0]['message'].get('content') or ''; usage=obj.get('usage') or {}; actual=obj.get('model',''); status='ok'
    except Exception as e: err=str(e)
    nums=['8','30%','1','15%','10']; low=text.lower()
    rec={'tag':tag,'requested_model':mid,'actual_model':actual,'status':status,'elapsed_sec':round(time.time()-t,3),'chars':len(text),'usage':usage,'numeric_checks':{x:(x in text) for x in nums},'polarity_hint':(('không kinh sợ' in low or 'không hề sợ' in low or 'không sợ' in low) and ('mừng' in low or 'vui' in low)),'error':err}
    (outdir/f'{tag}.txt').write_text(text,encoding='utf-8')
    return rec

results=[]
with ThreadPoolExecutor(max_workers=8) as ex:
    futs={ex.submit(run,m):m for m in models}
    for f in as_completed(futs):
        r=f.result(); results.append(r); print(r['tag'],r['status'],r['elapsed_sec'],r['usage'].get('cost'))
order={tag:i for i,(_,tag) in enumerate(models)}; results.sort(key=lambda x:order[x['tag']])
(outdir/'summary.json').write_text(json.dumps({'source_chars':len(source),'models':results},ensure_ascii=False,indent=2),encoding='utf-8')
