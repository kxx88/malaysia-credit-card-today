#!/usr/bin/env python3
"""Automated accessibility scan (axe-core) of the built site: every tab and the offer sheet, light and dark mode, on a phone-sized screen.

Usage:  python3 ci/axe_scan.py <folder with index.html>
Needs:  pip install playwright && playwright install chromium ; npm install --no-save axe-core   (or set AXE_PATH to axe.min.js)
Fails (exit 1) on any serious or critical problem. Moderate and minor ones are printed as warnings.
"""
import functools, http.server, json, os, sys, threading
from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
AXE = os.environ.get("AXE_PATH", "node_modules/axe-core/axe.min.js")
if not os.path.isfile(AXE):
    sys.exit("axe-core not found at %s (run: npm install --no-save axe-core)" % AXE)
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d/index.html" % srv.server_port
CARDS = ["AFFIN|Duo Plus Visa Signature", "Alliance|Visa Infinite", "AmBank|Enrich Visa", "CIMB|Travel World Elite", "Hong Leong|Visa Infinite", "Maybank|Shopee Visa Platinum", "Public Bank|Quantum (Visa/Mastercard)"]
TAGS = ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa", "best-practice"]
found = {}
with sync_playwright() as p:
    br = p.chromium.launch()
    for scheme in ("light", "dark"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True, has_touch=True, color_scheme=scheme)
        pg = ctx.new_page(); pg.route("**/*", lambda r: r.continue_() if r.request.url.startswith("http://127") else r.abort())
        pg.add_init_script("localStorage.setItem('mb-mycards',%s);localStorage.setItem('mb-theme','%s')" % (json.dumps(json.dumps(CARDS)), scheme))
        pg.goto(URL); pg.wait_for_selector("#tb"); pg.add_script_tag(path=AXE)
        def scan(label):
            for v in pg.evaluate("axe.run(document,{runOnly:{type:'tag',values:%s}}).then(r=>r.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,n:v.nodes.length,ex:v.nodes[0].target.join(' ').slice(0,80)})))" % json.dumps(TAGS)):
                found.setdefault(v["id"], dict(v, where=set()))["where"].add("%s/%s" % (scheme, label))
        scan("today")
        for tab in ("browse", "signup", "cards"):
            pg.click(".nav button[data-go=%s]" % tab); pg.wait_for_timeout(200); scan(tab)
        pg.click(".nav button[data-go=today]"); pg.wait_for_timeout(150); pg.click(".car .o >> nth=0"); pg.wait_for_timeout(250); scan("sheet")
        pg.keyboard.press("Escape"); pg.click(".nav button[data-go=browse]"); pg.click("#bbtn"); pg.wait_for_timeout(250); scan("bank-sheet")
    br.close()
bad = [v for v in found.values() if v["impact"] in ("serious", "critical")]
for v in sorted(found.values(), key=lambda v: v["impact"] or ""):
    print("%s  [%s] %s: %s (%d elements, e.g. %s) on %s" % ("FAIL" if v in bad else "warn", v["impact"], v["id"], v["help"], v["n"], v["ex"], ", ".join(sorted(v["where"]))))
print("\n%d accessibility problem(s), %d serious or critical" % (len(found), len(bad)))
sys.exit(1 if bad else 0)
