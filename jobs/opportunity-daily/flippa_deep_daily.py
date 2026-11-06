#!/usr/bin/env python3
"""Bounded Flippa listing detail acquisition; dedicated authenticated profile, no bypass."""
from __future__ import annotations
import argparse,json,pathlib,re,random,time,sys,os,hashlib,ipaddress,socket,subprocess,tempfile,shutil
from urllib.parse import urlsplit
ROOT=pathlib.Path('/var/lib/acquisition-radar-scan')
PROFILE="c97a7500-3b11-403f-ac43-2566cdcd3fa2"
ID=re.compile(r'^[0-9]{6,12}$')
MAX=3


# This uses the existing transient, Guardian-owned public CDP worker.  It does
# not reuse the authenticated Flippa profile to navigate an external website.
MAX_SITE_PER_RUN = 1
SITE_PAGE_LIMIT = 2
PUBLIC_JOB_ROOT = pathlib.Path('/opt/browser-stack/jobs')
PUBLIC_RESULT_ROOT = pathlib.Path('/opt/browser-stack/results')
PUBLIC_JOB = '/usr/local/bin/vps-cdp-job'
ASSET_LINK_LABELS = {
    'website', 'website url', 'visit website', 'view website',
    'visit site', 'view site', 'open website', 'official website',
}

def safe_public_url(url):
    try:
        p = urlsplit(str(url or '').strip())
        host = (p.hostname or '').lower()
        port = p.port  # malformed port must fail, not enter regex fallback
    except (TypeError,AttributeError,ValueError):
        return False
    domain = host.removeprefix('www.')
    if (p.scheme != 'https' or not domain or p.username or p.password
            or port not in (None,443) or domain in ('localhost','flippa.com')
            or domain.endswith(('.local','.internal','.localhost'))):
        return False
    try:
        ipaddress.ip_address(domain)
        return False
    except ValueError:
        return bool(re.fullmatch(r'[a-z0-9][a-z0-9.-]{2,252}',domain)
                    and '.' in domain and '..' not in domain)


def visible_flippa_session_state(header_text):
    """Do not mistake a 200 public listing for an authenticated session."""
    heading = ' '.join(str(header_text or '').lower().split())
    if re.search(r'\blog\s*in\b', heading) and re.search(r'\bsign\s*up\b', heading):
        return 'PUBLIC_ONLY'
    if re.search(r'\bdanny\b', heading):
        return 'AUTHENTICATED'
    return 'UNVERIFIED'


def exact_asset_link(listing_id, actual_listing_url, anchors, source_kind='DIRECT_LISTING_CURRENT'):
    """Accept one explicit external website anchor on the exact Flippa listing."""
    p = urlsplit(str(actual_listing_url or ''))
    if source_kind not in ('DIRECT_LISTING_CURRENT', 'AUTHENTICATED_LIVE'):
        return {}
    if (p.scheme != 'https' or (p.hostname or '').lower().removeprefix('www.') != 'flippa.com'
            or not re.match(r'^/' + re.escape(str(listing_id)) + r'(?:[-/?#]|$)',p.path)):
        return {}
    candidates = {}
    for anchor in (anchors if isinstance(anchors,list) else [])[:400]:
        if not isinstance(anchor,dict):
            continue
        label = ' '.join(str(anchor.get('text') or '').lower().strip().split())
        url = str(anchor.get('href') or '').strip()
        if label not in ASSET_LINK_LABELS or not safe_public_url(url):
            continue
        host = (urlsplit(url).hostname or '').lower().removeprefix('www.')
        candidates.setdefault(host,[]).append((label,url))
    if len(candidates) != 1:
        return {}  # ambiguous or confidential; never guess from title/body
    domain, matched = next(iter(candidates.items()))
    if len({u for _,u in matched}) > 1:
        # Different paths on the same site are still one confirmed website.
        matched.sort(key=lambda x:(len(x[1]),x[1]))
    label,url = matched[0]
    receipt = hashlib.sha256((str(listing_id)+'|'+label+'|'+url).encode()).hexdigest()
    return {'verified_asset_domain':domain,'verified_asset_url':url,
            'asset_domain_verified':True,
            'asset_domain_source_kind':source_kind,
            'asset_domain_source_ref':'https://flippa.com/'+str(listing_id)+'#asset-link-sha256:'+receipt}

def matched_site_url(url, domain):
    if not safe_public_url(url):
        return False
    host=(urlsplit(url).hostname or '').lower().removeprefix('www.')
    return host==domain or host.endswith('.'+domain)

