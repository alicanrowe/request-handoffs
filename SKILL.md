---
name: request-handoffs
description: Use in any multi-thread project (a coordinator plus work threads) whenever a user ask or flag is routed, accepted, parked, delivered, or questioned ("where is X?", "did X ever reach you?"), and on every coordinator wake. Keeps a shared request ledger so no ask is dropped, parked silently, denied without a search, or called done before the fix is verified and live, and so open asks get re-checked and reported without the user asking.
metadata:
  author: Alican Rowe (@alicanrowe)
---

# Request handoffs

A project has one coordinator and many threads. Asks get lost in three places: when they are routed, when a thread quietly puts them behind newer work, and when someone answers "nobody asked for that" from memory. Asks also grow: a brief turns "match the pictures" into "redesign". And asks stall at the end: the fix is made, a long render starts, and nobody comes back to put it live or tell the user. This skill closes all of these with one shared ledger and seven rules.

## The ledger
- One JSON-lines file in the project's shared folder, shared by every thread and the coordinator. Set `REQUEST_LEDGER` to its path, or pass `--ledger`. The default is `request-ledger/ledger.jsonl` under the shared folder (`$PROJECT_FILES`, otherwise the current folder).
- `scripts/ledger.py` reads and writes it. Standard library only.
- One row per ask: the user's message id and words, the owner thread, where the result is to be delivered, the **done-check** (what must be true, and checkable, for it to count as done), status, ETA, when it is next due a look, and a history of every change.
- A flag is an ask. "These wires float", "that link is broken", "this looks wrong" gets a row like any request, with a done-check that says how the fix will be seen live.
- Open statuses: routed, accepted, resumed, parked, waiting, delivered. Only `verify` closes a row (or `bounce`, when it isn't the thread's to do).

```
python3 scripts/ledger.py add --msg <user msg id> --text "<user's words>" --owner "<thread title>" --owner-id <thread id> --deliver "<where>" --scope render|tweak|redesign|new|info --done-check "<what must be true and live>" [--live-url <page>] [--keep "<what must not change>"] [--from-project <source project>]
python3 scripts/ledger.py check <rid> --done-check "<...>" [--live-url <page>]   # set or fix the done-check
python3 scripts/ledger.py note <rid> --text "<progress, in the user's terms>" [--eta ...] [--next-check <hours>]
python3 scripts/ledger.py wait <rid> --on "<render / other thread / the user>" --eta "<range>" [--next-check <hours>]
python3 scripts/ledger.py handoff <rid> --to "<thread>" --to-id <id> --what "<their part>"   # stays open, new owner
python3 scripts/ledger.py verify <rid> --evidence "<what you checked>" --expect <strings on the live page> --told <msg id>   # the only way to close
python3 scripts/ledger.py reopen <rid> --reason "<what's still wrong>"
python3 scripts/ledger.py due                     # open rows due a look now (every 2 h by default; delivered rows at once)
python3 scripts/ledger.py report                  # plain-English list of everything still open, for the user
python3 scripts/ledger.py brief <rid>            # the user's words, scope and keep-list, to paste at the top of a brief
python3 scripts/ledger.py scope <rid> --to tweak --msg <id of the user's message that changed it>
python3 scripts/ledger.py accept <rid> --eta "2:00-3:30 PM ET"
python3 scripts/ledger.py park <rid> --reason "<what jumped ahead>" --eta "<new range>" --told <msg id of the message telling the user>
python3 scripts/ledger.py resume <rid> --eta "<range>"
python3 scripts/ledger.py deliver <rid> --where "<message id or file>"   # does NOT close; verify does
python3 scripts/ledger.py find <words...>       # search asks, open or closed
python3 scripts/ledger.py open [--owner <title>] # what is still owed
python3 scripts/ledger.py stale --hours 2        # accepted or parked rows with no update
```

## Rule 1: route with a row (coordinator)
When you route a user ask to a thread, add a ledger row in the same turn, with the user's message id and their exact words. Name one owner thread. If the ask says where the result should come back ("bring it to this thread", "show me here"), put that in `--deliver`.

