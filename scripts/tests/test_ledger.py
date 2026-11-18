"""Ledger rules hold: no row without a scope, no silent park, brief carries the user's words, find finds old asks.
    python3 scripts/tests/test_ledger.py"""
import os, subprocess, sys, tempfile
L = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ledger.py"), "--ledger",
     os.path.join(tempfile.mkdtemp(), "l.jsonl")]
run = lambda *a: subprocess.run(L + list(a), capture_output=True, text=True)
bad = 0
def ok(name, c):
    global bad; print("pass" if c else "FAIL", name); bad += not c
ok("add without --scope refused", run("add", "--msg", "m0", "--text", "x", "--owner", "T").returncode != 0)
ok("add with scope", run("add", "--msg", "m1", "--text", "match the close-ups on all eight", "--owner", "Edge", "--scope", "render", "--keep", "the design").returncode == 0)
ok("accept", run("accept", "R001", "--eta", "4-5 PM ET").returncode == 0)
ok("park without telling the user refused", run("park", "R001", "--reason", "shop questions", "--eta", "6 PM").returncode != 0)
ok("park after telling", run("park", "R001", "--reason", "shop questions", "--eta", "6 PM", "--told", "m9").returncode == 0)
b = run("brief", "R001").stdout
ok("brief quotes the user and the scope", "match the close-ups on all eight" in b and "no geometry change" in b and "the design" in b)
ok("find by the user's words", "R001" in run("find", "close-ups").stdout)
ok("scope change needs the user's message", run("scope", "R001", "--to", "tweak").returncode != 0 and run("scope", "R001", "--to", "tweak", "--msg", "m5").returncode == 0)
print("ledger ok" if not bad else f"{bad} failed"); sys.exit(1 if bad else 0)
