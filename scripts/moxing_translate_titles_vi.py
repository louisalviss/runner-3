#!/usr/bin/env python3
import argparse,hashlib,json,re
from pathlib import Path
MODEL_ID='DanVP/MoxhiMT-60'
MODEL_REVISION='3ae60c790cf21deebeab8e1a82f4024fbdc1fc87'
MODEL_LICENSE='Apache-2.0'
RUNTIME='CTranslate2 INT8'

def sha(s):return hashlib.sha256((s or '').encode()).hexdigest()

def load_runtime():
    import ctranslate2
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer
    root=Path(snapshot_download(MODEL_ID,revision=MODEL_REVISION,allow_patterns=['config.json','generation_config.json','source.spm','target.spm','vocab.json','tokenizer_config.json','special_tokens_map.json','ct2-int8/*']))
    tok=AutoTokenizer.from_pretrained(root)
    tr=ctranslate2.Translator(str(root/'ct2-int8'),device='cpu',compute_type='int8',inter_threads=1,intra_threads=4)
    return tok,tr

def translate_batch(tok,tr,texts):
    batches=[]
    for t in texts:
        ids=tok(t,truncation=True,max_length=192).input_ids
        batches.append(tok.convert_ids_to_tokens(ids))
    res=tr.translate_batch(batches,beam_size=4,max_decoding_length=160)
    out=[]
    for r in res:
        ids=tok.convert_tokens_to_ids(r.hypotheses[0]);out.append(tok.decode(ids,skip_special_tokens=True))
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--out',required=True);ap.add_argument('--batch-size',type=int,default=32);a=ap.parse_args()
    rows=[json.loads(x) for x in open(a.input,encoding='utf-8') if x.strip()]
    tok,tr=load_runtime()
    with open(a.out,'w',encoding='utf-8') as f:
      for start in range(0,len(rows),a.batch_size):
        batch=rows[start:start+a.batch_size];outs=translate_batch(tok,tr,[x['title_zh'] for x in batch])
        for x,vi in zip(batch,outs):
          vi=re.sub(r'\s+',' ',vi).strip()
          f.write(json.dumps({'title_zh':x['title_zh'],'title_zh_sha256':sha(x['title_zh']),'title_vi':vi,'title_vi_sha256':sha(vi),'model_id':MODEL_ID,'model_revision':MODEL_REVISION,'model_license':MODEL_LICENSE,'runtime':RUNTIME},ensure_ascii=False)+'\n')
    print(json.dumps({'rows':len(rows),'model_id':MODEL_ID,'model_revision':MODEL_REVISION,'runtime':RUNTIME},ensure_ascii=False))
if __name__=='__main__':main()