def choose_second_page(links, domain, home):
    candidates=[]
    for a in (links if isinstance(links,list) else [])[:400]:
        if not isinstance(a,dict):
            continue
        link=str(a.get('href') or '')
        if not matched_site_url(link,domain) or link.rstrip('/')==home.rstrip('/'):
            continue
        target=(str(a.get('text') or '')+' '+urlsplit(link).path).lower()
        priority=next((n for n,k in enumerate(('pricing','advertis','advertise','services','features','product','about','contact'))
                       if k in target),None)
        if priority is None:
            continue
        candidates.append((priority,len(link),link))
    return min(candidates)[2] if candidates else None

def read_public_page(url):
    """One bounded existing vps-cdp-job call; never creates a new browser owner."""
    if not safe_public_url(url):
        return {'ok':False,'reason':'UNSAFE_TARGET'}
    host=urlsplit(url).hostname
    try:
        for info in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM):
            if not ipaddress.ip_address(info[4][0]).is_global:
                return {'ok':False,'reason':'NON_PUBLIC_DNS'}
    except (OSError,ValueError):
        return {'ok':False,'reason':'DNS_CHECK_FAILED'}
    fd,jobpath=tempfile.mkstemp(prefix='flippa-site-',suffix='.json',dir=str(PUBLIC_JOB_ROOT))
    name=pathlib.Path(jobpath).stem
    result=PUBLIC_RESULT_ROOT/name
    try:
        cfg={'id':name,'urls':[url],'fingerprint':name,'egress_mode':'proxy',
             'egress_profile':'browser','guardian_priority':'background',
             'timeout_seconds':30,'settle_ms':900,'max_chars':8500,
             'capture_links':True,'capture_screenshot':False}
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            json.dump(cfg,out)
        env={**os.environ,'VPS_CDP_LOCK_WAIT_SECONDS':'12'}
        proc=subprocess.run(['sudo','-n',PUBLIC_JOB,jobpath,name],capture_output=True,
                            text=True,timeout=54,check=False,env=env)
        manifest=result/'manifest.json'
        if proc.returncode or not manifest.exists():
            return {'ok':False,'reason':'PUBLIC_CDP_BLOCKED'}
        rows=json.loads(manifest.read_text(encoding='utf-8')).get('results') or []
        row=rows[0] if rows else {}
        if not row.get('ok') or not matched_site_url(row.get('final_url'),host.lower().removeprefix('www.')):
            return {'ok':False,'reason':'SITE_NOT_MATERIAL_OR_REDIRECT'}
        return {'ok':True,'url':row.get('final_url'),'title':str(row.get('title') or '')[:180],
                'text':str(row.get('text') or '')[:8500],
                'links':(row.get('links') or [])[:400],
                'engine':str(row.get('engine_version') or '')}
    except (OSError,ValueError,subprocess.TimeoutExpired):
        return {'ok':False,'reason':'PUBLIC_CDP_UNAVAILABLE'}
    finally:
        pathlib.Path(jobpath).unlink(missing_ok=True)
        if result.exists():
            shutil.rmtree(result)

def capture_public_site(row, day, fetcher=read_public_page):
    """Capture facts and source hashes, not a fabricated semantic REVIEWED verdict."""
    ident=str(row.get('id') or '')
    domain=str(row.get('verified_asset_domain') or '').lower()
    first_url=str(row.get('verified_asset_url') or '')
    if (not ident.isdecimal() or not row.get('asset_domain_verified')
            or not matched_site_url(first_url,domain)):
        return {'status':'DOMAIN_UNVERIFIED','listing_id':ident}
    pages=[]
    links=[]
    for index,url in enumerate((first_url,None)):
        if index==1:
            url=choose_second_page(links,domain,first_url)
            if not url:break
        observed=fetcher(url)
        if not observed.get('ok') or not matched_site_url(observed.get('url'),domain):
            return {'status':'PARTIAL_PUBLIC_CAPTURE' if pages else 'PUBLIC_CAPTURE_BLOCKED',
                    'listing_id':ident,'asset_domain':domain,'pages':pages,
                    'reason':str(observed.get('reason') or 'INVALID_MATERIAL')}
        material=' '.join(str(observed.get('text') or '').split())
        if len(material)<60:
            return {'status':'PARTIAL_PUBLIC_CAPTURE' if pages else 'PUBLIC_CAPTURE_BLOCKED',
                    'listing_id':ident,'asset_domain':domain,'pages':pages,'reason':'THIN_CONTENT'}
        digest=hashlib.sha256((str(observed['url'])+'\\n'+material).encode()).hexdigest()
        kind='home' if index==0 else ('pricing' if 'pric' in url.lower() else
                                    'monetization' if 'advertis' in url.lower() else 'product')
        pages.append({'kind':kind,'url':observed['url'],
                      'title':str(observed.get('title') or '')[:180],
                      'finding':material[:400],
                      'source_ref':'flippa-deep-'+day.replace('-','')+'.json#site-sha256:'+digest,
                      'text_excerpt':material[:4500],
                      'text_sha256':digest,'observed_public_only':True})
        links=observed.get('links') or []
    return {'status':'CAPTURED_PUBLIC_PENDING_REVIEW' if len(pages)==2 else 'PARTIAL_PUBLIC_CAPTURE',
            'listing_id':ident,'asset_domain':domain,'pages':pages,
            'semantic_review_required':True,
            'financials_independently_verified':False}

