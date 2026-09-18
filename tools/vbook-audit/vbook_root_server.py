from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
import os,base64
BASE='/tmp/vbook-audit/roots'
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  u=urlparse(self.path); q=parse_qs(u.query)
  if u.path!='/get': self.send_response(404); self.end_headers(); return
  root=(q.get('root') or [''])[0]; fn=(q.get('file') or [''])[0]
  if not root.isdigit() or '/' in fn or '..' in fn:
   self.send_response(400); self.end_headers(); return
  p=os.path.join(BASE,root,'src',fn)
  try: b=open(p,'rb').read(); body=base64.b64encode(b)
  except: self.send_response(404); self.end_headers(); return
  self.send_response(200); self.send_header('Content-Type','text/plain'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
 def log_message(self,*a): pass
ThreadingHTTPServer(('0.0.0.0',18807),H).serve_forever()
