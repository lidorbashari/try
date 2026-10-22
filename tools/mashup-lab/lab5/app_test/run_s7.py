"""SPEC §7 checks (energy, new pair score, energy filter, cards, LCD, section plan) + extra screenshots.
usage: APP_TPL=... python3 run_s7.py [stub|real]   (expects build.build() output like run_tests.py)
Python reference implementation below mirrors SPEC §7 literally; JS must match it exactly (parity)."""
import asyncio, json, math, os, random, re, sys
from playwright.async_api import async_playwright
import build

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "shots")
ENGINE = sys.argv[1] if len(sys.argv) > 1 else "stub"
RESULTS = []


async def tab_click(pg, sel):
    """the tab bar minimises into a circle while scrolling down (iOS 26): a user taps the circle first"""
    await pg.evaluate("window.Liquid && Liquid.tabbar.minimized && Liquid.tabbar.expand()")
    await pg.wait_for_timeout(450)
    await pg.click(sel)

def check(name, ok, info=""):
    RESULTS.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (("  " + str(info)[:400]) if info and not ok else ""))

# ---------------- Python reference (SPEC §4.11 + §7) ----------------
def rhu(x):  # JS Math.round (half up)
    return math.floor(x + 0.5)
def camrel(a, b):
    na, la, nb, lb = int(a[:-1]), a[-1], int(b[:-1]), b[-1]
    if a == b: return "same"
    if la == lb and abs(na - nb) in (1, 11): return "adj"
    if na == nb and la != lb: return "rel"
    return None
def tempo(a, b):
    o = [(abs(a - b) / min(a, b), "1:1"), (abs(a - 2 * b) / min(a, 2 * b), "vhalf"), (abs(2 * a - b) / min(2 * a, b), "vdouble")]
    return sorted(o, key=lambda x: x[0])[0]
def base_score(rel, t):
    s = 100 - t[0] * 100 * 6
    if rel != "same": s -= 6
    if t[1] != "1:1": s -= 6
    return max(0, rhu(s))
EB = dict(techno=8, edm=8, dnb=9, techhouse=8, house=7, afrohouse=6, ukg=7, amapiano=6, afro=6, dancehall=7, regg=7, latin=7, hiphop=6, rnb=4, pop=6, ilpop=5, mizr=6)
def energy(t):
    if t.get("e") not in (None, ""):
        return max(1, min(10, rhu(float(t["e"])))), False
    e = EB.get(t["g"], 6)
    bpm = t["bpm"] * 2 if t["g"] == "dnb" else t["bpm"]
    if bpm >= 128: e += 1
    elif bpm <= 95: e -= 1
    return max(1, min(10, e)), True
VG = {"mizr", "ilpop", "pop", "rnb", "hiphop", "latin", "regg", "afro", "dancehall"}
BG = {"house", "techhouse", "afrohouse", "techno", "edm", "dnb", "ukg", "amapiano"}
def pen(d): return 0 if d <= 1 else 2 if d == 2 else 5 if d == 3 else 9
def score_pair(v, b):
    rel = camrel(v["k"], b["k"])
    if not rel: return None
    t = tempo(v["bpm"], b["bpm"]); base = base_score(rel, t)
    ev, eb = energy(v)[0], energy(b)[0]
    bonus = (2 if v["g"] in VG else 0) + (2 if b["g"] in BG else 0)
    return dict(score=max(0, min(100, rhu(base - pen(abs(ev - eb)) + bonus))), base=base, ev=ev, eb=eb)
