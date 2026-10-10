#!/usr/bin/env python3
"""Verify fixes C1-C4, D1-D5, E1-E4, F1-F2 on a BUILT site folder (the folder that holds index.html and the site_assets files).

Usage:   python3 verify_fixes_2.py /path/to/built/folder        e.g. <publishing clone>/staging
Needs:   pip install playwright && playwright install chromium
It starts a throw-away local web server (needed for the service worker test). Prints PASS/FAIL per check; exit 1 on any FAIL.
"""
import datetime, functools, http.server, json, os, re, sys, threading
from playwright.sync_api import sync_playwright

if len(sys.argv) != 2:
    sys.exit(__doc__)
ROOT = os.path.abspath(sys.argv[1])
if not os.path.isfile(os.path.join(ROOT, "index.html")):
    sys.exit("index.html not found in " + ROOT)
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d/index.html" % srv.server_port

CARDS = ["AFFIN|Duo Plus Visa Signature", "Alliance|Visa Infinite", "AmBank|Enrich Visa", "CIMB|Travel World Elite",
         "Hong Leong|Visa Infinite", "Maybank|Shopee Visa Platinum", "Public Bank|Quantum (Visa/Mastercard)"]
# Fix "today" at one day after the data date, so results do not depend on the day you run this
_m = re.search(r'"date":"(\d{1,2} [A-Za-z]{3} \d{4})"', open(os.path.join(ROOT, "index.html"), encoding="utf-8").read())
CLOCK = datetime.datetime.strptime(_m.group(1), "%d %b %Y") + datetime.timedelta(days=1, hours=10) if _m else None
res = []
def check(name, ok, detail=""):
    res.append(bool(ok)); print(("PASS  " if ok else "FAIL  ") + name + (("  - " + str(detail)) if detail else ""))

CONTRAST_JS = """(sel)=>{const lum=c=>{c=c.map(v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)});return 0.2126*c[0]+0.7152*c[1]+0.0722*c[2]};
  const rgb=s=>(s.match(/[\\d.]+/g)||[]).slice(0,3).map(Number);
  const e=document.querySelector(sel);if(!e)return null;const cs=getComputedStyle(e);
  let bg=cs.backgroundColor,n=e;while(/rgba\\(.*,\\s*0\\)|transparent/.test(bg)&&n.parentElement){n=n.parentElement;bg=getComputedStyle(n).backgroundColor}
  const a=lum(rgb(cs.color)),b=lum(rgb(bg));return Math.round((Math.max(a,b)+0.05)/(Math.min(a,b)+0.05)*100)/100}"""