**Cross-project asks** ("use the jewelry direction on the case's tools", "bring the new tools over to the case") belong to the thread that owns the thing being changed: the case thread here, not the jewelry thread. Tag `--from-project` with where the style or parts come from, and send the source thread an FYI only. Say both thread names to the user, so they know where to look.

**Scope comes from the user's words, not from the plan.** Set `--scope` from what the user actually said: "match the close-ups", "same layout", "re-render" is `render` (no geometry change); "fix the moth rig" is `tweak` (that part only); only "redesign X" or "make it new" is `redesign`. Every brief you write for a thread starts with `ledger.py brief <rid>`, so the thread sees the user's own words and what must not change. When the user narrows or widens the scope later, run `scope` with their message id and tell every thread working on it.

**Machine work goes to cloud machines.** Never route a render, a bake or a long compute job to a session on the user's own computer. Their computer is for things only it can do (a signed-in app, a local download, moving files), and that is a gate in the ETA.

## Rule 2: accept or bounce (thread)
A thread that receives an ask runs `accept` with an ETA (use eta-estimating), and puts it on its checklist **as its own line, worded in the user's terms**. Before starting, read `brief <rid>`: if the plan in the brief does more than the scope allows (a redesign when the user asked for matching pictures), do the scoped work and ask about the rest. If the ask isn't yours, say so to the coordinator straight away and leave the row unaccepted. Silence is not acceptance.

## Rule 3: never park silently (thread)
When newer or more urgent work pushes an accepted ask back (a shop-floor emergency, an audit, a new request), that is a change to a promise:
1. Run `park` with the reason and a new ETA.
2. In the same turn, tell the user in one line: what is waiting, why, and when it restarts. Pass that message's id as `--told`. The script refuses a park without `--told`.
3. Keep the checklist line, marked as paused with the reason. Never drop it from the checklist.
4. When the urgent work ends, `resume` it before taking anything new, unless the user reorders.

Two hours with no update on an accepted ask counts as parked. The coordinator runs `stale --hours 2` whenever it summarises work for the user, and asks the owner thread about each hit.

## Rule 4: search before you deny (everyone)
Before answering "it never got to me", "nobody asked for that", "it was never made", or "nothing was lost", you must search, and you must say what you searched:
1. `ledger.py find <key words>` (try the user's words and the thing's names, for example "handle", "inlay", "tools").
2. Your own thread history and your checklist, including lines you marked pending or paused.
3. As coordinator: the project chat for the user's own message, and the owner thread's history.

If any of these turns up the ask, the answer is "yes, it reached <thread> at <time>; here is where it stands", not a denial. A user who says "I definitely asked" is right until a search proves otherwise. Don't let the way the question is worded steer the search: "did it come over from the jewelry thread?" still means "is the work I asked for anywhere?", so search for the work, not just for a handoff from that thread.

## Rule 5: do the asked thing, not more (everyone)
A brief can grow on the way: the coordinator plans "bring them all to the same level" and writes "redesign", or a thread sees something it would improve. Work beyond the user's words costs their time to review and can undo choices they liked. So:
1. The thread's first checklist line quotes the scope ("Match Durumi's close-ups; design unchanged").
2. Anything outside the scope is a suggestion in the reply, not work done.
3. When the user narrows the scope mid-job ("no redesign"), stop the out-of-scope work in the same turn, keep what's in scope, and say what was dropped.

## Rule 6: done means verified and live (everyone)
Nothing is done because the work was made, a render was started, or a reply said "fixed". It is done when the done-check holds where the user will see it:
1. **Set the done-check when the row is made**, in checkable terms: "the project page on the site shows the re-rendered images (new version suffix) for every machine; wire check passes", "skill pushed to its GitHub repo on main", "file attached in the project chat". Anything the project's standing rules require counts too: site page updated, skill published, Drive backup done.
2. **`deliver` is not done.** After delivering, look: load the live page (with a cache-busting fetch), open the commit, read the file. Then run `verify` with what you saw. When there's a `--live-url`, `verify` fetches it and refuses unless the page contains the `--expect` strings (name the new image file or version, not just the page title).
3. **Tell the user it's done in the same turn**, with the link, and pass that message as `--told`. `verify` refuses without it.
4. If the user says it's still wrong, `reopen` it at once. Their word beats the check.

