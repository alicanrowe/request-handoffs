---
name: request-handoffs
description: Use in any multi-thread project (a coordinator plus work threads) whenever a user ask is routed, accepted, parked, delivered, or questioned ("where is X?", "did X ever reach you?"). Keeps a shared request ledger so no ask is silently dropped, parked without telling the user, or denied without a search.
metadata:
  author: Alican Rowe (@alicanrowe)
---

# Request handoffs

A project has one coordinator and many threads. Asks get lost in three places: when they are routed, when a thread quietly puts them behind newer work, and when someone answers "nobody asked for that" from memory. Asks also grow: a brief turns "match the pictures" into "redesign". This skill closes all four with one shared ledger and five rules.

## The ledger
- One JSON-lines file in the project's shared folder, shared by every thread and the coordinator. Set `REQUEST_LEDGER` to its path, or pass `--ledger`. The default is `request-ledger/ledger.jsonl` under the shared folder (`$PROJECT_FILES`, otherwise the current folder).
- `scripts/ledger.py` reads and writes it. Standard library only.
- One row per ask: the user's message id and words, the owner thread, where the result is to be delivered, status, ETA, and a history of every change.

```
python3 scripts/ledger.py add --msg <user msg id> --text "<user's words>" --owner "<thread title>" --owner-id <thread id> --deliver "<where>" --scope render|tweak|redesign|new|info [--keep "<what must not change>"] [--from-project <source project>]
python3 scripts/ledger.py brief <rid>            # the user's words, scope and keep-list, to paste at the top of a brief
python3 scripts/ledger.py scope <rid> --to tweak --msg <id of the user's message that changed it>
python3 scripts/ledger.py accept <rid> --eta "2:00-3:30 PM ET"
python3 scripts/ledger.py park <rid> --reason "<what jumped ahead>" --eta "<new range>" --told <msg id of the message telling the user>
python3 scripts/ledger.py resume <rid> --eta "<range>"
python3 scripts/ledger.py deliver <rid> --where "<message id or file>"
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

## Delivering
Standing rule from the user (18 Nov 2026): merge pull requests when they are ready, without asking. A thread that opened a PR merges it once its checks pass and the result has been looked at, then reports it as done with the link. Merging is not a reason to park or wait for a reply. The scope rule still holds: a PR that goes beyond the user's words is reported, not merged.

When the result goes out, run `deliver` with the message or file, and post it where `--deliver` says. If the user asked for it to come back to the project chat, the owner thread sends it to the coordinator to relay, not just to its own thread.

## Worked failure (why this exists)
A user asked the coordinator, in three messages a few minutes apart, to redesign a case piece's tools, tool stands, handle and outside inlays in the style of a jewelry line, and to "bring them to this thread". The coordinator routed all three to the case thread correctly, and the case thread put them on its checklist. Within 15 minutes the user asked for a build-book audit, then spent two hours at the shop asking for cut lists. The case thread did that work, left the design lines as "not started" (one quietly marked "paused for the book"), and never told the user. Two hours later the user asked "did the redesign never make it from the jewelry thread?". The case thread answered "no, it never got to me", and the coordinator, after the jewelry thread said it hadn't made it, told the case thread "nothing was lost, it was never made". Both answers were wrong: the ask had been on the case thread's own checklist the whole time.

A second failure the same day: the user asked for eight sawhorses' close-ups and sheet layout to match a ninth. The briefs said "bring to the same level", and threads started redesigning parts. The user had to step in twice ("no redesign", then "only the flagged bit"). A `render` scope on the ledger row and `brief` at the top of each brief would have kept them to pictures.

Rules 1 to 5 each break those chains: a ledger row would have shown the ask, a park would have told the user, `stale` would have flagged it after two hours, and a search would have stopped the denial.

## Keep this skill improving
When an ask gets lost, parked, denied or over-scoped again, add the failure to the worked failures above, tighten the rule or the script that should have stopped it, and add a case to `scripts/tests/test_ledger.py` (run it after any change to `ledger.py`). Then publish the skill.
