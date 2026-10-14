#!/usr/bin/env python3
"""Immutable, prospective next-open reference labels for missed 1D Dump signals.

This is NON-TRADING research: not BUY_SIGNAL, Candidate, portfolio sizing, or
an authoritative backtest. Journal entries are appended, never backdated.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parents[1] / "data" / "opportunity-radar"
JOURNAL = DATA / "market-dump-forward-shadow.jsonl"
STATUS = DATA / "market-dump-forward-shadow-status.json"
SCHEMA = "opportunity-radar-dump-forward-shadow-v1"
RAW_SCHEMA = "market-pricing-append-only-raw-move-event-v1"
NY = ZoneInfo("America/New_York")
HORIZONS = (1, 5, 20)


def finite(x):
    try:
        val = float(x)
        return val if math.isfinite(val) else None
    except (ValueError, TypeError):
        return None


def utc_time(s):
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_DISCOVERY_TIMESTAMP")
    return d.astimezone(timezone.utc)


def require_input(health, prefilter):
    if health.get("status") != "COMPLETE" or health.get("complete") is not True:
        return False
    date = health.get("source_session_date")
    records = prefilter.get("records") or []
    if not date or prefilter.get("source_session_date") != date or prefilter.get("complete") is not True:
        raise ValueError("SOURCE_SESSION_MISMATCH")
    if len(records) != health.get("prefilter_count"):
        raise ValueError("PREFILTER_COUNT_MISMATCH")
    if any(r.get("last_date") != date for r in records):
        raise ValueError("STALE_PER_SYMBOL_SOURCE_DATE")
    if len({r["symbol"] for r in records}) != len(records):
        raise ValueError("DUPLICATE_PREFILTER_SYMBOL")
    if finite(health.get("fresh_history_coverage")) is None or finite(health["fresh_history_coverage"]) < .8:
        raise ValueError("INSUFFICIENT_FRESH_COVERAGE")
    return True


def validate_journal(journal):
    ids = set()
    for row in journal:
        if row.get("schema") != SCHEMA or row.get("state") != "SHADOW_ONLY_NO_TRADE":
            raise ValueError("BAD_EXISTING_SHADOW_JOURNAL")
        key = (row.get("event_id"), row.get("kind"), row.get("source_session_date"))
        if not row.get("event_id") or key in ids:
            raise ValueError("DUPLICATE_SHADOW_EVENT")
        ids.add(key)


def quote(rec):
    raw_open, adj_open, close, adj_close = (
        finite(rec.get("open")), finite(rec.get("adjusted_open")),
        finite(rec.get("price")), finite(rec.get("adjusted_price")),
    )
    if rec.get("adjustment_verified") is not True or rec.get("corporate_action_suspected") or rec.get("corporate_action_unverified"):
        return None
    ret = finite(rec.get("ret_1d_pct"))
    if not (raw_open and adj_open and close and adj_close and ret is not None and min(raw_open, adj_open, close, adj_close)>0):
        return None
    if abs(adj_open / raw_open - adj_close / close)>1e-5:
        return None
    return {"adjusted_open":adj_open,"adjusted_close":adj_close,"daily_factor":1+ret/100}


def market_open(session):
    return datetime.fromisoformat(session + "T09:30:00").replace(tzinfo=NY).astimezone(timezone.utc)


def proposal(event, captured):
    sym = event.get("symbol")
    if (event.get("schema")!=RAW_SCHEMA or event.get("predicate")!="1D_SHOCK" or not sym or
            event.get("state")!="RAW_MOVE_ONLY_NOT_TRADE"):
        return None
    move, volume = finite(event.get("adjusted_return_1d_pct_first_seen")), finite(event.get("volume_ratio_first_seen"))
    if move is None or volume is None or move > -7 or volume < 1:
        return None
    if event.get("event_id") != f'{event.get("source_session_date")}|{sym}|1D_SHOCK':
        raise ValueError("INVALID_IMMUTABLE_EVENT_ID")
    first_seen = utc_time(str(event["event_first_logged_at_utc"]))
    if first_seen > utc_time(captured):
        raise ValueError("FUTURE_FIRST_SEEN")
    return {"symbol":sym,"event_id":event["event_id"],"source_session_date":event["source_session_date"],
            "first_seen":first_seen.isoformat(),"volume_ratio":volume,"move":move,
            "baseline_emitted":event.get("baseline_emitted") is True,
            "source_prefilter_sha256":event.get("source_prefilter_sha256"),
            "severity":(-move)*math.log1p(volume)}


def append(base, kind, session, **extra):
    return {"schema":SCHEMA,"kind":kind,"event_id":base["event_id"],
            "source_session_date":session,"symbol":base["symbol"],
            "state":"SHADOW_ONLY_NO_TRADE",**extra}


def run(health, prefilter, raw_ledger, previous, sessions, captured):
    if not require_input(health,prefilter):
        return [], {"status":"SOURCE_DEGRADED_NOT_EVALUATED","no_trading":True}
    validate_journal(previous)
    now = utc_time(captured)
    session = health["source_session_date"]
    if session not in sessions:
        raise ValueError("SOURCE_SESSION_NOT_IN_EXCHANGE_CALENDAR")
    i_now = sessions.index(session)
    lookup={x["symbol"]:x for x in prefilter["records"]}
    prior_keys={(r["event_id"],r["kind"],r["source_session_date"]) for r in previous}
    output=[]
    def write(row):
        key=(row["event_id"],row["kind"],row["source_session_date"])
        if key not in prior_keys:
            prior_keys.add(key);output.append(row)
    # New detections are created ONLY on the current authoritative completed session.
    # The prior 2026 research cohorts are never silently imported.
    offers=[]
    unique=set()
    for r in raw_ledger:
        if r.get("source_session_date")!=session or r.get("predicate")!="1D_SHOCK":
            continue
        p=proposal(r,captured)
        if p is None:continue
        if p["symbol"] in unique:raise ValueError("DUPLICATE_CURRENT_DAY_SOURCE_EVENTS")
        unique.add(p["symbol"])
        if p["source_prefilter_sha256"] != health["prefilter_sha256"]:
            continue  # immutable first-capture packet can differ on later same-session rescans
        if p["symbol"] not in lookup or quote(lookup[p["symbol"]]) is None:
            # Do not create a future-tradable detection from bad current evidence.
            continue
        offers.append(p)
    missed=sorted((p for p in offers if not p["baseline_emitted"]),
                  key=lambda p:(p["severity"],p["symbol"]),reverse=True)[:20]
    control=sorted((p for p in offers if p["baseline_emitted"]),
                   key=lambda p:(p["severity"],p["symbol"]),reverse=True)
    for group,group_rows in (("C_MISSED_DUMP",missed),("A_BASELINE_DUMP",control)):
        for p in group_rows:
            write(append(p,"DETECTION",session,group=group,first_seen_utc=p["first_seen"],
                         logged_at_utc=now.isoformat(),source_prefilter_sha256=p["source_prefilter_sha256"],
                         volume_ratio=p["volume_ratio"],move_1d_pct=p["move"],
                         policy="OBSERVE_FROM_NEXT_NYSE_OPEN_ONLY"))
    state=previous+output
    proposals=[p for p in state if p["kind"]=="DETECTION"]
    existing_entries={p["event_id"]:p for p in state if p["kind"]=="ENTRY"}
    closed={p["event_id"] for p in state if p["kind"]=="BLOCK"}
    previous_marks={(p["event_id"],p["source_session_date"]):p for p in state if p["kind"]=="MARK"}
    for p in proposals:
        eid=p["event_id"]
        source=p["source_session_date"]
        if source not in sessions:continue
        i_source=sessions.index(source)
        i_entry=i_source+1
        if i_entry>=len(sessions):continue
        entry_session=sessions[i_entry]
        if session==entry_session and eid not in existing_entries and eid not in closed:
            # Require first-discovery AND decision logging before the next opening.
            if utc_time(p["first_seen_utc"])>=market_open(entry_session) or utc_time(p["logged_at_utc"])>=market_open(entry_session):
                write(append(p,"BLOCK",session,group=p["group"],reason="LATE_FIRST_DETECTION_OR_DECISION"))
                closed.add(eid);continue
            q=quote(lookup.get(p["symbol"],{}))
            if not q:
                write(append(p,"BLOCK",session,group=p["group"],reason="MISSING_VALID_NEXT_OPEN_OHLC"))
                closed.add(eid);continue
            factor=q["adjusted_close"]/q["adjusted_open"]
            entry=append(p,"ENTRY",session,group=p["group"],entry_session=entry_session,
                         entry_adjusted_open=q["adjusted_open"],current_adjusted_close=q["adjusted_close"],
                         gross_factor=factor,reference_only=True,source_prefilter_sha256=health["prefilter_sha256"])
            write(entry);existing_entries[eid]=entry
            write(append(p,"OUTCOME_1D",session,group=p["group"],entry_session=entry_session,
                         exit_session=session,gross_pct=(factor-1)*100,
                         net_50bps_pct=(factor-1)*100-.5,net_100bps_pct=(factor-1)*100-1.0))
        elif eid in existing_entries and eid not in closed:
            entry=existing_entries[eid]
            if i_now<i_entry or i_now>=i_entry+20:continue
            if i_now==i_entry:continue
            # Never skip a session and later fill the missing return from hindsight.
            previous_session=sessions[i_now-1]
            previous_row=(existing_entries.get(eid) if i_now==i_entry+1
                          else previous_marks.get((eid,previous_session)))
            if previous_row is None:
                write(append(p,"BLOCK",session,group=p["group"],reason="PRIOR_SESSION_MARK_MISSING"))
                closed.add(eid);continue
            q=quote(lookup.get(p["symbol"],{}))
            if not q:
                write(append(p,"BLOCK",session,group=p["group"],reason="DAILY_BAR_OR_CORPORATE_ACTION_UNVERIFIED"))
                closed.add(eid);continue
            factor=finite(previous_row["gross_factor"])*q["daily_factor"]
            mark=append(p,"MARK",session,group=p["group"],entry_session=entry_session,
                        gross_factor=factor,daily_adjusted_return_pct=(q["daily_factor"]-1)*100,
                        source_prefilter_sha256=health["prefilter_sha256"])
            write(mark)
            previous_marks[(eid,session)]=mark
            elapsed=i_now-i_entry+1
            if elapsed in (5,20):
                write(append(p,f"OUTCOME_{elapsed}D",session,group=p["group"],entry_session=entry_session,
                             exit_session=session,gross_pct=(factor-1)*100,
                             net_50bps_pct=(factor-1)*100-.5,net_100bps_pct=(factor-1)*100-1.0))
    return output,{"status":"SHADOW_ONLY_NO_TRADE","session":session,"accepted_prefilter_sha256":health["prefilter_sha256"],
                   "proposals":len(offers),"selected_new_missed":len(missed),"selected_control":len(control),
                   "added_by_kind":{k:sum(x["kind"]==k for x in output) for k in
                   ("DETECTION","ENTRY","MARK","OUTCOME_1D","OUTCOME_5D","OUTCOME_20D","BLOCK")},
                   "journal_previous":len(previous),"journal_new":len(output),
                   "first_detection_immutable":True,"buy_signal_generated":False,
                   "source_authority":"COMPLETED_US_SESSION_ONLY","promotion_eligible":False}


def main():
    health=json.loads((DATA/"market-health.json").read_text(encoding="utf-8"))
    if health.get("status")!="COMPLETE" or health.get("complete") is not True:
        print("FORWARD_SHADOW_SKIPPED_SOURCE_DEGRADED")
        return
    payload=(DATA/"market-prefilter.json").read_bytes()
    if hashlib.sha256(payload).hexdigest()!=health.get("prefilter_sha256"):
        raise ValueError("PREFILTER_SHA256_MISMATCH")
    prefilter=json.loads(payload)
    raw=[json.loads(s) for s in (DATA/"market-move-events.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
    old=JOURNAL.read_text(encoding="utf-8") if JOURNAL.exists() else ""
    previous=[json.loads(s) for s in old.splitlines() if s.strip()]
    import pandas_market_calendars as mcal
    today=datetime.fromisoformat(health["source_session_date"]).date()
    cal=mcal.get_calendar("NYSE")
    ix=cal.valid_days(start_date=today-timedelta(days=100),end_date=today+timedelta(days=65))
    sessions=[x.date().isoformat() for x in ix]
    added,report=run(health,prefilter,raw,previous,sessions,datetime.now(timezone.utc).isoformat())
    if added:
        tmp=JOURNAL.with_suffix(".jsonl.tmp")
        tmp.write_text(old+("" if not old or old.endswith("\n") else "\n")+
                       "".join(json.dumps(x,separators=(",",":"),allow_nan=False)+"\n" for x in added),encoding="utf-8")
        tmp.replace(JOURNAL)
    STATUS.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(report,separators=(",",":")))


if __name__=="__main__":
    main()