## Rule 7: follow through without being asked (everyone)
The user should never have to ask "did that ever happen?". So:
1. **The owner keeps going after long jobs.** Before ending a turn while a render, upload or other long job runs, the owner thread runs `wait --on "<job>"` and schedules its own wake-up (`send_later`) for when the job should be done. On waking, it checks the output, continues the next step (page, push, backup), and only stops when `verify` passes. A thread whose work is waiting is not finished: don't resolve it.
2. **Handoffs keep the row open.** When the last step belongs to another thread (a page refresh, a merge), run `handoff`, message that thread, and wake it when your part is ready. The row stays open under the new owner until that thread verifies it. A thread that marked itself done but still owes a step gets messaged, not forgotten.
3. **The coordinator runs `due` on every wake** and, while any row is open, keeps one scheduled check-in of its own (every 2 to 3 hours, `send_later`). For each due row: ask the owner thread where it stands, or check the done-check directly; then `note` what it found. A row that slipped past its ETA gets a new ETA and a one-line message to the user, unprompted.
4. **Report back unprompted.** When a row closes, the user hears about it in the project chat (the coordinator relays it). When the user comes back after being away, the coordinator's first reply includes `report` for anything still open. Never make the user remind you.
5. Every lesson gets folded back here (see below), so the same stall can't happen twice.

## Delivering
Standing rule from the user (18 Nov 2026): merge pull requests when they are ready, without asking. A thread that opened a PR merges it once its checks pass and the result has been looked at, then reports it as done with the link. Merging is not a reason to park or wait for a reply. The scope rule still holds: a PR that goes beyond the user's words is reported, not merged.

When the result goes out, run `deliver` with the message or file, and post it where `--deliver` says. Then check the done-check and run `verify` (Rule 6). If the user asked for it to come back to the project chat, the owner thread sends it to the coordinator to relay, not just to its own thread.

## Worked failure (why this exists)
A user asked the coordinator, in three messages a few minutes apart, to redesign a case piece's tools, tool stands, handle and outside inlays in the style of a jewelry line, and to "bring them to this thread". The coordinator routed all three to the case thread correctly, and the case thread put them on its checklist. Within 15 minutes the user asked for a build-book audit, then spent two hours at the shop asking for cut lists. The case thread did that work, left the design lines as "not started" (one quietly marked "paused for the book"), and never told the user. Two hours later the user asked "did the redesign never make it from the jewelry thread?". The case thread answered "no, it never got to me", and the coordinator, after the jewelry thread said it hadn't made it, told the case thread "nothing was lost, it was never made". Both answers were wrong: the ask had been on the case thread's own checklist the whole time.

A second failure the same day: the user asked for eight sawhorses' close-ups and sheet layout to match a ninth. The briefs said "bring to the same level", and threads started redesigning parts. The user had to step in twice ("no redesign", then "only the flagged bit"). A `render` scope on the ledger row and `brief` at the top of each brief would have kept them to pictures.

A third failure (20 Nov 2026): the user flagged floating wires in a Dancer render. The CAD thread fixed that machine, added a wire check to the CAD skill, found and fixed the same fault on all 24 machines, and pushed the skill. Then it said "re-rendering now, a few hours, then the page gets the new pictures" and went quiet, while the page thread waited to be told the renders were done. The fix was real but not live, nothing was logged, and the user only learned any of it by asking. A ledger row with a done-check ("the Dancers page shows the new renders"), a `wait` plus a scheduled wake-up on the CAD thread, a `handoff` to the page thread, and the coordinator's `due` check would each have carried it to the live page and told the user without being asked.

Rules 1 to 7 each break those chains: a ledger row would have shown the ask, a park would have told the user, `stale` would have flagged it after two hours, and a search would have stopped the denial.

## Keep this skill improving
When an ask gets lost, parked, denied or over-scoped again, add the failure to the worked failures above, tighten the rule or the script that should have stopped it, and add a case to `scripts/tests/test_ledger.py` (run it after any change to `ledger.py`). Then publish the skill.
