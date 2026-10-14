#!/usr/bin/env python3
"""Daily SEO + acquisition join. Source scanners remain independent owners."""
import argparse, datetime as dt, hashlib, json, os, pathlib, re, subprocess, sys, tempfile
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
        rows.append({"identity":domain, "domain":domain, "source":"SEOTRENDS", "title":x.get("title", ""), "score":x.get("discovery_score",0), "verdict":state, "reason":(terminal.get("reason") or reason)[:200], "metrics":terminal.get("metrics") or {}, "research":["Semrush existing broker","exact SERP","business/Niche DD"]})
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
    for x in seo["items"]:
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
    payload = {"schema":"opportunity-daily-v1","date_vn":day,"generated_at":dt.datetime.now(TZ).isoformat(),"scope":"SEO_TRENDS_PLUS_FLIPPA","overall":"PARTIAL_BLOCKED" if seo["terminal_status"]=="BLOCKED" or flippa["status"]!="PASS" else "RESEARCH_PENDING","seo":seo,"flippa":flippa,"research_queue":deduped,"limits":{"buy_cap_usd":MAX_BUY,"no_bids":True,"no_new_projects":True,"no_solo_semrush_research":True},"owner":"daily-synthesis-only"}
    return payload

def format_report(v):
    f=v["flippa"];s=v["seo"]
    lines=["# Daily SEO + Acquisition Radar — "+v["date_vn"],"",
        "STATE: "+v["overall"],"SCANNER SOURCE: existing SeoTrends + authenticated Flippa; not a full Flippa main crawl","",
        "## Coverage",
        "- SeoTrends: "+str(s["scanned"])+"/"+str(s["added"])+" daily added domains, "+str(len(s["items"]))+" shortlist; Semrush "+str(s["provider_status"])+"; terminal "+str(s["terminal_status"]),
        "- Flippa: "+str(f["stats"].get("first_access","?"))+" First Access, "+str(f["stats"].get("recent","?"))+" Recent-500; "+str(f["stats"].get("entered_recent_window","?"))+" entrants vs previous window (NOT necessarily newly listed).",
        "- Research queue: "+str(len(v["research_queue"]))+"; automated purchases/bids: 0.","",
        "## Prioritized research handoff (NOT BUY NOW / BUILD APPROVED)"]
    for x in v["research_queue"][:12]:
        val = x.get("url",x.get("domain",""))
        lines.append("- **"+x["title"]+"** ["+x["source"]+" / "+x["verdict"]+"] "+val+"; "+x.get("reason","")+"; next: "+", ".join(x["research"][:3]))
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
    value = build(args.date,current,prev,resolve_deep(args.date,args.deep))
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
    source_hash = hashlib.sha256((json.dumps(value["seo"],sort_keys=True)+json.dumps(value["flippa"],sort_keys=True)).encode()).hexdigest()
    target = OUT/(args.date+"-manifest.json")
    prior = load(target,{})
    if prior.get("source_sha256") == source_hash:
        print("ALREADY_CHECKPOINTED",target)
        return 0
    atomic(OUT/(args.date+"-report.md"),txt)
    atomic(OUT/(args.date+"-research-queue.json"),json.dumps(value,ensure_ascii=False,indent=2))
    atomic(target,json.dumps({"date":args.date,"source_sha256":source_hash,"status":value["overall"],"flippa_state":str(current),"previous_state":str(prev) if prev else None,"research_count":len(value["research_queue"])},indent=2))
    print("CHECKPOINT_PASS",target,"status",value["overall"],"research",len(value["research_queue"]))
    return 0

if __name__ == "__main__":
    sys.exit(main())
