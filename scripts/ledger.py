#!/usr/bin/env python3
"""Shared request ledger for multi-thread projects. Standard library only.

Rows live in a JSON-lines file. Every change appends the whole updated row, so the
file is also the history; the latest row per id wins.
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone

SCOPES = {
    "render": "new pictures, views or layout of the current design; no geometry change",
    "tweak": "change only the named part; everything else stays as it is",
    "redesign": "the user asked for a new design of the named thing",
    "new": "something that doesn't exist yet",
    "info": "an answer or a check; nothing is changed",
}


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
    r.update({k: v for k, v in kw.items() if v is not None})
    r.setdefault("history", []).append({"at": r["updated"], "status": status,
                                        **{k: v for k, v in kw.items() if v is not None}})
    save(p, r)
    show(r)

def show(r):
    print(f"{r['rid']:>5}  {r['status']:<9} scope={r.get('scope','?')}  owner={r.get('owner','?')}  eta={r.get('eta','-')}  "
          f"updated={r.get('updated','')}\n       {r['text'][:140]}")

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
             "deliver": a.deliver, "from_project": a.from_project, "scope": a.scope, "keep": a.keep, "created": now()}
        change(p, r, "routed")
    elif a.cmd in ("accept", "resume"):
        change(p, get(rows, a.rid), "accepted" if a.cmd == "accept" else "resumed", eta=a.eta)
    elif a.cmd == "park":
        if not a.told:
            sys.exit("refused: tell the user first (what waits, why, new ETA), then pass --told <message id>")
        change(p, get(rows, a.rid), "parked", reason=a.reason, eta=a.eta, told=a.told)
    elif a.cmd == "deliver":
        change(p, get(rows, a.rid), "delivered", where=a.where)
    elif a.cmd == "bounce":
        change(p, get(rows, a.rid), "bounced", reason=a.reason)
    elif a.cmd == "brief":
        r = get(rows, a.rid)
        print(f"Request {r['rid']} from the user (message {r['msg']}), routed to {r.get('owner')}:\n"
              f"  User's words: \"{r['text']}\"\n"
              f"  Scope: {r.get('scope', 'unset')} ({SCOPES.get(r.get('scope'), 'ask the coordinator')})\n"
              f"  Must not change: {r.get('keep') or 'anything the words above do not name'}\n"
              f"  Deliver to: {r.get('deliver')}\n"
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
            if r["status"] not in ("delivered", "bounced") and (not a.owner or a.owner.lower() in r.get("owner", "").lower()):
                show(r)
    elif a.cmd == "stale":
        for r in rows.values():
            if r["status"] in ("routed", "accepted", "resumed", "parked") and age_h(r) >= a.hours:
                print(f"STALE {age_h(r):.1f} h"); show(r)

if __name__ == "__main__":
    main()
