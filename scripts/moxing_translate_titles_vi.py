#!/usr/bin/env python3
import argparse, hashlib, json, re
MODEL_ID='Helsinki-NLP/opus-mt-zh-vi'
MODEL_REVISION='e048b2d21aebc6da81d050a4bac4e5b5178bba58'

def sha(s): return hashlib.sha256((s or '').encode()).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--out',required=True);ap.add_argument('--batch-size',type=int,default=24);a=ap.parse_args()
    import torch
    from transformers import AutoTokenizer,AutoModelForSeq2SeqLM
    rows=[json.loads(x) for x in open(a.input,encoding='utf-8') if x.strip()]
    tok=AutoTokenizer.from_pretrained(MODEL_ID,revision=MODEL_REVISION)
    model=AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID,revision=MODEL_REVISION);model.eval();torch.set_num_threads(max(1,min(4,torch.get_num_threads())))
    with open(a.out,'w',encoding='utf-8') as f:
      for start in range(0,len(rows),a.batch_size):
        batch=rows[start:start+a.batch_size];texts=[x['title_zh'] for x in batch]
        enc=tok(texts,return_tensors='pt',padding=True,truncation=True,max_length=160)
        with torch.inference_mode(): gen=model.generate(**enc,max_new_tokens=128,num_beams=4,renormalize_logits=True,early_stopping=True)
        outs=tok.batch_decode(gen,skip_special_tokens=True)
        for x,vi in zip(batch,outs):
          vi=re.sub(r'\s+',' ',vi).strip()
          f.write(json.dumps({'title_zh':x['title_zh'],'title_zh_sha256':sha(x['title_zh']),'title_vi':vi,'title_vi_sha256':sha(vi),'model_id':MODEL_ID,'model_revision':MODEL_REVISION},ensure_ascii=False)+'\n')
    print(json.dumps({'rows':len(rows),'model_id':MODEL_ID,'model_revision':MODEL_REVISION},ensure_ascii=False))
if __name__=='__main__':main()
