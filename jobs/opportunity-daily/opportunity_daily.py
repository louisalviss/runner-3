#!/usr/bin/env python3
"""Daily SEO + acquisition join. Source scanners remain independent owners."""
import argparse, datetime as dt, hashlib, json, os, pathlib, re, subprocess, sys, tempfile
from build_buy_decision import qualify
from flippa_semrush_bridge import inspect as inspect_flippa_semrush
from daily_publish import publish as publish_daily
from zoneinfo import ZoneInfo

ROOT = pathlib.Path("/var/lib/acquisition-radar-scan")
SEO = pathlib.Path("/var/lib/seotrends-public/scans")
OUT = pathlib.Path("/var/lib/opportunity-daily")
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
MAX_BUY = 10000
TEMPLATE = ROOT / "flippa-daily-stage-20261013.py"
VENV = "/opt/chatgpt-bridge/venv/bin/python"

def load(path, default=None):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def atomic(path, content):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)

def parse_amount(x):
    try: return float(str(x).replace(",","")) if x is not None and str(x).strip() else None
    except (ValueError, TypeError): return None

def normalize_domain(s):
    s = str(s or "").lower().strip()
    s = re.sub(r"^https?://", "", s).split("/")[0]
    return s[4:] if s.startswith("www.") else s

def existing_flippa_states(exclude):
    p = [*ROOT.glob("flippa-????????-state.json"), *ROOT.glob("flippa-????????-pm-state.json"), *ROOT.glob("flippa-????????-daily-state.json")]
    return sorted([x for x in p if x != exclude and load(x, {}).get("recent_done")], key=lambda x:x.stat().st_mtime, reverse=True)

