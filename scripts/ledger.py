#!/usr/bin/env python3
"""Shared request ledger for multi-thread projects. Standard library only.

Rows live in a JSON-lines file. Every change appends the whole updated row, so the
file is also the history; the latest row per id wins.

An ask is open until `verify` closes it with evidence that its done-check holds (the fix is live:
page updated, skill pushed, file delivered). `deliver` alone does not close anything.
"""
import argparse, json, os, sys, time, urllib.request
from datetime import datetime, timedelta, timezone

SCOPES = {
    "render": "new pictures, views or layout of the current design; no geometry change",
    "tweak": "change only the named part; everything else stays as it is",
    "redesign": "the user asked for a new design of the named thing",
    "new": "something that doesn't exist yet",
    "info": "an answer or a check; nothing is changed",
}


OPEN = ("routed", "accepted", "resumed", "parked", "waiting", "delivered")
CLOSED = ("closed", "bounced")
CHECK_EVERY_H = 2.0   # an open ask gets looked at, and the user told of any change, at least this often


def ledger_path(a):
    if a.ledger:
        return a.ledger
    if os.environ.get("REQUEST_LEDGER"):
        return os.environ["REQUEST_LEDGER"]
    base = os.environ.get("PROJECT_FILES", ".")
    return os.path.join(base, "request-ledger", "ledger.jsonl")

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def load(p):
    rows = {}
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    rows[r["rid"]] = r
    return rows

def save(p, r):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(r) + "\n")
        f.flush(); os.fsync(f.fileno())

def get(rows, rid):
    if rid not in rows:
        sys.exit(f"no request {rid}")
    return dict(rows[rid])

