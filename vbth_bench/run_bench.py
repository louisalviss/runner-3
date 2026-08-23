import json, os, subprocess, time, urllib.request, urllib.error
from pathlib import Path

API='https://openrouter.ai/api/v1/chat/completions'
KEY=os.environ['OPENROUTER_API_KEY']
SRC_COMMIT='88af9c6b09ae42c5cd2fd8f93089c5ed42bda1a9'
SRC_PATH='vbth_test/input/ch0009.txt'

# Reuse source already present in git history; do not add book text again.
raw=subprocess.check_output(['git','show',f'{SRC_COMMIT}:{SRC_PATH}'], text=True)

def between(a,b):
    s=raw.index(a); e=raw.index(b,s)
    return raw[s:e].strip()

# Two tiny hard cases: semantic negation + action prose/numeric skill fidelity.
case1=between('Rất nhanh, Skinner người bên cạnh tay', 'Skinner ngưng ngưng lại')
case2=between('Marseille thừa cơ hướng miệng', 'Hắn cho dù là cùng cấp với một cái tiểu BOSS')
source='[ĐOẠN A]\n'+case1+'\n\n[ĐOẠN B]\n'+case2

system='''Bạn là biên tập viên tiểu thuyết tiếng Việt. Viết lại văn convert thành tiếng Việt tự nhiên, lạnh, gọn, dễ đọc. Không tóm tắt. Giữ 1:1 mọi sự kiện, quan hệ nhân quả, phủ định/đối lập, con số, %, đơn vị, tên riêng, tên kỹ năng/vật phẩm và điều kiện. Không thêm suy diễn. Dùng “hắn” nhất quán cho nhân vật nam khi phù hợp. Có thể tách/gộp câu nhưng không đổi nghĩa. Trả về duy nhất bản đã biên tập, giữ nhãn [ĐOẠN A]/[ĐOẠN B].'''

models=[
 {'id':'inclusionai/ling-3.0-flash:free','tag':'ling3_free'},
 {'id':'google/gemma-4-31b-it:free','tag':'gemma4_31b_free'},
 {'id':'nvidia/nemotron-3-super-120b-a12b:free','tag':'nemotron3_super_free'},
 {'id':'dots-studio/dots-3-note-preview:free','tag':'dots3_note_free'},
 {'id':'poolside/laguna-s-2.1:free','tag':'laguna_s_free'},
 {'id':'stealth/ox-alpha','tag':'ox_alpha_free'},
 {'id':'inclusionai/ling-3.0-flash','tag':'ling3_paid'},
 {'id':'qwen/qwen3.7-flash','tag':'qwen37_flash'},
 {'id':'deepseek/deepseek-v4-flash-0731','tag':'deepseek_v4_flash'},
 {'id':'stepfun/step-3.5-flash','tag':'step35_flash'},
 {'id':'openai/gpt-5.6-luna','tag':'gpt56_luna'},
 {'id':'deepseek/deepseek-v4-pro','tag':'deepseek_v4_pro'},
 {'id':'google/gemini-3.7-flash','tag':'gemini37_flash'},
 {'id':'anthropic/claude-haiku-4.5','tag':'claude_haiku45'},
]

outdir=Path('vbth_bench/results'); outdir.mkdir(parents=True, exist_ok=True)
summary=[]
for m in models:
    payload={
      'model':m['id'],
      'messages':[{'role':'system','content':system},{'role':'user','content':source}],
      'temperature':0.15,
      'max_tokens':1800,
      'usage':{'include':True},
    }
    # Low reasoning where accepted; prose editing does not need deep CoT.
    if m['id'] in {'qwen/qwen3.7-flash','deepseek/deepseek-v4-flash-0731','deepseek/deepseek-v4-pro','google/gemini-3.7-flash','openai/gpt-5.6-luna'}:
        payload['reasoning']={'effort':'low'}
    data=json.dumps(payload).encode()
    req=urllib.request.Request(API,data=data,headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json','HTTP-Referer':'https://github.com/louisalviss/runner-3','X-Title':'VBTH minimal benchmark'})
    start=time.time(); status='error'; text=''; usage={}; actual=''; err=''
    for attempt in range(2):
      try:
        with urllib.request.urlopen(req,timeout=120) as r:
          obj=json.loads(r.read())
        text=obj['choices'][0]['message'].get('content') or ''
        usage=obj.get('usage') or {}; actual=obj.get('model',''); status='ok'; break
      except Exception as e:
        err=str(e)
        if attempt==0: time.sleep(3)
    elapsed=round(time.time()-start,3)
    # cheap deterministic checks, judge quality later in-chat
    nums=['8','30%','1','15%','10']
    numeric={x:(x in text) for x in nums}
    polarity=('không kinh sợ' in text.lower() or 'không hề sợ' in text.lower() or 'không sợ' in text.lower()) and ('mừng' in text.lower() or 'vui' in text.lower())
    rec={'tag':m['tag'],'requested_model':m['id'],'actual_model':actual,'status':status,'elapsed_sec':elapsed,'chars':len(text),'usage':usage,'numeric_checks':numeric,'polarity_hint':polarity,'error':err}
    summary.append(rec)
    (outdir/f"{m['tag']}.txt").write_text(text,encoding='utf-8')
    print(m['tag'],status,elapsed,usage.get('cost'))

(outdir/'summary.json').write_text(json.dumps({'source_chars':len(source),'models':summary},ensure_ascii=False,indent=2),encoding='utf-8')