def run_flippa(day):
    """Invoke existing authenticated RawCDP source-owner, incremental recent/First Access only."""
    stamp = day.replace("-", "") + "-daily"
    state = ROOT / ("flippa-" + stamp + "-state.json")
    if load(state, {}).get("recent_done") and load(state, {}).get("first_done"):
        return state
    if not TEMPLATE.exists():
        raise RuntimeError("FLIPPA_TEMPLATE_MISSING")
    script = ROOT / ("flippa-daily-stage-" + stamp + ".py")
    if not script.exists():
        source = TEMPLATE.read_text(encoding="utf-8")
        if "20261013" not in source:
            raise RuntimeError("FLIPPA_TEMPLATE_DRIFT")
        atomic(script, source.replace("20261013", stamp))
    env = os.environ.copy()
    env["PYTHONPATH"] = "/opt/browser-stack/bin:/opt/dhs-control"
    output = subprocess.run([VENV, str(script), "bootstrap"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=900)
    atomic(OUT / (day + "-flippa-run.log"), output.stdout[-20000:])
    if output.returncode:
        raise RuntimeError("FLIPPA_SCAN_FAILED: see source run log")
    return state

def resolve_deep(day, specified=None):
    if specified: return specified
    candidate = ROOT / ("flippa-deep-" + day.replace("-","") + ".json")
    return str(candidate) if candidate.is_file() else None

def auth_blocked(item):
    s = str(item.get("reason", "")).upper()
    return any(x in s for x in ["AUTH_UNAVAILABLE", "NOX_LOGIN_CHALLENGE", "KEYWORD_UNIVERSE_FAILED", "BLOCKED_AUTH"])

def read_seo(day):
    queue = load(SEO / (day + "-semrush-queue.json"), {})
    sem = load(SEO / (day + "-semrush-results.json"), {})
    final = load(SEO / (day + "-terminal-verdicts.json"), {})
    items = list(queue.get("items", []))
    statuses = {normalize_domain(x.get("domain")): x for x in sem.get("items", [])}
    terminals = {normalize_domain(x.get("domain")):x for x in final.get("verdicts", [])}
    rows = []
    for x in items:
        domain = normalize_domain(x.get("domain"))
        provider = statuses.get(domain, {})
        reason = str(provider.get("reason", ""))
        terminal = terminals.get(domain, {})
        terminal_verdict = str(terminal.get("verdict") or "")
        if auth_blocked(provider) or final.get("status") == "BLOCKED" or (provider.get("status") not in ("PASS",) and final.get("status") != "PASS"):
            state = "BLOCKED_PROVIDER"
        elif terminal_verdict == "DROP":
            state = "DROP"
        elif terminal_verdict == "BUILD":
            state = "SEO_BUILD_TEST"
        elif terminal_verdict == "WATCH":
            state = "WATCH_DD" if terminal.get("product_intent_checked") else "WATCH_RESEARCH"
        elif provider.get("status") == "PASS":
            state = "WATCH_RESEARCH"
        else:
            state = "BLOCKED_PROVIDER"
        rows.append({"identity":domain, "domain":domain, "source":"SEOTRENDS", "title":x.get("title", ""), "score":x.get("discovery_score",0), "verdict":state, "reason":(terminal.get("reason") or reason)[:200], "metrics":terminal.get("metrics") or {}, "product_intent_checked":terminal.get("product_intent_checked") is True, "serp_gate":terminal.get("serp_gate"), "terminal_verdict":terminal_verdict or None, "research":["Semrush existing broker","exact SERP","business/Niche DD"]})
    return {"items":rows, "added":queue.get("added_total"),"scanned":queue.get("scanned"),"pending":queue.get("pending"),"source_complete":bool(queue.get("scan_terminal")),"provider_status":sem.get("status","MISSING"),"terminal_status":final.get("status","MISSING")}

def read_flippa(current_path, previous_path=None, deep_path=None):
    current = load(current_path, {})
    old = load(previous_path, {}) if previous_path else {}
    if not current.get("first_done") or not current.get("recent_done"):
        return {"status":"BLOCKED_SOURCE","error":"INCOMPLETE_FLIPPA_INCREMENTAL","new":[],"stats":{}}
    pages = current.get("pages", [])
    if len(set(current.get("recent_ids", []))) != 500 or any(p.get("status") != 200 or p.get("challenge") != "NONE" for p in pages):
        return {"status":"BLOCKED_SOURCE","error":"CARD_COVERAGE_OR_CHALLENGE","new":[],"stats":{}}
    curr_ids = set(current["recent_ids"])
    prev_ids = set(old.get("recent_ids", []))
    delta = sorted(curr_ids - prev_ids)
    current_rows = current.get("recent_rows", {})
    if not prev_ids:
        # No prior checkpoint is not evidence all inventory is NEW.
        delta = []
    deep = {str(x.get("id")):x for x in ((load(deep_path,[]) if deep_path else []) or [])}
    rows = []
    for key in delta:
        card = current_rows.get(key, {})
        if not card: continue
        cost = card.get("p")
        profit = card.get("pr")
        vetted = bool(card.get("vet"))
        if cost is not None and cost > MAX_BUY:
            continue
        if isinstance(profit,(int,float)) and profit < 0:
            continue
        title = (card.get("heading") or card.get("title") or "")[:110]
        desc = (card.get("raw_text") or card.get("title") or "").lower()
        seo_hint = any(w in desc for w in ("organic","search traffic","calculator","online tools","seo","google clicks","page views","utility"))
        kind = str(card.get("pt") or "").lower()
        if any(w in kind for w in ("youtube channel", "twitter account", "facebook page", "ecommerce", "shopify store")):
            continue
        if (profit is None or profit < 100) and not seo_hint:
            continue
        direct = deep.get(key, {})
        confirmed = direct.get("status") == 200 and direct.get("challenge") == "NONE"
        reserve = parse_amount(direct.get("reserve"))
        bin_price = parse_amount(direct.get("bin"))
        asking_price = parse_amount(direct.get("asking"))
        pageviews = parse_amount(direct.get("pageviews"))
        churn_s = direct.get("churn")
        churn = float(churn_s.rstrip("%")) if churn_s else None
        subs = int(direct.get("subs")) if str(direct.get("subs") or "").isdigit() else None
        verdict = "WATCH_RESEARCH"
        reason = "Card only; auction start is not reserve"
        if confirmed and reserve is not None and reserve > MAX_BUY:
            verdict, reason = "DROP_BUY_CAP", "Verified reserve exceeds $10k cap"
        elif confirmed and profit is None and pageviews is not None and pageviews < 200:
            verdict, reason = "DROP_TRAFFIC_WEAK", "Under 200 monthly pageviews and no verified profits"
        elif profit is None and seo_hint:
            verdict, reason = "BUILD_REFERENCE", "SEO utility concept; no earnings or traffic proof, and auction card is not reserve"
        elif confirmed and churn is not None and churn >= 25:
            verdict, reason = "WATCH_CHURN", "Direct listing shows high churn"
        elif confirmed and subs is not None and subs < 20:
            verdict, reason = "WATCH_SMALL_N", "Fewer than 20 subscriber accounts"
        elif confirmed and seo_hint and isinstance(profit,(int,float)) and profit < 200:
            verdict, reason = "WATCH_WEAK_ECON", "Low profit; cannot justify purchase without independent SEO moat"
        elif confirmed and seo_hint:
            verdict, reason = "SEO_BUY_DD", "Organic/utility thesis; GSC and keywords unverified"
        elif confirmed and vetted and isinstance(profit,(int,float)) and profit >= 250:
            verdict, reason = "BUY_DD", "Economics need proof of recurring profit and transferability"
        research = ["direct current listing/attainable reserve","GSC/GA + Semrush + exact SERP","unit economics/processor/cohorts","BUY vs BUILD","selective independent Reddit/X/Facebook evidence"]
        rows.append({"identity":"flippa:"+key, "id":key,"title":title,"url":card.get("href",""),"ask_card":cost,"profit_card":profit,"vetted_card":vetted,"reserve_verified":reserve,"bin_verified":bin_price,"asking_verified":asking_price,"pageviews_verified":pageviews,"subscriber_count":subs,"churn":churn,"source":"FLIPPA","verdict":verdict,"reason":reason,"research":research,"verified_detail":confirmed,"score":round((5 if vetted else 0) + min(5,max(0,profit or 0)/200) + (2 if seo_hint else 0),2)})
    rows.sort(key=lambda x:(x["verdict"] not in ("SEO_BUY_DD","BUY_DD","BUILD_REFERENCE"),-x["score"],x["identity"]))
    return {"status":"PASS","new":rows,"stats":{"first_access":len(set(current["first_ids"])),"recent":len(curr_ids),"entered_recent_window":len(delta),"exited_recent_window":len(prev_ids - curr_ids),"first_access_delta":len(set(current["first_ids"])-set(old.get("first_ids",[]))),"source_pages":len(pages)}}

def build(day, flippa_current, previous=None, deep=None):
    seo = read_seo(day)
    flippa = read_flippa(flippa_current, previous, deep)
    queue = []
    # Explicit quotas prevent 10k domains or a full market crawl from overwhelming the provider.
    for x in flippa["new"]:
        if x["verdict"] not in ("DROP_BUY_CAP","DROP_TRAFFIC_WEAK","DROP"):
            queue.append(x)
        if len([v for v in queue if v["source"] == "FLIPPA"]) >= 5: break
    # A final DROP is a terminal decision, not a pending-research slot.
    # Prioritize verified product-intent WATCH/BUILD_TEST before unmatched research.
    priority = {"SEO_BUILD_TEST":0, "WATCH_DD":1, "WATCH_RESEARCH":2, "BLOCKED_PROVIDER":3}
    seo_pending = sorted(
        (x for x in seo["items"] if x["verdict"] != "DROP"),
        key=lambda x:(priority.get(x["verdict"], 4), -float(x.get("score") or 0), x["identity"]),
    )
    for x in seo_pending:
        text = (x["title"]+" "+x["domain"]).lower()
        if any(w in text for w in ("bankfive", "news analysis", "electric motors", "it services and digital transformation", "digicom it services")):
            continue
        queue.append(x)
        if len([v for v in queue if v["source"] == "SEOTRENDS"]) >= 5: break
    seen = set()
    deduped = []
    for x in queue:
        identity = x["identity"]
        if identity in seen:continue
        seen.add(identity);deduped.append(x)
    decision = qualify(day, seo, flippa, root=SEO, max_buy_usd=MAX_BUY)
    payload = {"schema":"opportunity-daily-v2","date_vn":day,"generated_at":dt.datetime.now(TZ).isoformat(),"scope":"SEO_TRENDS_PLUS_FLIPPA","overall":"PARTIAL_BLOCKED" if decision["status"]!="PASS" else "RESEARCH_PENDING","seo":seo,"flippa":flippa,"research_queue":deduped,"qualification":decision,"limits":{"buy_cap_usd":MAX_BUY,"no_bids":True,"no_new_projects":True,"no_solo_semrush_research":True},"owner":"daily-synthesis-only"}
    return payload

def format_report(v):
    f=v["flippa"];s=v["seo"]
    lines=["# Daily SEO + Acquisition Radar — "+v["date_vn"],"",
        "STATE: "+v["overall"],"SCANNER SOURCE: existing SeoTrends + authenticated Flippa; not a full Flippa main crawl","",
        "## Coverage",
        "- SeoTrends: "+str(s["scanned"])+"/"+str(s["added"])+" daily added domains, "+str(len(s["items"]))+" shortlist; Semrush "+str(s["provider_status"])+"; terminal "+str(s["terminal_status"]),
        "- Flippa: "+str(f["stats"].get("first_access","?"))+" First Access, "+str(f["stats"].get("recent","?"))+" Recent-500; "+str(f["stats"].get("entered_recent_window","?"))+" entrants vs previous window (NOT necessarily newly listed).",
        "- Legacy source watch queue (not qualified DD): "+str(len(v["research_queue"]))+"; automated purchases/bids: 0.",""]
    qualification=v.get("qualification") or {}
    if qualification:
        c=qualification.get("counts") or {}
        lines += ["", "## Unified BUILD or BUY qualification", "- Scanner/evidence gate: "+qualification["status"]+"; candidates evaluated: "+str(qualification["evaluated"])+" (not every Flippa card).", "- Semantic business evidence: "+str(qualification.get('business_semantic_source_status') or 'NOT_RUN')+"; end-to-end business DD: "+str(qualification.get('end_to_end_business_dd') or 'NOT_RUN')+"; X/Facebook/Reddit validation: "+str(qualification.get('end_to_end_social_check') or 'NOT_RUN')+".", "- BUY approved: 0; BUILD approved: 0; DD shortlist: "+str(len(qualification["actionable_dd"]))+"; study/reference: "+str(len(qualification["study_queue"]))+".", "- Evidence status counts: "+", ".join(str(k)+"="+str(c[k]) for k in sorted(c)), "- Seller card earnings are NOT audited earnings; source domain traffic is NOT transferable to a new site.", "", "### DD candidates (not approval)"]
        for x in qualification["actionable_dd"]:
            lines.append("- **"+str(x["title"])+"** ["+x["source"]+" / "+x["category"]+"] "+x["reference"]+"; BUY="+x["buy"]["state"]+" / BUILD="+x["build"]["state"]+"; verify: "+", ".join(x["missing"][:3]))
        if not qualification["actionable_dd"]: lines.append("- None: zero candidates have enough evidence to enter a focused DD shortlist.")
        lines += ["", "### Study or reference only (not approved)"]
        for x in qualification["study_queue"]:
            lines.append("- **"+str(x["title"])+"** ["+x["source"]+" / "+x["category"]+"] "+x["reference"]+"; "+x["build"]["why"])
        if not qualification["study_queue"]: lines.append("- None.")
        lines += ["", "### Archived and not presented as an opportunity", "- "+str(qualification["evaluated"]-len(qualification["actionable_dd"])-len(qualification["study_queue"]))+" candidates remain fully documented in machine-readable qualification.candidates."]
    else:
        lines += ["", "## Unified BUILD or BUY qualification", "- NOT_RUN; no BUILD/BUY promotion possible."]
    cross=v.get("flippa_semrush") or {}
    if cross:
        lines += ["", "## Flippa independent Semrush cross-check", "- Status: "+str(cross.get("status"))+"; eligible verified domains: "+str(cross.get("eligible"))+"; counts: "+str(cross.get("counts"))+"."]
        for item in cross.get("items") or []:
            m=item.get("metrics") or {}
            lines.append("- "+item["domain"]+": "+item["status"]+"; modeled US organic traffic: "+str(m.get("estimated_us_organic_visits","N/A"))+"; organic keyword rows: "+str(m.get("organic_keyword_rows","N/A"))+"; "+str(item.get("reason") or "Source estimates, not buyer analytics"))
    else:
        lines += ["", "## Flippa independent Semrush cross-check", "- NOT_RUN; cannot certify Flippa keyword/SERP evidence."]
    lines += ["", "## Enforcement", "- Source results cannot be promoted by traffic/revenue headline alone; Semrush auth failure is BLOCKED, never zero demand.","- First Access/recent-window absence is NOT delisted/sold.", "- All social verification is candidate-targeted through existing source-owned adapters.", "- This is a machine-readable handoff. Human/semantic DD and source-local durability remain separately owned."]
    return "\n".join(lines)+"\n"

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--date",default=dt.datetime.now(TZ).date().isoformat())
    ap.add_argument("--run-flippa",action="store_true")
    ap.add_argument("--flippa-state")
    ap.add_argument("--previous-state")
    ap.add_argument("--deep")
    ap.add_argument("--dry-run",action="store_true")
    args=ap.parse_args(argv)
    scan_error = None
    default_current = ROOT/("flippa-"+args.date.replace("-","")+"-daily-state.json")
    current = pathlib.Path(args.flippa_state) if args.flippa_state else default_current
    if args.run_flippa:
        try:
            current = run_flippa(args.date)
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
            scan_error = type(exc).__name__ + ": " + str(exc)[:180]
            current = default_current
    prev = pathlib.Path(args.previous_state) if args.previous_state else next(iter(existing_flippa_states(current)),None)
    deep_path=resolve_deep(args.date,args.deep)
    value = build(args.date,current,prev,deep_path)
    semcross_path=ROOT/("flippa-semDD-"+args.date.replace("-","")+".json")
    if args.run_flippa and not args.dry_run and value["flippa"]["status"]=="PASS":
        try:
            value["flippa_semrush"]=inspect_flippa_semrush(args.date,value["flippa"],deep_path,max_domains=2)
        except Exception as exc:
            value["flippa_semrush"]={"status":"BLOCKED","eligible":None,"counts":{},"items":[],"reason":"BRIDGE_EXCEPTION:"+type(exc).__name__}
    elif semcross_path.is_file():
        value["flippa_semrush"]=load(semcross_path,{})
    cross=value.get("flippa_semrush") or {}
    cross_by_listing={x.get('listing_identity'):x for x in cross.get('items') or []}
    for candidate in value['qualification'].get('candidates') or []:
        if candidate.get('source')=='FLIPPA':
            c=cross_by_listing.get(candidate.get('identity'))
            candidate['evidence']['semrush_crosscheck']=(
                {'status':c.get('status'),'domain':c.get('domain'),'metrics':c.get('metrics'),'modeled_not_analytics':True}
                if c else {'status':'NOT_RUN_OR_UNVERIFIED_DOMAIN'}
            )
    value['qualification']['end_to_end_social_check']='NOT_RUN'
    value['qualification']['end_to_end_business_dd']='NOT_AUTOMATED'
    value['qualification']['business_semantic_source_status']=value['qualification'].get('semantic_dd_status')
    if cross.get('status')=='BLOCKED':
        value["overall"]="PARTIAL_BLOCKED"
    if scan_error:
        value["flippa"]["source_error"] = scan_error
        value["overall"] = "PARTIAL_BLOCKED"
    if not value["seo"]["source_complete"]:
        value["overall"] = "PARTIAL_BLOCKED"
    txt = format_report(value)
    if args.dry_run:
        print(txt)
        print("RESULT", json.dumps({"overall":value["overall"],"research_count":len(value["research_queue"]),"flippa":value["flippa"]["stats"],"seo":len(value["seo"]["items"])}))
        return 0
    OUT.mkdir(parents=True,exist_ok=True)
    # Fingerprint the decision output as well as inputs, so a fixed classifier cannot
    # be hidden behind a stale same-date checkpoint with identical source files.
    source_hash = hashlib.sha256(json.dumps({"seo":value["seo"],"flippa":value["flippa"],"research_queue":value["research_queue"],"qualification":value["qualification"],"limits":value["limits"],"flippa_semrush":value.get("flippa_semrush"),"report_sha256":hashlib.sha256(txt.encode("utf-8")).hexdigest()},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    target = OUT/(args.date+"-manifest.json")
    prior = load(target,{})
    if prior.get("source_sha256") == source_hash:
        print("ALREADY_CHECKPOINTED",target)
        if args.run_flippa:
            persisted=load(OUT/(args.date+"-research-queue.json"),{})
            saved=OUT/(args.date+"-report.md")
            saved_text=saved.read_text(encoding="utf-8") if saved.is_file() else txt
            p=publish_daily(args.date,persisted or value,saved_text)
            print("DAILY_DROPBOX",json.dumps({"status":p["status"],"label":p.get("label")}))
            if p["status"] not in ("PASS","ALREADY_PUBLISHED"):
                return 4
        return 0
    atomic(OUT/(args.date+"-report.md"),txt)
    atomic(OUT/(args.date+"-research-queue.json"),json.dumps(value,ensure_ascii=False,indent=2))
    atomic(target,json.dumps({"date":args.date,"source_sha256":source_hash,"status":value["overall"],"flippa_state":str(current),"previous_state":str(prev) if prev else None,"research_count":len(value["research_queue"]),"qualification_status":value["qualification"]["status"],"qualified_dd_count":len(value["qualification"]["actionable_dd"]),"approved_buy":0,"approved_build":0},indent=2))
    print("CHECKPOINT_PASS",target,"status",value["overall"],"research",len(value["research_queue"]))
    if args.run_flippa:
        p=publish_daily(args.date,value,txt)
        print("DAILY_DROPBOX",json.dumps({"status":p["status"],"label":p.get("label")}))
        if p["status"] not in ("PASS","ALREADY_PUBLISHED"):
            return 4
    return 0

if __name__ == "__main__":
    sys.exit(main())
