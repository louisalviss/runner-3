from pathlib import Path
p=Path("cloudflare/runner3-core/artifact-library-simple-entry.js")
s=p.read_text(encoding="utf-8")
marker="R3_AUTH_PASSTHROUGH_V76='v76'"
if marker in s:
    print("READER_V76_AUTH_PASSTHROUGH=ALREADY_APPLIED")
    raise SystemExit(0)
old='    if (["/artifact-library/login","/artifact-library/logout","/artifact-library/setup-pin","/artifact-library/change-pin","/artifact-library/reset-pin","/artifact-library/magic","/artifact-library/api/magic-link"].includes(p)) return redirectHome();'
new='''    // v76: auth endpoints must reach the canonical hardening/auth app. Redirecting
    // them here caused Create/Reset PIN forms to loop back to the Library root.
    if (["/artifact-library/login","/artifact-library/logout","/artifact-library/setup-pin","/artifact-library/change-pin","/artifact-library/reset-pin","/artifact-library/magic","/artifact-library/api/magic-link"].includes(p)) {
      return (await r3LoadLegacyLibraryAppV57()).fetch(request, env, ctx);
    }'''
if old not in s:
    raise SystemExit("V76_AUTH_REDIRECT_ANCHOR_MISSING")
s=s.replace(old,new,1)
const_anchor="const R3_SINGLE_OWNER_SESSION_V73='v73';"
if const_anchor not in s:
    raise SystemExit("V76_CONST_ANCHOR_MISSING")
s=s.replace(const_anchor,const_anchor+"\nconst R3_AUTH_PASSTHROUGH_V76='v76';",1)
p.write_text(s,encoding="utf-8")
print("READER_V76_AUTH_PASSTHROUGH=PASS")
