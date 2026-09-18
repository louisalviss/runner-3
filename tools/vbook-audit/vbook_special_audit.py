import importlib.util,json,os,sys,base64,time,subprocess
sp=importlib.util.spec_from_file_location("b",os.environ.get("VBOOK_BATCH","/tmp/vbook_batch_plain.py"))
b=importlib.util.module_from_spec(sp); sp.loader.exec_module(b)
META=b.META

def manifest(i):
    return json.load(open(f"/tmp/vbook-audit/roots/{i}/plugin.json",encoding="utf-8"))

def script_name(i,key):
    return (manifest(i).get("script") or {}).get(key)

def call(i,key,args):
    fn=script_name(i,key)
    if not fn:return {"ok":False,"kind":"missing_script"}
    return b.call(i,fn,args,12)

def inner(x): return x.get("inner") or {}
def data(x): return inner(x).get("data")

def valid_b64(s):
    if not isinstance(s,str) or len(s)<128:return (False,0)
    try:
        raw=base64.b64decode(s,validate=False)
        return (len(raw)>=256,len(raw))
    except Exception:return (False,0)

def audit(i):
    r=META[i]; typ=r.get("type"); m=manifest(i); cfg=m.get("config") or {}; out={"i":i,"name":r.get("name"),"type":typ,"source":r.get("source")}
    if typ=="translate":
        lx=call(i,"language",[]); langs=data(lx); out["language"]={"ok":lx.get("ok"),"n":len(langs) if isinstance(langs,list) else 0,"kind":lx.get("kind")}
        if not lx.get("ok") or not isinstance(langs,list) or len(langs)<2: out["class"]="SPECIAL_LANGUAGE_FAIL"; return out
        tx=call(i,"translate",["Hello world","en","vi"]); td=data(tx); out["translate"]={"ok":tx.get("ok"),"kind":tx.get("kind"),"text":str(td)[:160],"message":str(inner(tx).get("message") or "")[:180]}
        out["class"]="PASS_SPECIAL" if tx.get("ok") and isinstance(td,str) and len(td.strip())>=2 and td.strip().lower()!="hello world" else "SPECIAL_TRANSLATE_FAIL"
        return out
    if typ=="tts":
        vx=call(i,"voice",[]); voices=data(vx); out["voice"]={"ok":vx.get("ok"),"n":len(voices) if isinstance(voices,list) else 0,"kind":vx.get("kind")}
        if not vx.get("ok") or not isinstance(voices,list) or not voices: out["class"]="SPECIAL_VOICE_FAIL"; return out
        voice=next((v for v in voices if isinstance(v,dict) and str(v.get("language","")).lower().startswith("vi")),voices[0])
        vid=voice.get("id") if isinstance(voice,dict) else str(voice)
        if cfg.get("api_keys") and not cfg.get("required_api_key"):
            out["class"]="CONFIG_REQUIRED"; out["voice_id"]=vid; return out
        tx=call(i,"tts",["Xin chào, đây là bài kiểm tra âm thanh.",str(vid)]); td=data(tx); ok,n=valid_b64(td); msg=str(inner(tx).get("message") or "")
        out["tts"]={"ok":tx.get("ok"),"kind":tx.get("kind"),"decoded_bytes":n,"message":msg[:220]}
        low=msg.lower()
        if ok and tx.get("ok"): out["class"]="PASS_SPECIAL"
        elif any(k in low for k in ["đăng nhập","login","sessionid"]): out["class"]="AUTH_REQUIRED"
        else: out["class"]="SPECIAL_TTS_FAIL"
        return out
    if typ=="ai":
        out["class"]="CONFIG_REQUIRED" if cfg.get("required_api_key") else "SPECIAL_UNTESTED"
        return out
    out["class"]="SPECIAL_UNSUPPORTED"; return out

def reset_engine():
    adb=os.environ.get("ADB","adb")
    try:
        subprocess.run([adb,"shell","am","force-stop","com.vbook.app"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        time.sleep(0.5)
        subprocess.run([adb,"shell","am","startservice","-n","com.vbook.app/.test.ExtensionTestService"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        time.sleep(1.0)
    except Exception:
        pass

ids=[0,27,28,30,32,33,34,38,96]
rows=[]
for i in ids:
    t=time.time()
    try:r=audit(i)
    except Exception as e:r={"i":i,"name":META[i].get("name"),"type":META[i].get("type"),"class":"SPECIAL_ERROR","err":repr(e)}
    r["wall"]=round(time.time()-t,2); rows.append(r); print(json.dumps(r,ensure_ascii=False),flush=True)
    if "transport" in json.dumps(r,ensure_ascii=False).lower(): reset_engine()
json.dump(rows,open("/tmp/vbook-audit/special-results.json","w",encoding="utf-8"),ensure_ascii=False,indent=2)
