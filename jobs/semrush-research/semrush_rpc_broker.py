#!/opt/chatgpt-bridge/venv/bin/python
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import socketserver
import subprocess
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import quote

from playwright.sync_api import sync_playwright

MANAGER = os.environ.get('CLOAK_MANAGER_URL', 'http://127.0.0.1:8080').rstrip('/')
GUARDIAN = os.environ.get('VPS_RESOURCE_GUARDIAN_BIN', '/usr/local/bin/vps-resource-guardian')
PROFILE_ID = os.environ.get('SEMRUSH_NOXTOOLS_PROFILE_ID', '5f65f5cd-c8fa-4238-bd14-441760eda81d')
OWNER = 'semrush-rpc-broker'
LIVE_HOSTS = ['6.semrush.com.in', '5.semrush.com.in', '4.semrush.com.in', '3.semrush.com.in', '2.semrush.com.in', '1.semrush.com.in']
ALLOWED_METHODS = {'keywords.GetInfo', 'ideas.GetKeywordsSummary', 'ideas.GetKeywords', 'serp.GetURLs'}
ALLOWED_DPA_METHODS = {'organic.PositionsTotal', 'organic.Positions'}
DATABASE_RE = re.compile(r'^[a-z]{2}$')
LOCK = threading.RLock()


def safe_error(code: str, **extra):
    out = {'ok': False, 'state': code, 'error_code': code}
    out.update(extra)
    return out