def band(e): return "warm" if e <= 5 else "groove" if e <= 7 else "peak"
def find_pairs(data, gv, gb, max_diff=0.06, no_hot=True, same=False, en="all"):
    out = []
    for v in [t for t in data if t["g"] == gv]:
        for b in [t for t in data if t["g"] == gb]:
            if v is b or v["a"].split(",")[0].strip().lower() == b["a"].split(",")[0].strip().lower(): continue
            rel = camrel(v["k"], b["k"])
            if not rel or (same and rel != "same"): continue
            t = tempo(v["bpm"], b["bpm"])
            if t[0] > max_diff + 1e-9: continue
            if no_hot and (v["hot"] or b["hot"]): continue
            sp = score_pair(v, b)
            if en != "all" and band(rhu((sp["ev"] + sp["eb"]) / 2)) != en: continue
            out.append(sp["score"])
    return out

async def new_page(b, w=390, h=844, scheme="light", init=None):
    ctx = await b.new_context(viewport={"width": w, "height": h}, device_scale_factor=3 if w < 800 else 1, color_scheme=scheme, has_touch=w < 800, is_mobile=w < 800)
    pg = await ctx.new_page(); pg.errs = []
    pg.on("console", lambda m: pg.errs.append(m.type + ": " + m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: pg.errs.append("pageerror: " + str(e)))
    await pg.route("**/fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
    await pg.route("**/fonts.gstatic.com/**", lambda r: r.abort())
    if ENGINE == "real":   # real engine: answer the lookup (no match → Studio Groove) instead of aborting, so the console stays clean
        await pg.route("**/itunes.apple.com/**", lambda r: r.fulfill(status=200, content_type="application/json", headers={"Access-Control-Allow-Origin": "*"}, body='{"resultCount":0,"results":[]}'))
    else:
        await pg.route("**/itunes.apple.com/**", lambda r: r.abort())
    if init: await pg.add_init_script(init)
    await pg.goto("file://" + os.path.join(HERE, f"out_{ENGINE}.html")); await pg.wait_for_timeout(700)
    return pg

async def shot(pg, name): await pg.screenshot(path=os.path.join(SHOTS, name + ".png"))

async def main():
    out, dpath, n = build.build(ENGINE)
    data = json.load(open(dpath, encoding="utf-8"))
    print("built", out, n, "tracks from", dpath)
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        pg = await new_page(b)
        has = await pg.evaluate("!!(window.__lab && ['scorePair','energyOf','sectionPlan','findPairs'].every(k => typeof window.__lab[k] === 'function'))")
        check("window.__lab exposes scorePair, energyOf, sectionPlan, findPairs", has)
        # energy parity for every track
        js_e = await pg.evaluate("DATA.map(t => { const x = __lab.energyOf(t); return [x.e, x.est]; })")
        bad = [(t["t"], t["g"], t["bpm"], js_e[i], energy(t)) for i, t in enumerate(data) if tuple(js_e[i]) != energy(t)]
        check(f"energyOf parity on all {len(data)} tracks", not bad, bad[:5])
        # explicit energy beats the estimate
        ex = await pg.evaluate("[__lab.energyOf({g:'rnb', bpm:90, e:9}), __lab.energyOf({g:'dnb', bpm:87}), __lab.energyOf({g:'rnb', bpm:90}), __lab.energyOf({g:'techno', bpm:130})]")
        check("energyOf: source e wins, dnb uses 2× BPM, ≤95 → −1, ≥128 → +1", ex == [{"e": 9, "est": False}, {"e": 10, "est": True}, {"e": 3, "est": True}, {"e": 9, "est": True}], ex)
        # score parity on random pairs (all genres)
        random.seed(7); idx = [(random.randrange(n), random.randrange(n)) for _ in range(4000)]
        js_s = await pg.evaluate("(idx) => idx.map(([a, b]) => { const p = __lab.scorePair(DATA[a], DATA[b]); return p ? [p.score, p.base, p.en.v, p.en.b] : null; })", idx)
        mism = []; cmp = 0
        for (a, bb), js in zip(idx, js_s):
            py = score_pair(data[a], data[bb])
            if (py is None) != (js is None): mism.append((a, bb, py, js)); continue
            if py is None: continue
            cmp += 1
            if js != [py["score"], py["base"], py["ev"], py["eb"]]: mism.append((a, bb, py, js))
        check(f"scorePair parity on {cmp} key-compatible random pairs", not mism and cmp > 300, mism[:4])
        # findPairs counts + score multiset parity incl. energy filter
        for gv, gb, en in (("mizr", "house", "all"), ("afro", "afrohouse", "peak"), ("hiphop", "dnb", "all"), ("ilpop", "techhouse", "groove"), ("rnb", "amapiano", "warm")):
            js = await pg.evaluate("([gv, gb, en]) => __lab.findPairs(gv, gb, {maxDiff: .06, noHot: true, sameKey: false, energy: en}).map(p => p.score).sort((a,b)=>a-b)", [gv, gb, en])
            py = sorted(find_pairs(data, gv, gb, en=en))
            check(f"findPairs parity {gv}/{gb}/{en}: {len(js)} pairs", js == py, [len(js), len(py)])
        # p.base / p.en kept
        k = await pg.evaluate("(() => { const p = MashApp.currentPairs()[0]; return [typeof p.base, Object.keys(p.en).sort().join(',')]; })()")
        check("pairs keep p.base and p.en = {v, b, est}", k == ["number", "b,est,v"], k)
        # energy filter UI
        n_all = await pg.evaluate("MashApp.currentPairs().length")
        res = {}
        for e in ("warm", "groove", "peak", "all"):
            await pg.click(f'#segE [data-e="{e}"]'); await pg.wait_for_timeout(250)
            res[e] = await pg.evaluate("""(() => { const ps = MashApp.currentPairs(); const chips = Array.from(document.querySelectorAll('#list .card .en')).map(c => c.textContent.trim());
                return [ps.length, Number(document.querySelector('#resN').textContent), Array.from(new Set(chips)), ps.every(p => window.__lab.energyBand(window.__lab.pairEnergy(p)) === (document.querySelector('#segE').dataset.e === 'all' ? window.__lab.energyBand(window.__lab.pairEnergy(p)) : document.querySelector('#segE').dataset.e))]; })()""")
            if e == "peak":
                await pg.evaluate("window.scrollTo(0, document.querySelector('#segE').getBoundingClientRect().top + scrollY - 140)"); await pg.wait_for_timeout(400)
                await shot(pg, "30-energy-peak-light")
        words = {"warm": "חימום", "groove": "גרוב", "peak": "שיא"}
        ok = all(res[e][0] == res[e][1] and res[e][3] and (res[e][0] == 0 or res[e][2] == [words[e]]) for e in words) and sum(res[e][0] for e in words) == n_all and res["all"][0] == n_all
        check("energy filter הכל/חימום/גרוב/שיא partitions the list; chips match", ok, res)
        dig = await pg.evaluate("Array.from(document.querySelectorAll('.card .en')).some(c => /\\d/.test(c.textContent))")
        check("energy chips are words only (no digits)", not dig)
        # mixer: LCD energy + section plan
        await pg.locator("#list .card").nth(0).locator('[data-act="both"]').click(); await pg.wait_for_timeout(700)
        await pg.click('#mini [data-act="open-mixer"]'); await pg.wait_for_timeout(900)
        lcd = await pg.evaluate("['A','B'].map(s => document.querySelector('#dk-' + s + ' [data-lcd]').textContent)")
        check("mixer LCD shows E per deck (E8 / E~7)", all(re.search(r"E~?\d+$", x) for x in lcd), lcd)
        exp = await pg.evaluate("['A','B'].map(s => { const t = s === 'A' ? MashApp.loaded.p.v : MashApp.loaded.p.b; const x = __lab.energyOf(t); return 'E' + (x.est ? '~' : '') + x.e; })")
        check("LCD energy equals energyOf()", all(lcd[i].endswith(exp[i]) for i in range(2)), [lcd, exp])
        badge = await pg.evaluate("document.querySelector('#dk-A [data-src]').textContent")
        if ENGINE == "stub": check("Apple source badge carries 'תצוגה מקדימה באדיבות iTunes'", "באדיבות iTunes" in badge, badge)
        plan = await pg.evaluate("""(() => { const pl = document.querySelector('#mixer .plan'); if (!pl) return null;
            return { steps: pl.querySelectorAll('.steps li').length, cues: Array.from(pl.querySelectorAll('.cue')).map(c => c.textContent.trim()), label: pl.querySelector('.plan-tag').textContent,
                     note: pl.querySelector('.plan-note').textContent, sp: __lab.sectionPlan(MashApp.loaded.p) }; })()""")
        ok = plan and plan["steps"] == 5 and all(re.fullmatch(r"[AB] \d+:\d\d", c) for c in plan["cues"]) and "הערכה לפי מבנה טיפוסי של הסגנון: לבדוק באוזן" in plan["label"] and "30 שניות" in plan["note"]
        check("mixer plan: 5 steps, mm:ss cues, honesty label, preview note", ok, plan and {k: plan[k] for k in ("steps", "cues", "label")})
        if plan:
            sp = plan["sp"]; st = sp["steps"]
            # club beat (house) → B enters at bar 33, drop 81; song vocal → A chorus 25, next 49; bar = 240 / synced bpm
            loaded = await pg.evaluate("[MashApp.loaded.p.v.g, MashApp.loaded.p.b.g, MashApp.targets(MashApp.loaded.p)]")
            tg = loaded[2]; barB = 240 / tg["bT"]; barA = 240 / tg["vT"]
            ok = st[1]["barB"] == 33 and abs(st[1]["tB"] - 32 * barB) < 1e-6 and st[1]["barA"] == 25 and abs(st[1]["tA"] - 24 * barA) < 1e-6 and st[3]["barB"] == 81 and abs(st[3]["tB"] - 80 * barB) < 1e-6 and st[3]["barA"] == 49 and abs(st[2]["tB"] - 48 * barB) < 1e-6
            check(f"sectionPlan bars/times for {loaded[0]} over {loaded[1]} (bar = 240/bpm at sync)", ok, st)
        await pg.evaluate("document.querySelector('#mixer').scrollTo(0, 0)"); await pg.wait_for_timeout(400)
        await shot(pg, "31-mixer-top-light")
        await pg.evaluate("document.querySelector('#mixer').scrollTo(0, document.querySelector('#mixer .plan').offsetTop - 60)"); await pg.wait_for_timeout(500)
        await shot(pg, "32-mixer-plan-light")
        sw = await pg.evaluate("[document.documentElement.scrollWidth, document.querySelector('#mixer').scrollWidth, document.querySelector('#mixer').clientWidth]")
        check("no horizontal overflow at 390 (page + mixer sheet)", sw[0] <= 390 and sw[1] <= sw[2], sw)
        check("zero console errors (§7 light)", not pg.errs, pg.errs)
        await pg.context.close()
        # dark: plan + energy
        pg = await new_page(b, scheme="dark")
        await pg.click('#segE [data-e="groove"]'); await pg.wait_for_timeout(300)
        await pg.evaluate("window.scrollTo(0, document.querySelector('#segE').getBoundingClientRect().top + scrollY - 140)"); await pg.wait_for_timeout(400)
        await shot(pg, "33-energy-groove-dark")
        await pg.locator("#list .card").nth(1).locator('[data-act="mixer"]').click(); await pg.wait_for_timeout(900)
        await pg.click('#mixer [data-act="tp-both"]'); await pg.wait_for_timeout(700)
        await pg.evaluate("document.querySelector('#mixer').scrollTo(0, 0)"); await pg.wait_for_timeout(400)
        await shot(pg, "34-mixer-top-dark")
        await pg.evaluate("document.querySelector('#mixer').scrollTo(0, document.querySelector('#mixer .plan').offsetTop - 60)"); await pg.wait_for_timeout(500)
        await shot(pg, "35-mixer-plan-dark")
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(600)
        await shot(pg, "36-home-mini-dark")
        check("zero console errors (§7 dark)", not pg.errs, pg.errs)
        await pg.context.close()
        # desktop mixer with plan
        pg = await new_page(b, w=1280, h=800)
        await pg.locator("#list .card").nth(0).locator('[data-act="both"]').click(); await pg.wait_for_timeout(700)
        await pg.click('#mini [data-act="open-mixer"]'); await pg.wait_for_timeout(900)
        await pg.evaluate("document.querySelector('#mixer').scrollTo(0, document.querySelector('#mixer .plan').offsetTop - 300)"); await pg.wait_for_timeout(500)
        await shot(pg, "37-desktop-mixer-plan")
        check("zero console errors (§7 desktop)", not pg.errs, pg.errs)
        await pg.context.close()
        # data-driven tab bar: a 5th feature tab (e.g. "מעברי מילים") fits and the lens lands on it
        pg = await new_page(b)
        await pg.evaluate("""(() => { const v = document.createElement('section'); v.innerHTML = '<header class="lt"><div class="lt-t"><h1>מעברי מילים</h1></div></header><p style="color:var(--label-2)">מקום לפיצ׳ר</p>';
            MashApp.addTab({ id: 'words', label: 'מעברי מילים', icon: 'spark', view: v, before: 'saved' }); MashApp.setTab('words'); })()""")
        await pg.wait_for_timeout(900)
        await shot(pg, "38-five-tabs-light")
        geo = await pg.evaluate("(() => { const l = document.querySelector('.tb-plat').getBoundingClientRect(), t = document.querySelector('#tab-words').getBoundingClientRect(), bar = document.querySelector('#tabbar').getBoundingClientRect(); return [Math.abs(l.left - t.left) < 2 && Math.abs(l.width - t.width) < 2, bar.width <= 390 - 32 + 0.5, document.querySelectorAll('.tab:not([hidden])').length]; })()")
        check("addTab: 5 tabs fit at 390 and the lens sits on the new tab", geo[0] and geo[1] and geo[2] == 4 or geo[2] == 5 and geo[0] and geo[1], geo)
        check("zero console errors (5 tabs)", not pg.errs, pg.errs)
        await pg.context.close()
        # overflow sweep: every view + both sheets, light and dark, in Claude mode (DJ tab visible)
        from run_tests import MOCK_CLAUDE
        for scheme in ("light", "dark"):
            pg = await new_page(b, scheme=scheme, init=MOCK_CLAUDE)
            widths = {}
            for t in ("home", "search", "saved", "dj"):
                await tab_click(pg, f"#tab-{t}"); await pg.wait_for_timeout(450)
                widths[t] = await pg.evaluate("document.documentElement.scrollWidth")
            await pg.click('#v-dj [data-act="source"]'); await pg.wait_for_timeout(700)
            widths["source"] = await pg.evaluate("[document.querySelector('#srcSheet').scrollWidth, document.querySelector('#srcSheet').clientWidth]")
            await pg.keyboard.press("Escape"); await pg.wait_for_timeout(500)
            ok = all(v <= 390 for k, v in widths.items() if k != "source") and widths["source"][0] <= widths["source"][1]
            check(f"no horizontal overflow at 390 in every view + source sheet ({scheme}, Claude mode)", ok, widths)
            check(f"zero console errors (sweep {scheme})", not pg.errs, pg.errs)
            await pg.context.close()
        pg = await new_page(b)
        await pg.context.close()
        await b.close()
    badn = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(badn)}/{len(RESULTS)} passed" + (f"; FAILED: {badn}" if badn else ""))
    sys.exit(1 if badn else 0)

if __name__ == "__main__":
    asyncio.run(main())
