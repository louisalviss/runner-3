import html, re, requests, sys
page="https://appteka.store/apps/a82r263690/download"
t=requests.get(page,timeout=30,headers={"User-Agent":"Mozilla/5.0"}).text
m=re.search(r"href=\"([^\"]+\.apk[^\"]*)",t)
if not m:
    raise SystemExit("APK link not found")
u=html.unescape(m.group(1))
r=requests.get(u,timeout=90,headers={"User-Agent":"Mozilla/5.0"})
r.raise_for_status()
open(sys.argv[1] if len(sys.argv)>1 else "vbook.apk","wb").write(r.content)
print({"bytes":len(r.content),"content_type":r.headers.get("content-type"),"url":u.split("?")[0]})
