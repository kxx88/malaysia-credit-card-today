#!/usr/bin/env python3
"""Verify fixes A1-A6 and B1-B4 on a BUILT page (the index.html the build produces).

Usage:   python3 verify_fixes.py /path/to/built/index.html
Needs:   pip install playwright && playwright install chromium   (Chromium only, no network access needed)
Output:  one PASS/FAIL line per check; exit code 1 if anything fails.
Date-independent: the browser clock is set relative to the page's own data date (DB.meta.date).
"""
import datetime, json, re, sys
from playwright.sync_api import sync_playwright

if len(sys.argv) != 2:
    sys.exit(__doc__)
URL = "file://" + __import__("os").path.abspath(sys.argv[1])
CARDS = ["AFFIN|Duo Plus Visa Signature", "Alliance|Visa Infinite", "AmBank|Enrich Visa", "CIMB|Travel World Elite",
         "Hong Leong|Visa Infinite", "Maybank|Shopee Visa Platinum", "Public Bank|Quantum (Visa/Mastercard)"]
res = []
def check(name, ok, detail=""):
    res.append(ok); print(("PASS  " if ok else "FAIL  ") + name + (("  - " + str(detail)) if detail else ""))

def block(r):
    r.continue_() if r.request.url.startswith("file:") else r.abort()

with sync_playwright() as p:
    br = p.chromium.launch()
    def page(clock=None):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        pg = ctx.new_page(); pg.route("**/*", block); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:100]))
        pg.add_init_script("localStorage.setItem('mb-mycards', %s)" % json.dumps(json.dumps(CARDS)))
        if clock: pg.clock.install(time=clock)
        pg.goto(URL); pg.wait_for_selector("#tb"); return pg, errs
    pg, errs = page()
    # the data date decides what "yesterday", "5 days ago" and "ended" mean, so read it from the page
    mdate = pg.evaluate("DB.meta.date"); d0 = datetime.datetime.strptime(mdate, "%d %b %Y")
    at = lambda days: d0 + datetime.timedelta(days=days, hours=10)
    check("page loads without script errors", not errs, errs)
    pg, _ = page(at(1))
    x1 = pg.evaluate("document.querySelector('.car .o').getBoundingClientRect().left")
    x2 = pg.evaluate("document.querySelector('.wal .cf').getBoundingClientRect().left")
    check("A1 swipe rows start at the 18px page padding", x1 >= 16 and x2 >= 16, "card x=%d, wallet x=%d (broken = 0)" % (x1, x2))
    m = pg.evaluate("""()=>{const abbr=/\\b(?:St|Dr|Mr|Mrs|Ms|Jr|Sr|No|Nos|Jln|Sdn|Bhd|Co|Ltd|Inc|vs|Tel|Hj|Hjh)\\.$/i;let cut=0,bare=0,rep=0,pv=0;
      PROMOS.forEach(o=>{const v=benefitOf(o);if(/^\\d{1,3}%$/.test(v))bare++;
        if(!v){const s=previewOf(o);if(s){pv++;if(abbr.test(s))cut++;const nt=norm(o.t),ns=norm(s);if(ns&&(nt.indexOf(ns)===0||ns===nt))rep++}}});
      return {cut,bare,rep,pv}}""")
    check("A3 no preview is cut at an abbreviation (St., Dr., No. ...)", m["cut"] == 0, "%d of %d previews" % (m["cut"], m["pv"]))
    check("A4 no bare '15%' headlines", m["bare"] == 0, m["bare"])
    check("A6 a preview never repeats the title", m["rep"] == 0, m["rep"])
    lv = pg.evaluate("(()=>{const c={confirmed:0,likely:0};PROMOS.forEach(o=>{if(o._cat!=='signup'){const l=fitLevel(o);if(l in c)c[l]++}});return c})()")
    check("B1 two match states exist (confirmed + likely)", lv["likely"] > 0, lv)
    card = pg.evaluate("oh(PROMOS.find(o=>o._cat!=='signup'&&fitLevel(o)==='likely'))")
    check("B1 bank-only match shows 'Likely your card'", "Likely your card" in card)
    pg.evaluate("openSheet(PROMOS.findIndex(o=>o._cat!=='signup'&&fitLevel(o)==='likely'))"); sh = pg.inner_text("#shB")
    check("B1 sheet says 'Likely works' and 'Check your card'", "Likely works with your cards" in sh and "Check your card" in sh)
    check("B3 sheet footer: terms, not affiliated, last checked", all(s in sh for s in ("Terms and conditions apply", "not affiliated", "Last checked")))
    href = pg.get_attribute("#shB a.rep", "href") or ""
    check("B3 'Report a problem' link is pre-filled with the offer id", "Offer%20id" in href and "title=" in href, href[:80])
    pg.keyboard.press("Escape")
    pg.evaluate("openSheet(PROMOS.findIndex(o=>o._end==null))"); sh = pg.inner_text("#shB")
    check("B2 sheet explains an unconfirmed end date", "could not confirm" in sh.lower() or "not confirmed" in sh.lower() or "Ongoing" in sh)
    pg.keyboard.press("Escape")
    check("B2 an undated card shows the dashed 'Dates unverified' pill", pg.evaluate("oh(PROMOS.find(o=>o._end==null&&o._cat!=='signup')).includes('pill q')"))
    pg.evaluate("openSheet(PROMOS.findIndex(o=>o._cat==='signup'))"); sh = pg.inner_text("#shB")
    check("A5 sign-up sheet says 'For new customers', never 'Not in your cards'", "For new customers" in sh and "Not in your cards" not in sh)
    pg.keyboard.press("Escape")
    check("A5 sign-up cards never say 'Your card'", pg.evaluate("PROMOS.filter(o=>o._cat==='signup').every(o=>!oh(o).includes('Your card'))"))
    dt = pg.inner_text("#dt"); hh = pg.evaluate("document.querySelector('#dt').getBoundingClientRect().height")
    check("B4 header text is one short line, no clock time", dt.startswith("Updated") and not re.search(r"\d:\d\d", dt) and hh <= 30, "%r, text height %dpx" % (dt, hh))
    check("B4 no stale banner when the data is 1 day old", pg.evaluate("document.querySelector('#stale').hidden"))
    pg5, _ = page(at(5)); b5 = pg5.evaluate("(()=>{const s=document.querySelector('#stale');return s.hidden?'':s.textContent})()")
    check("B4 plain-language banner when the data is 5 days old", "5 days ago" in b5 and "run hasn't landed" not in b5, b5)
    pg20, e20 = page(at(20))
    g = pg20.evaluate("""(()=>{const ended=PROMOS.filter(o=>{const d=endIn(o);return d!=null&&d<0});
      return {ended:ended.length,leak:ended.filter(vis).length,pill:[...document.querySelectorAll('.o .pill')].filter(x=>x.textContent==='Ended').length}})()""")
    pg20.click(".nav button[data-go=browse]"); pg20.wait_for_timeout(300)
    pill2 = pg20.evaluate("[...document.querySelectorAll('#br .pill')].filter(x=>x.textContent==='Ended').length")
    check("A2 ended offers are not listed (clock moved 20 days on)", g["leak"] == 0 and g["pill"] == 0 and pill2 == 0, "%d offers ended by then, %d listed" % (g["ended"], g["leak"]))
    br.close()
print("\n%d/%d checks passed" % (sum(res), len(res))); sys.exit(0 if all(res) else 1)