def manager_call(method: str, path: str, payload=None, timeout: int = 90):
    data = None
    headers = {'Accept': 'application/json', 'User-Agent': 'semrush-rpc-broker'}
    if payload is not None or method != 'GET':
        data = json.dumps(payload or {}, separators=(',', ':')).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(MANAGER + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', 'replace')
        raise RuntimeError(f'{method} {path} HTTP {exc.code}: {raw[:500]}') from exc


def profile_status() -> str:
    try:
        return str(manager_call('GET', f'/api/profiles/{quote(PROFILE_ID, safe="")}', timeout=15).get('status') or '')
    except Exception:
        return ''


def guardian_acquire(ttl: int = 120, wait_seconds: int = 30) -> str:
    deadline = time.monotonic() + max(1, min(wait_seconds, 60))
    last = 'guardian-error'
    while time.monotonic() <= deadline:
        proc = subprocess.run(
            [GUARDIAN, 'acquire', '--owner', OWNER, '--profile', PROFILE_ID,
             '--priority', 'research-interactive', '--ttl', str(ttl), '--allow-recent-idle-reuse'],
            text=True, capture_output=True, check=False, timeout=20,
        )
        try:
            payload = json.loads((proc.stdout or '').strip() or '{}')
        except Exception:
            payload = {}
        if proc.returncode == 0 and payload.get('granted') is True and payload.get('token'):
            return str(payload['token'])
        last = str(payload.get('reason') or f'exit-{proc.returncode}')
        if last not in {'profile-busy', 'browser-slots-full'}:
            break
        time.sleep(0.25)
    raise RuntimeError('SEMRUSH_RESOURCE_ADMISSION_DENIED:' + last)


def guardian_release(token: str | None) -> None:
    if not token:
        return
    try:
        subprocess.run([GUARDIAN, 'release', '--token', token], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False, timeout=10)
    except Exception:
        pass


def ensure_profile_running() -> None:
    if profile_status() == 'running':
        return
    try:
        manager_call('POST', f'/api/profiles/{quote(PROFILE_ID, safe="")}/launch', {}, timeout=90)
    except RuntimeError as exc:
        if 'HTTP 409' not in str(exc):
            raise
    for _ in range(60):
        if profile_status() == 'running':
            return
        time.sleep(0.5)
    raise RuntimeError('SEMRUSH_PROFILE_LAUNCH_TIMEOUT')


def profile_cdp_live_connections() -> int | None:
    """Count ESTABLISHED socket endpoints for this profile's CDP port."""
    try:
        ps = subprocess.run(['docker', 'exec', 'cloak-manager', 'ps', '-eo', 'args'],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8)
    except Exception:
        return None
    if ps.returncode != 0:
        return None
    needle = f'--user-data-dir=/data/profiles/{PROFILE_ID}'
    port = None
    for line in (ps.stdout or '').splitlines():
        if needle not in line or '--remote-debugging-port=' not in line:
            continue
        m = re.search(r'--remote-debugging-port=(\d{2,5})(?:\s|$)', line)
        if m and 1 <= int(m.group(1)) <= 65535:
            port = int(m.group(1)); break
    if port is None:
        return 0 if profile_status() != 'running' else None
    target = f'{port:04X}'
    total = 0; known = False
    for path in ('/proc/net/tcp', '/proc/net/tcp6'):
        try:
            p = subprocess.run(['docker', 'exec', 'cloak-manager', 'cat', path],
                               text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8)
        except Exception:
            continue
        if p.returncode != 0:
            continue
        known = True
        for line in (p.stdout or '').splitlines()[1:]:
            fields = line.split()
            if len(fields) < 4 or fields[3] != '01':
                continue
            try:
                local_port = fields[1].rsplit(':', 1)[1].upper()
                remote_port = fields[2].rsplit(':', 1)[1].upper()
            except Exception:
                continue
            if target in {local_port, remote_port}:
                total += 1
    return total if known else None


def stop_profile_if_unowned() -> None:
    for _ in range(20):
        live = profile_cdp_live_connections()
        if live is None:
            return
        if live == 0:
            try:
                manager_call('POST', f'/api/profiles/{quote(PROFILE_ID, safe="")}/stop', {}, timeout=30)
            except Exception:
                pass
            return
        time.sleep(0.25)


def page_body(page) -> str:
    try:
        return ' '.join((page.locator('body').inner_text(timeout=4000) or '').split())
    except Exception:
        return ''


def challenge(page) -> bool:
    text = (str(page.title() or '') + ' ' + page_body(page)).lower()
    return any(x in text for x in ('just a moment', 'performing security verification', 'verify you are human', 'captcha', 'security verification'))


def info_args(seed: str, database: str) -> dict:
    return {'phrase': seed, 'device': 0, 'currency': 'USD', 'database': database, 'date': ''}


def idea_args(seed: str, database: str, questions_only: bool = False) -> dict:
    return {'phrase': seed, 'device': 0, 'currency': 'USD', 'database': database,
            'location': 0, 'date': '', 'mode': 0, 'questions_only': bool(questions_only)}


def idea_rows(result):
    if isinstance(result, list):
        return result
    if not isinstance(result, dict):
        return []
    for key in ('keywords', 'items', 'rows', 'data', 'results'):
        if isinstance(result.get(key), list):
            return result[key]
    return []


class BrokerState:
    def __init__(self, idle_seconds: int):
        self.idle_seconds = max(5, int(idle_seconds))
        self.pw = None
        self.browser = None
        self.ctx = None
        self.page = None
        self.server = None
        self.lease_token = None
        self.last_used = 0.0
        self.inflight = 0
        self.stopping = False

    def _pick_server(self):
        evidence = []
        try:
            host = (self.page.url.split('/')[2] if '://' in self.page.url else '')
            if host.endswith('semrush.com.in'):
                ok = bool(self.page.evaluate('()=>!!window?.sm2?.user?.api_key')) and not challenge(self.page)
                evidence.append({'host': host, 'ok': ok, 'title': str(self.page.title() or '')[:80]})
                if ok:
                    self.server = host
                    return evidence
        except Exception as exc:
            evidence.append({'host': 'current', 'ok': False, 'error': type(exc).__name__})
        for host in LIVE_HOSTS:
            try:
                url = f'https://{host}/analytics/keywordoverview/?q=roofing&db=us'
                self.page.goto(url, wait_until='domcontentloaded', timeout=45000)
                self.page.wait_for_timeout(1800)
                ok = bool(self.page.evaluate('()=>!!window?.sm2?.user?.api_key')) and not challenge(self.page)
                evidence.append({'host': host, 'ok': ok, 'title': str(self.page.title() or '')[:80]})
                if ok:
                    self.server = host
                    return evidence
            except Exception as exc:
                evidence.append({'host': host, 'ok': False, 'error': type(exc).__name__})
        raise RuntimeError('SEMRUSH_LIVE_AUTH_UNAVAILABLE:' + json.dumps(evidence, separators=(',', ':'))[:1200])

    def ensure_connected(self):
        if self.pw is not None and self.page is not None and self.server:
            self.last_used = time.monotonic()
            return
        self.lease_token = guardian_acquire()
        try:
            ensure_profile_running()
            self.pw = sync_playwright().start()
            self.browser = self.pw.chromium.connect_over_cdp(
                f'{MANAGER}/api/profiles/{quote(PROFILE_ID, safe="")}/cdp', timeout=30000)
            if not self.browser.contexts:
                raise RuntimeError('SEMRUSH_PROFILE_NO_CONTEXT')
            self.ctx = self.browser.contexts[0]
            self.page = self.ctx.pages[-1] if self.ctx.pages else self.ctx.new_page()
            self._pick_server()
            self.last_used = time.monotonic()
        except Exception:
            self.disconnect(stop_profile=True)
            raise

    def rpc(self, method: str, args: dict) -> dict:
        if method not in ALLOWED_METHODS:
            return safe_error('METHOD_NOT_ALLOWED')
        self.ensure_connected()
        self.inflight += 1
        try:
            value = self.page.evaluate("""async ({method,args})=>{
              const k=window?.sm2?.user?.api_key;
              if(!k)return {status:0,result:null,error:{message:'API_KEY_MISSING'}};
              const q={jsonrpc:'2.0',id:1,method,params:args};
              const r=await fetch('/kwogw/v2/webapi',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'include',body:JSON.stringify(q)});
              const text=await r.text(); let j=null; try{j=JSON.parse(text)}catch(e){}
              return {status:r.status,result:j?.result??null,error:j?.error??(j?null:{message:'NON_JSON',sample:text.slice(0,160)})};
            }""", {'method': method, 'args': args})
            self.last_used = time.monotonic()
            return {'ok': value.get('error') is None, 'status': value.get('status'), 'result': value.get('result'), 'error': value.get('error'), 'server': self.server}
        finally:
            self.inflight = max(0, self.inflight - 1)
            self.last_used = time.monotonic()

    def rpc_many(self, calls: list[dict]) -> list[dict]:
        if not isinstance(calls, list) or not calls or len(calls) > 16:
            raise RuntimeError('SEMRUSH_RPC_BATCH_INVALID')
        checked = []
        for call in calls:
            if not isinstance(call, dict):
                raise RuntimeError('SEMRUSH_RPC_BATCH_INVALID')
            method = str(call.get('method') or '')
            args = call.get('args')
            tag = str(call.get('tag') or '')[:500]
            if method not in ALLOWED_METHODS or not isinstance(args, dict):
                raise RuntimeError('SEMRUSH_RPC_BATCH_INVALID')
            checked.append({'tag': tag, 'method': method, 'args': args})
        self.ensure_connected()
        self.inflight += 1
        try:
            values = self.page.evaluate("""async (calls)=>{
              if(!window?.sm2?.user?.api_key)return calls.map(c=>({tag:c.tag,status:0,result:null,error:{message:'API_KEY_MISSING'}}));
              return await Promise.all(calls.map(async (c,i)=>{
                try{
                  const q={jsonrpc:'2.0',id:i+1,method:c.method,params:c.args};
                  const r=await fetch('/kwogw/v2/webapi',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'include',body:JSON.stringify(q)});
                  const text=await r.text(); let j=null; try{j=JSON.parse(text)}catch(e){}
                  return {tag:c.tag,status:r.status,result:j?.result??null,error:j?.error??(j?null:{message:'NON_JSON',sample:text.slice(0,160)})};
                }catch(e){return {tag:c.tag,status:0,result:null,error:{message:String(e)}}}
              }));
            }""", checked)
            self.last_used = time.monotonic()
            return list(values or [])
        finally:
            self.inflight = max(0, self.inflight - 1)
            self.last_used = time.monotonic()

    def dpa_rpc(self, method: str, params: dict) -> dict:
        if method not in ALLOWED_DPA_METHODS or not isinstance(params, dict):
            return safe_error('DPA_REQUEST_INVALID')
        script = """async ({method,params})=>{
          const k=window?.sm2?.user?.api_key;
          if(!k)return {status:0,result:null,error:{message:'API_KEY_MISSING'}};
          const q={jsonrpc:'2.0',id:1,method,params:{...params,apikey:k}};
          const r=await fetch('/dpa/rpc',{method:'POST',headers:{'Content-Type':'application/json; charset=utf-8'},credentials:'include',body:JSON.stringify(q)});
          const text=await r.text(); let j=null; try{j=JSON.parse(text)}catch(e){}
          return {status:r.status,result:j?.result??null,error:j?.error??(j?null:{message:'NON_JSON',sample:text.slice(0,160)})};
        }"""
        self.ensure_connected()
        self.inflight += 1
        try:
            value = self.page.evaluate(script, {'method': method, 'params': params})
            err_text = json.dumps(value.get('error'), ensure_ascii=False) if value.get('error') is not None else ''
            if 'Auth error' in err_text or 'API_KEY_MISSING' in err_text:
                self.disconnect(stop_profile=True)
                self.ensure_connected()
                value = self.page.evaluate(script, {'method': method, 'params': params})
            self.last_used = time.monotonic()
            return {'ok': value.get('error') is None, 'status': value.get('status'), 'result': value.get('result'), 'error': value.get('error'), 'server': self.server}
        finally:
            self.inflight = max(0, self.inflight - 1)
            self.last_used = time.monotonic()

    def collect_seed(self, seed: str, database: str, page_size: int = 100) -> dict:
        seed = ' '.join(str(seed).split()).strip()
        database = str(database or '').lower().strip()
        if not seed or len(seed) > 300:
            return safe_error('SEED_INVALID')
        if not DATABASE_RE.fullmatch(database):
            return safe_error('DATABASE_INVALID')
        info = self.rpc('keywords.GetInfo', info_args(seed, database))
        summary = self.rpc('ideas.GetKeywordsSummary', idea_args(seed, database, False))
        ideas_out = self.rpc('ideas.GetKeywords', idea_args(seed, database, False))
        ideas_error = ideas_out.get('error')
        return {'ok': bool(info.get('error') is None and summary.get('error') is None and ideas_error is None), 'state': 'PASS' if ideas_error is None else 'RPC_ERROR', 'seed': seed, 'database': database, 'server': self.server, 'info': info.get('result'), 'summary': summary.get('result'), 'ideas': idea_rows(ideas_out.get('result')), 'rpc_variant': 'live-ui-v1' if ideas_error is None else None, 'errors': {'info': info.get('error'), 'summary': summary.get('error'), 'ideas': [] if ideas_error is None else [ideas_error]}}

    def disconnect(self, stop_profile: bool = True):
        pw, token = self.pw, self.lease_token
        self.pw = self.browser = self.ctx = self.page = None
        self.server = None
        self.lease_token = None
        try:
            if pw is not None:
                pw.stop()
        except Exception:
            pass
        if pw is not None:
            time.sleep(0.4)
        if stop_profile:
            stop_profile_if_unowned()
        guardian_release(token)

    def idle_tick(self):
        if self.pw is None or self.inflight or self.stopping:
            return
        if time.monotonic() - self.last_used < self.idle_seconds:
            return
        self.stopping = True
        try:
            self.disconnect(stop_profile=True)
        finally:
            self.stopping = False


STATE = None


def handle_request(req: dict) -> dict:
    action = str(req.get('action') or '').strip().lower()
    with LOCK:
        if action == 'status':
            return {'ok': True, 'state': 'WARM' if STATE and STATE.pw is not None else 'IDLE', 'profile_status': profile_status(), 'server': STATE.server if STATE else None, 'inflight': STATE.inflight if STATE else 0, 'idle_seconds': STATE.idle_seconds if STATE else None}
        if action == 'ensure':
            try:
                STATE.ensure_connected(); return {'ok': True, 'state': 'WARM', 'server': STATE.server}
            except RuntimeError as exc: return safe_error(str(exc).split(':', 1)[0], detail=str(exc)[:1200])
            except Exception as exc: return safe_error('SEMRUSH_BROKER_RUNTIME_ERROR', runtime_error=type(exc).__name__)
        if action == 'collect_seed':
            try: return STATE.collect_seed(req.get('seed') or '', req.get('database') or 'us', req.get('page_size') or 100)
            except RuntimeError as exc: return safe_error(str(exc).split(':', 1)[0], detail=str(exc)[:1200])
            except Exception as exc: return safe_error('SEMRUSH_BROKER_RUNTIME_ERROR', runtime_error=type(exc).__name__)
        if action == 'rpc_many':
            calls = req.get('calls')
            if not isinstance(calls, list): return safe_error('REQUEST_INVALID')
            try: return {'ok': True, 'server': STATE.server, 'results': STATE.rpc_many(calls)}
            except RuntimeError as exc: return safe_error(str(exc).split(':', 1)[0], detail=str(exc)[:1200])
            except Exception as exc: return safe_error('SEMRUSH_BROKER_RUNTIME_ERROR', runtime_error=type(exc).__name__)
        if action == 'rpc':
            method = str(req.get('method') or ''); args = req.get('args')
            if method not in ALLOWED_METHODS or not isinstance(args, dict): return safe_error('REQUEST_INVALID')
            try: return STATE.rpc(method, args)
            except RuntimeError as exc: return safe_error(str(exc).split(':', 1)[0], detail=str(exc)[:1200])
            except Exception as exc: return safe_error('SEMRUSH_BROKER_RUNTIME_ERROR', runtime_error=type(exc).__name__)
        if action == 'dpa_rpc':
            method = str(req.get('method') or ''); params = req.get('params')
            if method not in ALLOWED_DPA_METHODS or not isinstance(params, dict): return safe_error('DPA_REQUEST_INVALID')
            try: return STATE.dpa_rpc(method, params)
            except RuntimeError as exc: return safe_error(str(exc).split(':', 1)[0], detail=str(exc)[:1200])
            except Exception as exc: return safe_error('SEMRUSH_BROKER_RUNTIME_ERROR', runtime_error=type(exc).__name__)
        if action == 'disconnect':
            STATE.disconnect(stop_profile=True); return {'ok': True, 'state': 'IDLE'}
    return safe_error('ACTION_NOT_ALLOWED')


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        raw = self.rfile.readline(262145)
        if not raw or len(raw) > 262144:
            response = safe_error('REQUEST_INVALID')
        else:
            try:
                req = json.loads(raw.decode('utf-8'))
                if not isinstance(req, dict): raise ValueError
                response = handle_request(req)
            except Exception:
                response = safe_error('REQUEST_INVALID')
        try:
            self.wfile.write((json.dumps(response, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8'))
        except BrokenPipeError:
            pass


class Server(socketserver.UnixStreamServer):
    def service_actions(self):
        with LOCK:
            if STATE is not None:
                STATE.idle_tick()


def main() -> int:
    global STATE
    ap = argparse.ArgumentParser(description='Single-owner Semrush RPC broker using the persistent NoxTools profile.')
    ap.add_argument('--socket', default='/run/semrush-rpc-broker/control.sock')
    ap.add_argument('--group-gid', type=int, required=True)
    ap.add_argument('--idle-seconds', type=int, default=20)
    args = ap.parse_args()
    STATE = BrokerState(args.idle_seconds)
    sock = pathlib.Path(args.socket)
    sock.parent.mkdir(parents=True, exist_ok=True)
    os.chown(sock.parent, 0, args.group_gid); os.chmod(sock.parent, 0o750)
    try: sock.unlink()
    except FileNotFoundError: pass
    try:
        with Server(str(sock), Handler) as server:
            os.chown(sock, 0, args.group_gid); os.chmod(sock, 0o660)
            server.serve_forever(poll_interval=0.25)
    finally:
        with LOCK:
            STATE.disconnect(stop_profile=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