def change(p, r, status, **kw):
    r["status"] = status
    r["updated"] = now()
    if status in OPEN and not kw.get("next_check"):
        kw["next_check"] = (datetime.now(timezone.utc) + timedelta(hours=CHECK_EVERY_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r.update({k: v for k, v in kw.items() if v is not None})
    r.setdefault("history", []).append({"at": r["updated"], "status": status,
                                        **{k: v for k, v in kw.items() if v is not None}})
    save(p, r)
    show(r)

def show(r):
    print(f"{r['rid']:>5}  {r['status']:<9} scope={r.get('scope','?')}  owner={r.get('owner','?')}  eta={r.get('eta','-')}  "
          f"updated={r.get('updated','')}\n       {r['text'][:140]}")
    if r["status"] not in CLOSED:
        print(f"       done when: {r.get('done_check') or 'NOT SET: run ledger.py check ' + r['rid'] + ' --done-check ...'}")
        if r.get("waiting_on"):
            print(f"       waiting on: {r['waiting_on']}")
        if r.get("last_note"):
            print(f"       last: {r['last_note'][:140]}")

def parse(t):
    return datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

def due(r):
    nc = r.get("next_check")
    return r["status"] in OPEN and (not nc or parse(nc) <= datetime.now(timezone.utc))

def url_has(url, expect):
    req = urllib.request.Request(url, headers={"User-Agent": "request-ledger-verify", "Cache-Control": "no-cache"})
    body = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    return all(e in body for e in expect)

def age_h(r):
    t = datetime.strptime(r.get("updated", r["created"]), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger")
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("add"); a.add_argument("--msg", required=True); a.add_argument("--text", required=True)
    a.add_argument("--owner", required=True); a.add_argument("--owner-id"); a.add_argument("--deliver", default="owner thread")
    a.add_argument("--from-project")
    a.add_argument("--scope", required=True, choices=SCOPES,
                   help="what the user's words allow: " + "; ".join(f"{k} = {v}" for k, v in SCOPES.items()))
    a.add_argument("--keep", help="what must not change, in the user's terms (e.g. 'the design, stones, seat')")
    a.add_argument("--done-check", required=True,
                   help="what must be true, and checkable, for this to count as done and live (e.g. 'the project page shows the re-rendered pictures; wire check passes on every machine')")
    a.add_argument("--live-url", help="page the result must show up on; verify fetches it")
    x = sp.add_parser("check"); x.add_argument("rid"); x.add_argument("--done-check", required=True); x.add_argument("--live-url")
    x = sp.add_parser("note"); x.add_argument("rid"); x.add_argument("--text", required=True)
    x.add_argument("--eta"); x.add_argument("--next-check", type=float, help="hours until the next look (default 2)")
    x = sp.add_parser("wait"); x.add_argument("rid"); x.add_argument("--on", required=True, help="who or what it waits on (a render, another thread, the user)")
    x.add_argument("--eta", required=True); x.add_argument("--next-check", type=float)
    x = sp.add_parser("handoff"); x.add_argument("rid"); x.add_argument("--to", required=True); x.add_argument("--to-id")
    x.add_argument("--what", required=True, help="the part of the work the new owner does")
    x = sp.add_parser("verify"); x.add_argument("rid"); x.add_argument("--evidence", required=True,
                   help="what you checked: live URL, commit, file path, check output")
    x.add_argument("--expect", nargs="*", default=[], help="strings the live page must contain (new image names, version tag)")
    x.add_argument("--told", required=True, help="id of the message that told the user it's done")
    x = sp.add_parser("reopen"); x.add_argument("rid"); x.add_argument("--reason", required=True)
    x = sp.add_parser("due")
    x = sp.add_parser("report")
    for c in ("accept", "resume"):
        x = sp.add_parser(c); x.add_argument("rid"); x.add_argument("--eta", required=True)
    x = sp.add_parser("park"); x.add_argument("rid"); x.add_argument("--reason", required=True)
    x.add_argument("--eta", required=True); x.add_argument("--told", help="id of the message that told the user")
    x = sp.add_parser("deliver"); x.add_argument("rid"); x.add_argument("--where", required=True)
    x = sp.add_parser("bounce"); x.add_argument("rid"); x.add_argument("--reason", required=True)
    x = sp.add_parser("find"); x.add_argument("words", nargs="+")
    x = sp.add_parser("open"); x.add_argument("--owner")
    x = sp.add_parser("stale"); x.add_argument("--hours", type=float, default=2.0)
    x = sp.add_parser("show"); x.add_argument("rid")
    x = sp.add_parser("brief"); x.add_argument("rid")
    x = sp.add_parser("scope"); x.add_argument("rid"); x.add_argument("--to", required=True, choices=SCOPES)
    x.add_argument("--msg", required=True, help="id of the user's message that changed the scope")
    a = ap.parse_args()
    p = ledger_path(a); rows = load(p)

    if a.cmd == "add":
        rid = f"R{len(rows) + 1:03d}"
        r = {"rid": rid, "msg": a.msg, "text": a.text, "owner": a.owner, "owner_id": a.owner_id,
             "deliver": a.deliver, "from_project": a.from_project, "scope": a.scope, "keep": a.keep,
             "done_check": a.done_check, "live_url": a.live_url, "created": now()}
        change(p, r, "routed")
    elif a.cmd in ("accept", "resume"):
        change(p, get(rows, a.rid), "accepted" if a.cmd == "accept" else "resumed", eta=a.eta)
    elif a.cmd == "park":
        if not a.told:
            sys.exit("refused: tell the user first (what waits, why, new ETA), then pass --told <message id>")
        change(p, get(rows, a.rid), "parked", reason=a.reason, eta=a.eta, told=a.told)
    elif a.cmd == "deliver":
        r = get(rows, a.rid)
        change(p, r, "delivered", where=a.where, next_check=now())
        print(f"Still open. Now check it: {r.get('done_check') or 'set a done-check first'}; then run verify.")
    elif a.cmd == "check":
        r = get(rows, a.rid); change(p, r, r["status"], done_check=a.done_check, live_url=a.live_url)
    elif a.cmd == "note":
        r = get(rows, a.rid)
        nc = (datetime.now(timezone.utc) + timedelta(hours=a.next_check)).strftime("%Y-%m-%dT%H:%M:%SZ") if a.next_check else None
        change(p, r, r["status"] if r["status"] in OPEN else "accepted", last_note=a.text, eta=a.eta, next_check=nc)
    elif a.cmd == "wait":
        r = get(rows, a.rid)
        nc = (datetime.now(timezone.utc) + timedelta(hours=a.next_check)).strftime("%Y-%m-%dT%H:%M:%SZ") if a.next_check else None
        change(p, r, "waiting", waiting_on=a.on, eta=a.eta, next_check=nc)
    elif a.cmd == "handoff":
        r = get(rows, a.rid)
        owners = r.get("owners") or [r.get("owner")]
        change(p, r, r["status"] if r["status"] in OPEN else "accepted", owner=a.to, owner_id=a.to_id,
               owners=owners + [a.to], last_note=f"handed to {a.to}: {a.what}")
    elif a.cmd == "verify":
        r = get(rows, a.rid)
        if not r.get("done_check"):
            sys.exit(f"refused: {a.rid} has no done-check. Set one with `check`, then verify against it.")
        if r.get("live_url"):
            try:
                okk = url_has(r["live_url"], a.expect)
            except Exception as e:
                sys.exit(f"refused: could not load {r['live_url']} ({e}). Not live means not done.")
            if not okk:
                sys.exit(f"refused: {r['live_url']} does not contain {a.expect}. The fix isn't live yet; it stays open.")
            if not a.expect:
                print("warning: no --expect strings, so only 'the page loads' was checked. Name the new image or text next time.")
        change(p, r, "closed", evidence=a.evidence, told=a.told, closed=now())
    elif a.cmd == "reopen":
        change(p, get(rows, a.rid), "accepted", reason=a.reason, next_check=now())
    elif a.cmd == "due":
        hits = [r for r in rows.values() if due(r)]
        for r in hits:
            print("DUE"); show(r)
        if not hits:
            print("nothing due")
    elif a.cmd == "report":
        op = [r for r in rows.values() if r["status"] in OPEN]
        if not op:
            print("Every ask in the ledger is closed and verified.")
        for r in op:
            state = {"delivered": "delivered, still being checked",
                     "waiting": f"waiting on {r.get('waiting_on')}",
                     "parked": f"paused ({r.get('reason')})"}.get(r["status"], "in progress")
            print(f"- \"{r['text'][:90]}\" ({r.get('owner')}): {state}"
                  + (f", ETA {r['eta']}" if r.get("eta") else "")
                  + (f". Last: {r['last_note'].rstrip('.')}" if r.get("last_note") else "")
                  + f". Done when: {r.get('done_check') or 'not set'}.")
    elif a.cmd == "bounce":
        change(p, get(rows, a.rid), "bounced", reason=a.reason)
    elif a.cmd == "brief":
        r = get(rows, a.rid)
        print(f"Request {r['rid']} from the user (message {r['msg']}), routed to {r.get('owner')}:\n"
              f"  User's words: \"{r['text']}\"\n"
              f"  Scope: {r.get('scope', 'unset')} ({SCOPES.get(r.get('scope'), 'ask the coordinator')})\n"
              f"  Must not change: {r.get('keep') or 'anything the words above do not name'}\n"
              f"  Deliver to: {r.get('deliver')}\n"
              f"  Done when: {r.get('done_check') or 'not set: ask the coordinator'} (verified and live, not just made)\n"
              "Do only this. If the work seems to need more than the scope allows, ask before doing it.")
    elif a.cmd == "scope":
        change(p, get(rows, a.rid), get(rows, a.rid)["status"], scope=a.to, scope_msg=a.msg)
    elif a.cmd == "show":
        print(json.dumps(get(rows, a.rid), indent=1))
    elif a.cmd == "find":
        ws = [w.lower() for w in a.words]
        hits = [r for r in rows.values() if any(w in json.dumps(r).lower() for w in ws)]
        for r in hits: show(r)
        if not hits:
            print("no ledger match. Still search your thread history and the project chat before saying it wasn't asked.")
    elif a.cmd == "open":
        for r in rows.values():
            if r["status"] not in CLOSED and (not a.owner or a.owner.lower() in r.get("owner", "").lower()):
                show(r)
    elif a.cmd == "stale":
        for r in rows.values():
            if r["status"] in OPEN and age_h(r) >= a.hours:
                print(f"STALE {age_h(r):.1f} h"); show(r)

if __name__ == "__main__":
    main()
