from pathlib import Path
ROOT=Path('cloudflare/runner3-core')
PIN=ROOT/'artifact-library-pin-v2-entry.js'
HARD=ROOT/'artifact-library-hardening-entry.js'
SIMPLE=ROOT/'artifact-library-simple-entry.js'
V7=ROOT/'artifact-library-reader-v7-github-audio-entry.js'

pin=PIN.read_text(encoding='utf-8')
hard=HARD.read_text(encoding='utf-8')
simple=SIMPLE.read_text(encoding='utf-8')
v7=V7.read_text(encoding='utf-8')

# Run after v87: all owner sessions are already 10-year rolling sessions.
def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise SystemExit(label)
    return text.replace(old,new,1)

pin=replace_once(pin,
'''function cookie(value, maxAge = REMEMBER_SECONDS) {\n  return `${LIBRARY_COOKIE}=${value}; Path=/artifact-library; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Strict`;\n}\n''',
'''function cookie(value, maxAge = REMEMBER_SECONDS) {\n  const expires = new Date(Date.now() + Math.max(0, Number(maxAge) || 0) * 1000).toUTCString();\n  return `${LIBRARY_COOKIE}=${value}; Path=/artifact-library; Max-Age=${maxAge}; Expires=${expires}; HttpOnly; Secure; SameSite=Lax`;\n}\n''','V91_PIN_COOKIE_ANCHOR')

hard=replace_once(hard,
'''function libraryCookie(value, maxAge = REMEMBER_SECONDS) {\n  return `${LIBRARY_COOKIE}=${value}; Path=/artifact-library; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Strict`;\n}\n''',
'''function libraryCookie(value, maxAge = REMEMBER_SECONDS) {\n  const expires = new Date(Date.now() + Math.max(0, Number(maxAge) || 0) * 1000).toUTCString();\n  return `${LIBRARY_COOKIE}=${value}; Path=/artifact-library; Max-Age=${maxAge}; Expires=${expires}; HttpOnly; Secure; SameSite=Lax`;\n}\n''','V91_HARD_COOKIE_ANCHOR')

simple=replace_once(simple,
'''function r3SingleOwnerCookieV73(value) {\n  return `${LIBRARY_COOKIE}=${value}; Path=/artifact-library; Max-Age=${R3_SINGLE_OWNER_SESSION_SECONDS_V73}; HttpOnly; Secure; SameSite=Strict`;\n}\n''',
'''function r3SingleOwnerCookieV73(value) {\n  const maxAge=R3_SINGLE_OWNER_SESSION_SECONDS_V73;\n  const expires=new Date(Date.now()+maxAge*1000).toUTCString();\n  return `${LIBRARY_COOKIE}=${value}; Path=/artifact-library; Max-Age=${maxAge}; Expires=${expires}; HttpOnly; Secure; SameSite=Lax`;\n}\n''','V91_SIMPLE_COOKIE_ANCHOR')

v7=replace_once(v7,
'''function r3PersistentOwnerCookieV87(value){\n  return `${R3_LIBRARY_COOKIE_V75}=${value}; Path=/artifact-library; Max-Age=${R3_READER_PERSISTENT_SESSION_SECONDS_V87}; HttpOnly; Secure; SameSite=Strict`;\n}\n''',
'''function r3PersistentOwnerCookieV87(value){\n  const maxAge=R3_READER_PERSISTENT_SESSION_SECONDS_V87;\n  const expires=new Date(Date.now()+maxAge*1000).toUTCString();\n  return `${R3_LIBRARY_COOKIE_V75}=${value}; Path=/artifact-library; Max-Age=${maxAge}; Expires=${expires}; HttpOnly; Secure; SameSite=Lax`;\n}\n''','V91_V7_COOKIE_ANCHOR')

old_form='''form: `<form method="post" action="/artifact-library/login"><div class="field"><label for="pin">6-digit Library PIN</label><input class="input pin" id="pin" name="pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="current-password" required autofocus></div><button class="button" type="submit">Open Library</button></form>`,'''
new_form='''form: `<form id="r3OwnerLoginV91" method="post" action="/artifact-library/login"><input type="text" name="username" value="ebook-owner" autocomplete="username" tabindex="-1" aria-hidden="true" style="position:absolute;left:-10000px;width:1px;height:1px;opacity:0"><div class="field"><label for="pin">6-digit Library PIN</label><input class="input pin" id="pin" name="pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="current-password" required autofocus></div><button class="button" type="submit">Open Library</button></form><script data-r3-pin-autofill-v91="1">(()=>{const f=document.getElementById('r3OwnerLoginV91'),p=document.getElementById('pin');if(!f||!p)return;let sent=false;const go=()=>{if(sent||!/^[0-9]{6}$/.test(String(p.value||'')))return;sent=true;setTimeout(()=>{try{f.requestSubmit?f.requestSubmit():f.submit();}catch{sent=false;}},120);};p.addEventListener('input',go);p.addEventListener('change',go);let n=0;const t=setInterval(()=>{go();if(++n>=12||sent)clearInterval(t);},250);})();</script>`,'''
if new_form not in pin:
    if old_form not in pin: raise SystemExit('V91_PIN_FORM_ANCHOR')
    pin=pin.replace(old_form,new_form,1)

pin=pin.replace('This device stays signed in with a long-lived HttpOnly owner session that is renewed whenever the Library is used.', 'This device stays signed in with a long-lived owner session. iOS Password AutoFill can remember the PIN and the form auto-submits after a 6-digit autofill.')

for name,text in [('pin',pin),('hard',hard),('simple',simple),('v7',v7)]:
    if 'SameSite=Lax' not in text or 'Expires=${expires}' not in text:
        raise SystemExit('V91_COOKIE_MARKER_'+name)
if 'data-r3-pin-autofill-v91="1"' not in pin or 'autocomplete="username"' not in pin:
    raise SystemExit('V91_AUTOFILL_MARKER')

PIN.write_text(pin,encoding='utf-8')
HARD.write_text(hard,encoding='utf-8')
SIMPLE.write_text(simple,encoding='utf-8')
V7.write_text(v7,encoding='utf-8')
print('READER_V91_SESSION_COMPAT=PASS')