def extract(id,title,body,status,challenge):
    def match(pattern):
        m=re.search(pattern,body,re.I|re.S)
        return m.group(1).strip() if m else None
    return {
      'id':id,'status':status,'challenge':challenge,'title':title,
      'reserve':match(r'Reserve:\s*USD \$([\d,]+(?:\.\d+)?)'),
      'bin':match(r'Buy It Now for USD \$([\d,]+(?:\.\d+)?)'),
      'asking':match(r'Asking Price[^\n]*\s*\n+\s*USD \$([\d,]+(?:\.\d+)?)'),
      'pageviews':match(r'Page Views\s*([\d,]+)\s*p/mo'),
      'subs':match(r'Total Active Subscribers\s*([\d,]+)'),
      'churn':match(r'Overall Churn\s*([\d.]+%)'),
      'body':body[:12000],
    }

def candidates_for_daily(flippa,limit=MAX):
    rows=[x for x in flippa.get('new') or [] if str(x.get('id') or '') and ID.fullmatch(str(x['id'])) and str(x.get('verdict') or '') not in ('DROP','DROP_TRAFFIC_WEAK','DROP_BUY_CAP')]
    # Focus the limited authenticated detail budget on plausible deals first.
    # Unverified build-reference cards must not displace higher-scoring watch candidates.
    rows.sort(key=lambda x:(0 if str(x.get('verdict') or '').startswith(('WATCH','BUY','SEO_BUY')) else 1, -float(x.get('score') or 0)))
    return list(dict.fromkeys(str(x['id']) for x in rows))[:min(MAX,limit)]

def existing_complete(path,ids):
    try:
        content=json.loads(path.read_text(encoding='utf8'))
        byid={str(x.get('id')):x for x in content if isinstance(x,dict)}
        return bool(ids) and all(i in byid and byid[i].get('status')==200 and byid[i].get('challenge')=='NONE' and byid[i].get('profile_id')==PROFILE for i in ids)
    except (OSError,ValueError,TypeError):return False

