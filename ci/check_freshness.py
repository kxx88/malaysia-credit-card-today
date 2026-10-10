#!/usr/bin/env python3
"""Guard rails for the published page.

Usage:  python3 ci/check_freshness.py index.html [--stale]
 always:   page parses, offers are not ended, ids are unique, no bare-% headlines, page under 2 MB
 on push:  compares with the previous commit: total offers must not fall more than 15%, and no bank with 20+ offers may lose more than 40%
 --stale:  (scheduled run) the data date must be today or yesterday in Kuala Lumpur, otherwise the daily update did not run
Exit code 1 on any problem; GitHub then emails the failed run to the repository owner.
"""
import datetime, json, re, subprocess, sys

path = sys.argv[1] if len(sys.argv) > 1 else "index.html"
stale_mode = "--stale" in sys.argv
ARR = ("dining", "movies", "travel", "signup", "shopping", "extra")
def load(text):
    i = text.index("var DB = ") + 9; j = text.index(";\n", i)
    return json.loads(text[i:j].replace("\\u003c", "<"))
problems = []
raw = open(path, encoding="utf-8").read()
try:
    db = load(raw)
except Exception as e:
    sys.exit("FAIL  the page data could not be read: %s" % e)
P = [p for a in ARR for p in db.get(a, [])]
kl = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=8)
print("data date %s (updated %s) | %d offers | page %d KB | Kuala Lumpur now %s" % (db["meta"].get("date"), db["meta"].get("updated"), len(P), len(raw) // 1024, kl.strftime("%d %b %H:%M")))
if len(P) < 500: problems.append("only %d offers on the page" % len(P))
if len(raw) > 2 * 1024 * 1024: problems.append("page is %d KB (limit 2048)" % (len(raw) // 1024))
today = kl.date()
ended = [p for p in P if p.get("e") and datetime.date.fromisoformat(p["e"]) < today - datetime.timedelta(days=2)]
if ended: problems.append("%d offers that ended more than 2 days ago are still listed (e.g. %s)" % (len(ended), ended[0]["t"][:40]))
ids = [p.get("id") for p in P]
if not all(ids) or len(set(ids)) != len(ids): problems.append("offer ids are missing or not unique")
bare = [p for p in P if re.fullmatch(r"\d{1,3}%", p.get("v", ""))]
if bare: problems.append("%d bare percentage headlines" % len(bare))
try:
    d0 = datetime.datetime.strptime(db["meta"]["date"], "%d %b %Y").date()
    if stale_mode and (today - d0).days > 1:
        problems.append("data is from %s, %d days old: the daily update did not run" % (db["meta"]["date"], (today - d0).days))
except Exception:
    problems.append("meta.date is missing or unreadable")
if not stale_mode:  # compare with the previous commit of the same file
    try:
        prev = load(subprocess.run(["git", "show", "HEAD~1:" + path], capture_output=True, text=True, check=True).stdout)
        Q = [p for a in ARR for p in prev.get(a, [])]
        print("previous commit: %d offers" % len(Q))
        if Q and len(P) < 0.85 * len(Q): problems.append("offers fell from %d to %d (more than 15%%)" % (len(Q), len(P)))
        now, before = [dict(), dict()]
        for src, dst in ((P, now), (Q, before)):
            for p in src: dst[p["b"]] = dst.get(p["b"], 0) + 1
        for b, n in sorted(before.items()):
            if n >= 20 and now.get(b, 0) < 0.6 * n: problems.append("%s fell from %d to %d offers" % (b, n, now.get(b, 0)))
    except Exception as e:
        print("note: no previous commit to compare with (%s)" % str(e).splitlines()[0][:60])
for pr in problems: print("FAIL  " + pr)
print("OK, all guard rails passed" if not problems else "\n%d problem(s)" % len(problems))
sys.exit(1 if problems else 0)