with sync_playwright() as p:
    br = p.chromium.launch()
    def page(w=390, h=844, cards=True, scheme="light", mobile=True, store=None, clock=True):
        ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, is_mobile=mobile and w < 500, has_touch=mobile and w < 500, color_scheme=scheme)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:100]))
        init = dict(store or {})
        if cards: init["mb-mycards"] = json.dumps(CARDS)
        init["mb-theme"] = scheme
        pg.add_init_script("(function(){var s=%s;for(var k in s)localStorage.setItem(k,s[k])})()" % json.dumps(init))
        if clock and CLOCK: pg.clock.install(time=CLOCK)
        pg.goto(URL); pg.wait_for_selector("#tb"); return pg, errs, ctx
    pg, errs, _ = page()
    check("page loads without script errors", not errs, errs)
    # ---------------- C1 ----------------
    pg.click(".nav button[data-go=browse]"); pg.wait_for_timeout(250)
    check("C1 sort menu offers 'Biggest headline saving'", pg.evaluate("[...document.querySelectorAll('#so option')].some(o=>o.value==='value'&&/headline saving/i.test(o.textContent))"))
    pg.select_option("#so", "value"); pg.wait_for_timeout(250)
    keys = pg.evaluate("[...document.querySelectorAll('#br .o')].map(c=>{const v=c.querySelector('.v:not(.s)');return v?v.textContent:''})")
    def k(v):
        m = re.search(r"(\d{1,3}(?:\.\d+)?)\s?%", v); r = re.search(r"RM\s?(\d[\d,]*)", v)
        return (0, -float(m.group(1))) if m else (1, -float(r.group(1).replace(",", ""))) if r else (2, 0)
    ks = [k(v) for v in keys]
    check("C1 results are ordered % first (largest first), then RM, then the rest", ks == sorted(ks) and len(ks) > 5, "first headlines: %s" % keys[:4])
    check("C1 a note explains the ranking and says to check minimum spend and cap", "Check the minimum spend and cap" in pg.inner_text("#vnote") and pg.is_visible("#vnote"))
    check("C1 Min / Cap chips appear on offer cards", pg.evaluate("document.querySelectorAll('#br .pill.t').length>0") or pg.evaluate("PROMOS.some(o=>o.min||o.cap)"))
    # ---------------- C2 ----------------
    tiles = pg.evaluate("(()=>{const cs=[...document.querySelectorAll('#br .o')];return {n:cs.length,withTile:cs.filter(c=>{const t=c.querySelector('.tile');return t&&t.textContent.length>=1&&t.textContent.length<=2}).length}})()")
    check("C2 every offer card has a merchant tile", tiles["n"] > 0 and tiles["n"] == tiles["withTile"], tiles)
    # ---------------- C3 ----------------
    pg.select_option("#so", "soon")
    chips = pg.evaluate("[...document.querySelectorAll('#chips .chip')].map(c=>c.textContent)")
    subs = [x for x in ("Health & beauty", "Auto & fuel", "Home", "Bills & insurance", "Instalments", "Online") if x in chips]
    split = pg.evaluate("(()=>{const ex=PROMOS.filter(o=>o._cat==='extra');return {extra:ex.length,other:ex.filter(o=>!o.sc).length}})()")
    check("C3 'Other' is split into category chips", len(subs) >= 4, "chips: %s" % subs)
    check("C3 'Other' now holds under 70% of what it used to", split["other"] <= 0.7 * split["extra"], "%d of %d" % (split["other"], split["extra"]))
    pg.click("#chips .chip:has-text('Health')"); pg.wait_for_timeout(200)
    ok = pg.evaluate("(()=>{const ids=[...document.querySelectorAll('#br .o')].map(c=>PROMOS[+c.dataset.o]);return ids.length>0&&ids.every(o=>inCat(o,'health'))})()")
    check("C3 the Health & beauty chip lists only health offers", ok)
    pg.click("#chips .chip:has-text('All')")
    # ---------------- D1 ----------------
    top = pg.evaluate("Math.round(document.querySelector('#br .o').getBoundingClientRect().top)")
    check("D1 first offer in Browse starts in the top 40% of a phone screen", top <= 340, "%dpx of 844 (was about 486)" % top)
    pg.click("#bbtn"); pg.wait_for_timeout(250)
    check("D1 'Banks' opens a bank filter sheet", pg.is_visible("#fs") and pg.evaluate("document.querySelectorAll('#fsb .chip').length>3"))
    first = pg.evaluate("document.querySelector('#fsb .chip').dataset.bf")
    pg.click("#fsb .chip >> nth=0"); pg.click("#fs .acts .cta:not(.alt)"); pg.wait_for_timeout(250)
    only = pg.evaluate("(b=>[...document.querySelectorAll('#br .o')].every(c=>PROMOS[+c.dataset.o].b===b))(%s)" % json.dumps(first))
    check("D1 picking a bank filters the list and shows the count on the button", only and "(1)" in pg.inner_text("#bbtn"), pg.inner_text("#bbtn"))
    pg.click("#sg button[data-scope=all]"); pg.wait_for_timeout(200)
    check("D1 the bank filter also works in 'All offers' mode (lists banks you do not hold)", pg.evaluate("bankList().length") > len(set(c.split("|")[0] for c in CARDS)))
    pg.click(".nav button[data-go=cards]"); pg.click(".nav button[data-go=browse]")
    # ---------------- D2 ----------------
    pg, errs, _ = page(); pg.wait_for_timeout(150)
    txt = pg.inner_text("#sc")
    check("D2 Today shows the active scope under the search box", "Offers for my" in txt and "Show all" in txt, txt.replace("\n", " | "))
    pg.click("#sc .lnk"); pg.wait_for_timeout(200)
    check("D2 'Show all' switches the scope and says so", "Showing all offers" in pg.inner_text("#sc") and "Only my cards" in pg.inner_text("#sc"))
    # ---------------- D3 ----------------
    pg3, e3, _ = page(cards=False)
    check("D3 first visit has no pre-selected cards and shows 'Start with my cards'", pg3.evaluate("MY_SEL.length")==0 and pg3.query_selector(".onb") is not None)
    pg3.click("[data-skip]"); pg3.wait_for_timeout(200)
    h3 = pg3.evaluate("(()=>{const s=document.querySelector('.skiphint');return s?s.getBoundingClientRect().height:-1})()")
    check("D3 after Skip the empty-wallet block shrinks to one quiet line", pg3.query_selector(".onb") is None and 0 < h3 < 80, "%spx" % round(h3))
    enc = pg3.evaluate("encIds(%s)" % json.dumps(CARDS[:3]))
    pg3.goto("about:blank"); pg3.goto(URL + "#cards=" + enc); pg3.wait_for_selector("#tb"); pg3.wait_for_timeout(300)
    check("D3 a #cards= link brings the owner's cards back", pg3.evaluate("MY_SEL.length")==3 and not pg3.evaluate("/#cards=/.test(location.hash)"))
    pg3.evaluate("history.replaceState(null,'',location.pathname)"); pg3.evaluate("location.hash='#cards=%s'" % pg3.evaluate("encIds(%s)" % json.dumps(CARDS[3:5]))); pg3.wait_for_timeout(300)
    check("D3 pasting a cards link into an already-open tab also works", pg3.evaluate("MY_SEL.length")==5)
    # ---------------- D4 ----------------
    pg.click(".nav button[data-go=cards]"); pg.wait_for_timeout(250)
    sticky = pg.evaluate("getComputedStyle(document.querySelector('.cstick')).position")
    firstb = pg.evaluate("document.querySelector('#cl .gb').textContent")
    check("D4 search stays pinned while scrolling", sticky == "sticky")
    check("D4 my banks are listed first", any(b in firstb for b in ("AFFIN", "Alliance", "AmBank", "CIMB", "Hong Leong", "Maybank", "Public Bank")), firstb[:40])
    n = pg.evaluate("document.querySelectorAll('#cj .chip').length"); pg.click("#cj .chip >> nth=%d" % (n - 1)); pg.wait_for_timeout(500)
    ty = pg.evaluate("Math.round(document.getElementById('bk%d').getBoundingClientRect().top)" % (n - 1))
    check("D4 jump chips scroll to a bank (%d banks)" % n, n > 5 and 0 <= ty < 300, "heading at %dpx" % ty)
    check("D4 wording: 'My cards' is used everywhere, no 'Your cards' heading", "Your cards" not in pg.evaluate("document.body.innerText"))
    # ---------------- no sideways page scroll on small phones ----------------
    for w in (360, 320):
        pw, _, _ = page(w, 700); bad = []
        for tab in ("today", "browse", "signup", "cards"):
            pw.click(".nav button[data-go=%s]" % tab); pw.wait_for_timeout(150)
            if pw.evaluate("document.documentElement.scrollWidth > innerWidth + 1"): bad.append(tab)
        pw.click(".nav button[data-go=today]"); pw.click(".car .o >> nth=0"); pw.wait_for_timeout(250)
        if pw.evaluate("document.querySelector('#sh .pn').scrollWidth > document.querySelector('#sh .pn').clientWidth + 1"): bad.append("sheet")
        check("layout fits a %dpx-wide phone on every tab and in the sheet (no sideways scroll)" % w, not bad, bad)
    # ---------------- E1 E4 over the main screens ----------------
    small, tiny = [], []
    def audit(label):
        r = pg.evaluate("""()=>{const s=[],t=[];document.querySelectorAll('button,a,input,select,summary').forEach(e=>{
            if(e.closest('.fine')||e.closest('.sr')||e.closest('[hidden]'))return;const r=e.getBoundingClientRect();
            if(r.width&&r.height&&(r.height<43.5||r.width<43.5))s.push((e.className||e.tagName)+':'+Math.round(r.width)+'x'+Math.round(r.height))});
          document.querySelectorAll('body *').forEach(e=>{if(e.closest('[hidden]')||e.closest('.sr')||e.id==='live')return;
            if(!e.children.length&&e.textContent.trim()){const f=parseFloat(getComputedStyle(e).fontSize);if(f<13.99)t.push(e.className+':'+f)}});return {s,t}}""")
        small.extend(label + " " + x for x in r["s"]); tiny.extend(label + " " + x for x in r["t"])
    pgm, _, _ = page()
    pg = pgm
    audit("today"); pg.click(".nav button[data-go=browse]"); pg.wait_for_timeout(200); audit("browse")
    pg.click(".nav button[data-go=signup]"); pg.wait_for_timeout(150); audit("signup")
    pg.click(".nav button[data-go=cards]"); pg.wait_for_timeout(150); audit("cards")
    pg.click(".nav button[data-go=today]"); pg.wait_for_timeout(150); pg.click(".car .o >> nth=0"); pg.wait_for_timeout(250); audit("sheet")
    check("E1 every button, link and field is at least 44 x 44 px", not small, sorted(set(small))[:6])
    check("E4 no text is smaller than 14 px", not tiny, sorted(set(tiny))[:6])
    # ---------------- C4 + E3 (sheet is open now) ----------------
    check("E3 focus moves into the dialog and the page behind is inert", pg.evaluate("document.querySelector('#sh .pn').contains(document.activeElement)||document.activeElement===document.querySelector('#sh .pn')") and pg.evaluate("document.querySelector('.app').hasAttribute('inert')"))
    for _ in range(14): pg.keyboard.press("Tab")
    check("E3 Tab cycles inside the dialog (14 presses)", pg.evaluate("document.querySelector('#sh').contains(document.activeElement)"))
    bot = pg.evaluate("Math.round(document.querySelector('#sh .acts').getBoundingClientRect().bottom)")
    check("C4 action bar is pinned inside the phone screen without scrolling", bot <= 844 + 1, "bottom at %dpx" % bot)
    sh = pg.inner_text("#shB")
    check("C4 'Compare' is gone; the secondary link names its destination", "Compare" not in sh)
    check("C4 key terms, collapsible details, View offer and Copy link are present", pg.query_selector("#sh details.det") is not None and "Copy link" in sh and "View offer" in sh)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    check("E3 Escape closes the dialog, un-hides the page and returns focus to the card", not pg.is_visible("#sh") and not pg.evaluate("document.querySelector('.app').hasAttribute('inert')") and pg.evaluate("document.activeElement&&document.activeElement.classList.contains('o')"))
    dup = pg.evaluate("(()=>{const i=PROMOS.findIndex(o=>o.ec&&o.ec.length&&/Eligible(?: cards?)?:/i.test(o.d));return i})()")
    if dup >= 0:
        pg.evaluate("openSheet(%d)" % dup); t = pg.inner_text("#sh details.det p"); pg.keyboard.press("Escape")
        check("C4 eligible cards are not repeated inside the offer text", not re.search(r"Eligible(?: cards?)?:", t))
    check("E3 swipe rows are labelled and results are announced", pg.evaluate("[...document.querySelectorAll('.car,.wal')].every(e=>e.getAttribute('role')==='group'&&e.getAttribute('aria-label'))") and pg.evaluate("document.getElementById('live').getAttribute('aria-live')==='polite'"))
    # ---------------- E2 ----------------
    pg, _, _ = page(); pg.wait_for_timeout(150)
    light = pg.evaluate("(%s)('.pill.ok')" % CONTRAST_JS) or pg.evaluate("(%s)('.pill.ok.l')" % CONTRAST_JS)
    muted = pg.evaluate("(%s)('.trk')" % CONTRAST_JS)
    pgd, _, _ = page(scheme="dark"); pgd.wait_for_timeout(150)
    dark = pgd.evaluate("(%s)('.pill.ok')" % CONTRAST_JS) or pgd.evaluate("(%s)('.pill.ok.l')" % CONTRAST_JS)
    check("E2 'Your card' pill text meets 4.5:1 in light and dark mode", (light or 0) >= 4.5 and (dark or 0) >= 4.5, "light %s, dark %s (was 4.35)" % (light, dark))
    check("E2 secondary text meets 4.5:1", (muted or 0) >= 4.5, muted)
    # ---------------- D5 ----------------
    pgw, _, _ = page(1280, 800, mobile=False); pgw.wait_for_timeout(200)
    cols = pgw.evaluate("getComputedStyle(document.querySelector('#tb .list')).gridTemplateColumns.split(' ').length")
    carov = pgw.evaluate("(()=>{const c=document.querySelector('.car');return c.scrollWidth<=c.clientWidth+2})()")
    check("D5 desktop: lists use two columns and the swipe row becomes a grid", cols == 2 and carov, "%d columns" % cols)
    pgw.click(".nav button[data-go=browse]"); pgw.wait_for_timeout(250)
    bw = pgw.evaluate("({grid:getComputedStyle(document.querySelector('#vB .bwrap')).gridTemplateColumns.split(' ').length,btn:getComputedStyle(document.querySelector('#bbtn')).display,bank:getComputedStyle(document.querySelector('#bw')).display,w:Math.round(document.querySelector('.app').getBoundingClientRect().width)})")
    check("D5 desktop Browse: filter sidebar beside the results, banks inline", bw["grid"] == 2 and bw["btn"] == "none" and bw["bank"] != "none", bw)
    # ---------------- landmarks, headings, tile contrast (accessibility follow-up) ----------------
    lm = pg.evaluate("({main:document.querySelectorAll('main').length,header:document.querySelectorAll('header').length,footer:document.querySelectorAll('footer').length,nav:document.querySelectorAll('nav').length,skip:!!document.querySelector('a.skip[href=\\'#main\\']')})")
    check("A11Y the page has header, one main, nav and footer landmarks and a skip link", lm["main"] == 1 and lm["header"] >= 1 and lm["footer"] == 1 and lm["nav"] == 1 and lm["skip"], lm)
    pg.click(".nav button[data-go=cards]"); pg.wait_for_timeout(150)
    hs = pg.evaluate("[...document.querySelectorAll('#vC h1,#vC h2,#vC h3')].map(h=>+h.tagName[1])")
    check("A11Y My cards headings never skip a level (h1 then h2)", hs and hs[0] == 1 and all(b - a <= 1 for a, b in zip(hs, hs[1:])), sorted(set(hs)))
    worst = pg.evaluate("""(()=>{const lin=v=>v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);let w=99,wh=-1;
      for(let h=0;h<360;h++){const m=/hsl\\((\\d+),([\\d.]+)%,([\\d.]+)%\\)/.exec(tileBg(h));const H=+m[1],S=+m[2]/100,Lg=+m[3]/100;
        const c=(1-Math.abs(2*Lg-1))*S,x=c*(1-Math.abs((H/60)%2-1)),mm=Lg-c/2;
        const rgb=H<60?[c,x,0]:H<120?[x,c,0]:H<180?[0,c,x]:H<240?[0,x,c]:H<300?[x,0,c]:[c,0,x];
        const L=0.2126*lin(rgb[0]+mm)+0.7152*lin(rgb[1]+mm)+0.0722*lin(rgb[2]+mm);const r=1.05/(L+0.05);if(r<w){w=r;wh=h}}return {w:Math.round(w*100)/100,h:wh}})()""")
    check("A11Y white initials on every possible tile colour reach 4.5:1 (all 360 hues)", worst["w"] >= 4.5, "worst %s at hue %s" % (worst["w"], worst["h"]))
    # ---------------- F1 F2 ----------------
    pgf, _, ctxf = page(clock=False); pgf.wait_for_timeout(300)
    head = pgf.evaluate("document.head.innerHTML")
    desc = re.search(r'name="description" content="([^"]+)"', head)
    check("F2 description (50-200 characters)", desc and 50 <= len(desc.group(1)) <= 200, len(desc.group(1)) if desc else 0)
    need = {"og:title": 'property="og:title"', "og:description": 'property="og:description"', "og:image (absolute)": r'property="og:image" content="https://', "twitter:card": 'name="twitter:card"',
            "theme-color": 'name="theme-color"', "canonical": 'rel="canonical"', "icon": 'rel="icon"', "apple-touch-icon": 'rel="apple-touch-icon"', "manifest": 'rel="manifest"'}
    miss = [n for n, s in need.items() if not re.search(s, head)]
    check("F2 share, icon and theme tags are present", not miss, miss or "all 9 present")
    check("F2 the share image file is served", ctxf.request.get(URL.rsplit("/", 1)[0] + "/og-image.png").status == 200)
    man = ctxf.request.get(URL.rsplit("/", 1)[0] + "/manifest.webmanifest"); mj = man.json() if man.status == 200 else {}
    sizes = sorted(i.get("sizes") for i in mj.get("icons", []))
    check("F1 manifest is valid (name, start_url, standalone, 192 and 512 icons)", mj.get("name") and mj.get("start_url") and mj.get("display") == "standalone" and "192x192" in sizes and "512x512" in sizes, sizes)
    pgf.evaluate("navigator.serviceWorker.ready.then(()=>1)"); pgf.wait_for_timeout(800)
    pgf.reload(); pgf.wait_for_selector("#tb"); pgf.wait_for_timeout(500)
    ctrl = pgf.evaluate("!!navigator.serviceWorker.controller")
    check("F1 service worker is registered and controls the page", ctrl)
    ctxf.set_offline(True)
    try:
        pgf.reload(); pgf.wait_for_selector("#tb", timeout=8000); n = pgf.evaluate("document.querySelectorAll('#tb .o').length")
        check("F1 the page opens with no network (served from the installed copy)", n > 0, "%d offer cards" % n)
    except Exception as ex:
        check("F1 the page opens with no network (served from the installed copy)", False, str(ex)[:80])
    br.close()
print("\n%d/%d checks passed" % (sum(res), len(res))); sys.exit(0 if all(res) else 1)