def capture(ids,day,out=ROOT):
    started_at=time.monotonic()
    ids=list(dict.fromkeys(str(x) for x in ids))[:MAX]
    if not all(ID.fullmatch(x) for x in ids):return {'status':'BLOCKED','reason':'INVALID_IDS','items':0}
    root=pathlib.Path(out);root.mkdir(parents=True,exist_ok=True)
    file=root/('flippa-deep-'+day.replace('-','')+'.json')
    state=root/('flippa-deep-'+day.replace('-','')+'-state.json')
    if not ids:
        return {'status':'PASS_EMPTY','items':0,'source':'NO_ELIGIBLE_CARDS'}
    # Never silently reuse or overwrite prior-day legacy-profile evidence.
    existing=[]
    if file.is_file():
        try:
            existing=json.loads(file.read_text(encoding='utf8'))
        except (ValueError,OSError):
            return {'status':'BLOCKED','reason':'DETAIL_EVIDENCE_INVALID','items':0}
        if (not isinstance(existing,list) or
                any(not isinstance(x,dict) or x.get('profile_id')!=PROFILE for x in existing)):
            return {'status':'BLOCKED','reason':'FLIPPA_DETAIL_PROFILE_LINEAGE_MISMATCH','items':0}
    prior={}
    if state.is_file():
        try:
            prior=json.loads(state.read_text(encoding='utf8'))
        except (OSError,ValueError):
            return {'status':'BLOCKED','reason':'DETAIL_STATE_INVALID','items':0}
        if not isinstance(prior,dict) or prior.get('profile_id')!=PROFILE:
            return {'status':'BLOCKED','reason':'FLIPPA_DETAIL_STATE_PROFILE_UNVERIFIED','items':0}
    if existing_complete(file,ids):
        return {'status':'PASS','items':len(ids),'source':'VALID_CACHED_DEEP'}
    import_repair=False
    if state.is_file():
        if prior.get('status') in ('BLOCKED','PARTIAL') and prior.get('date')==day:
            # One explicit recovery is allowed for a local missing dependency only;
            # never retry an auth/challenge/rate-limit failure in the same day.
            import_repair=(os.environ.get('ACQ_FLIPPA_ENV_FIX_ONCE')=='1' and prior.get('reason')=='ModuleNotFoundError' and not prior.get('repair_attempted'))
            if not import_repair:
                return {'status':prior['status'],'items':prior.get('items',0),'reason':'ONE_ATTEMPT_PER_DAY'}
            stamped={**prior,'repair_attempted':True}
            tmp=state.with_suffix('.tmp');tmp.write_text(json.dumps(stamped,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,state)
    done={str(x.get('id')):x for x in existing if isinstance(x,dict) and x.get('status')==200 and x.get('challenge')=='NONE' and x.get('profile_id')==PROFILE}
    remaining=[i for i in ids if i not in done]
    rows=list(done.values())
    status='PASS'; reason=''
    try:
        sys.path.insert(0,'/opt/browser-stack/bin')
        from raw_cdp_skill import RawCDPSkill
        with RawCDPSkill(PROFILE,owner='flippa-daily-deep-'+day,keep_running=False,new_page=True,close_page_on_exit=True,priority='auth') as skill:
            page=skill.page
            for count,listingid in enumerate(remaining):
                response=page.goto('https://flippa.com/'+listingid,wait_until='domcontentloaded',timeout=60000)
                page.wait_for_timeout(1600)
                http=response.status if response else 0
                challenge=skill.challenge()
                if http in (403,429) or challenge!='NONE':
                    status='BLOCKED';reason='HTTP_OR_HUMAN_CHALLENGE'
                    break
                title=page.title()
                body=page.locator('body').inner_text(timeout=15000)
                record=extract(listingid,title,body,http,challenge)
                record['profile_id']=PROFILE
                # Listing material may be public even when the profile is signed
                # out. Only a visible account marker can label it authenticated.
                nav_state = visible_flippa_session_state(body[:700])
                record['session_auth_state'] = nav_state
                record['listing_source_kind'] = ('AUTHENTICATED_LIVE'
                    if nav_state == 'AUTHENTICATED' else 'DIRECT_LISTING_CURRENT')
                try:
                    anchors=page.locator('a[href]').evaluate_all("""nodes => nodes.slice(0,400).map(a => ({
                        text: String(a.innerText || a.getAttribute('aria-label') || '').trim().slice(0,100),
                        href: String(a.href || '')
                    }))""")
                    record.update(exact_asset_link(
                        listingid,page.url,anchors,source_kind=record['listing_source_kind']))
                except Exception:
                    record['asset_domain_status']='ANCHOR_INSPECTION_UNAVAILABLE'
                rows.append(record)
                if count<len(remaining)-1:time.sleep(random.uniform(12,18))
    except Exception as e:
        status='BLOCKED';reason=type(e).__name__
    # The authenticated Flippa RawCDPSkill context has closed. Use only the
    # existing separate public CDP worker for a single verified external site.
    if status=='PASS':
        for record in rows:
            if (record.get('asset_domain_verified') is True
                    and not record.get('site_product_review')
                    and time.monotonic()-started_at < 100):
                record['site_product_review']=capture_public_site(record,day)
                break
    if status=='PASS' and sum(x.get('status')==200 and x.get('challenge')=='NONE' and str(x.get('id')) in ids for x in rows)!=len(ids):
        status='PARTIAL';reason='INCOMPLETE_DETAILS'
    # Always preserve earlier verified rows on challenge: no truncation.
    if rows:
        tmp=file.with_suffix('.json.tmp');tmp.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf8');os.replace(tmp,file)
    auth_states = [str(x.get('session_auth_state') or 'UNVERIFIED') for x in rows
                   if str(x.get('id') or '') in ids]
    result={'date':day,'profile_id':PROFILE,'status':status,'requested':len(ids),'items':len(rows),
            'reason':reason,'source':'SHARED_FLIPPA_CDP',
            'authenticated_details':sum(x == 'AUTHENTICATED' for x in auth_states),
            'public_or_unverified_details':sum(x != 'AUTHENTICATED' for x in auth_states),
            'repair_attempted':import_repair}
    tmp=state.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,state)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--date',required=True)
    p.add_argument('--ids',nargs='*',default=[])
    args=p.parse_args()
    print(json.dumps(capture(args.ids,args.date),ensure_ascii=False))
