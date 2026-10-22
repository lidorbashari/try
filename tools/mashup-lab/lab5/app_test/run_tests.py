"""UI tests + screenshots for app.html against engine_stub.js (or the real engine.js with `real`).
usage: python3 run_tests.py [stub|real]
Writes screenshots to app_test/shots/ and prints PASS/FAIL per assertion. Exit code 1 on any failure."""
import asyncio, json, os, re, sys
from playwright.async_api import async_playwright
import build

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "shots")
ENGINE = sys.argv[1] if len(sys.argv) > 1 else "stub"
RESULTS = []

def check(name, ok, info=""):
    RESULTS.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (("  " + str(info)[:300]) if info and not ok else ""))

MOCK_CLAUDE = r"""
window.__sampleCalls = 0;
async function sample(input, opts){
  window.__sampleCalls++;
  const T = Object.fromEntries(opts.tools.map(t=>[t.name,t]));
  window.__toolNames = Object.keys(T);
  const r = await T.find_pairs.execute({vocal_genre:"mizr", beat_genre:"house", limit:3}, {signal:new AbortController().signal});
  await T.present_pairs.execute({pairs: r.pairs.slice(0,2).map(p=>({vocal_id:p.vocal_id, beat_id:p.beat_id, why:"אותו סולם ואותו קצב: מזרחית רכה מעל האוס מתגלגל"}))}, {});
  await T.update_view.execute({vocal_genre:"mizr", beat_genre:"afrohouse"}, {});
  const txt = "בחרתי לך **שני זוגות** חזקים. לוחצים על נגן מאש־אפ יחד כדי לשמוע.";
  opts.onText({text: txt, delta: txt});
  return {text: txt, truncated:false};
}
sample.limits = async()=>({maxPromptBytes:262144, tools:{maxCount:16}});
window.claude = { use: async (n)=> n==="sample" ? sample : null };
"""

async def new_page(b, w=390, h=844, scheme="light", reduced=None, init=None, dpr=None):
    ctx = await b.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr or (3 if w < 800 else 1),
                              color_scheme=scheme, reduced_motion=reduced or "no-preference", has_touch=w < 800, is_mobile=w < 800)
    pg = await ctx.new_page()
    pg.errs = []
    pg.on("console", lambda m: pg.errs.append(m.type + ": " + m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: pg.errs.append("pageerror: " + str(e)))
    await pg.route("**/fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
    await pg.route("**/fonts.gstatic.com/**", lambda r: r.abort())
    if ENGINE == "real":   # real engine: answer the lookup (no match → Studio Groove) instead of aborting, so the console stays clean
        await pg.route("**/itunes.apple.com/**", lambda r: r.fulfill(status=200, content_type="application/json", headers={"Access-Control-Allow-Origin": "*"}, body='{"resultCount":0,"results":[]}'))
    else:
        await pg.route("**/itunes.apple.com/**", lambda r: r.abort())
    if init: await pg.add_init_script(init)
    await pg.goto("file://" + os.path.join(HERE, f"out_{ENGINE}.html"))
    await pg.wait_for_timeout(700)
    return pg

async def calls(pg, clear=False):
    c = await pg.evaluate("(window.__engineCalls || []).slice()")
    if clear: await pg.evaluate("window.__engineCalls && (window.__engineCalls.length = 0)")
    return c

def names(c): return [x[0] for x in c]

async def shot(pg, name, full=False):
    await pg.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=full)

async def main():
    out, dpath, n = build.build(ENGINE)
    print("built", out, "data:", dpath, n, "tracks")
    tpl = open(os.environ.get("APP_TPL") or os.path.join(os.path.dirname(HERE), "app.html"), encoding="utf-8").read()
    check("template has no 'spotify'", "spotify" not in tpl.lower())
    check("template has no window.open", "window.open" not in tpl)
    check("template has no 'אין לשיר הזה קובץ'", "אין לשיר הזה קובץ" not in tpl)
    check("placeholders exactly once", all(tpl.count(p) == 1 for p in ("__DATA__", "__SRC__", "/*__ENGINE__*/", "<!--BODY-->")))
    check("fragment starts with <title>", tpl.lstrip().startswith("<title>מעבדת המשאפים</title>"))
    stub = ENGINE == "stub"
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        # ---------------- home (light) ----------------
        pg = await new_page(b)
        await shot(pg, "01-home-light")
        sw = await pg.evaluate("document.documentElement.scrollWidth")
        check("no horizontal overflow at 390 (home)", sw <= 390, sw)
        html = (await pg.content()).lower()
        check("rendered DOM has no 'spotify'", "spotify" not in html)
        ext = await pg.evaluate("Array.from(document.querySelectorAll('a[href]')).filter(a => /^https?:/i.test(a.getAttribute('href'))).length")
        check("no external links outside Claude", ext == 0, ext)
        if stub:
            c = await calls(pg)
            check("engine created with net:true outside Claude", ["create", {"net": True}] in c, c[:3])
            check("no autoplay on load", not any(x[0] in ("play", "playBoth", "playOnly", "resume", "sequence") for x in c), names(c))
        cnt = await pg.evaluate("[document.querySelectorAll('#list .card').length, document.querySelector('#resN').textContent, MashApp.currentPairs().length]")
        check("home list renders 20 cards and the count", cnt[0] == 20 and int(cnt[1]) == cnt[2], cnt)
        await pg.evaluate("window.scrollTo(0, 1300)"); await pg.wait_for_timeout(500)
        await shot(pg, "02-home-list-light")
        # ---------------- card buttons ----------------
        await calls(pg, clear=True)
        card0 = pg.locator("#list .card").nth(0)
        pk0 = await card0.get_attribute("data-pk")
        await card0.locator('[data-act="both"]').click(); await pg.wait_for_timeout(700)
        c = await calls(pg, clear=True)
        if stub:
            check("card 'נגן מאש־אפ יחד' → gesture, loadPair, playBoth", names(c)[:1] == ["gesture"] and "loadPair" in names(c) and "playBoth" in names(c), names(c))
            lp = next((x for x in c if x[0] == "loadPair"), None)
            exp = await pg.evaluate(f"(() => {{ const [a,b] = '{pk0}'.split(':').map(Number); const p = MashApp.pairOf(MashApp.DATA[a], MashApp.DATA[b]); return [a, b, MashApp.ratesOf(p)]; }})()")
            check("loadPair gets the card's tracks + sync rates", lp and lp[1]["i"] == exp[0] and lp[2]["i"] == exp[1] and abs(lp[3]["A"] - exp[2]["A"]) < 1e-9 and abs(lp[3]["B"] - exp[2]["B"]) < 1e-9, [lp, exp])
        st = await pg.evaluate("[!document.querySelector('#mini').classList.contains('off'), document.querySelector('#list .card').classList.contains('is-loaded'), document.querySelector('#list .card [data-act=both]').getAttribute('aria-pressed'), document.querySelector('#miniS').textContent]")
        check("mini-player shows, card is live, primary pressed", st[0] and st[1] and st[2] == "true", st)
        await card0.locator('[data-act="both"]').click(); await pg.wait_for_timeout(300)
        c = await calls(pg, clear=True)
        if stub: check("same primary again → pauseAll", "pauseAll" in names(c) and "loadPair" not in names(c), names(c))
        card1 = pg.locator("#list .card").nth(1)
        await card1.locator('[data-act="vocal"]').click(); await pg.wait_for_timeout(600)
        c = await calls(pg, clear=True)
        if stub: check("'שירה בלבד' → gesture, loadPair, playOnly(A)", names(c)[0] == "gesture" and "loadPair" in names(c) and ["playOnly", "A"] in c, c)
        await card1.locator('[data-act="beat"]').click(); await pg.wait_for_timeout(600)
        c = await calls(pg, clear=True)
        if stub: check("'ביט בלבד' on the loaded card → playOnly(B), no reload", ["playOnly", "B"] in c and "loadPair" not in names(c), c)
        for _ in range(30):
            st = await pg.evaluate("document.querySelector('#miniS').textContent")
            if "טוען" not in st: break
            await pg.wait_for_timeout(250)
        check("mini status says ביט בלבד", "ביט בלבד" in st, st)
        await shot(pg, "03-home-playing-light")
        card2 = pg.locator("#list .card").nth(2)
        await card2.locator('[data-act="mixer"]').click(); await pg.wait_for_timeout(900)
        c = await calls(pg, clear=True)
        if stub: check("'פתח במיקסר' → loadPair + mixer opens, no play", "loadPair" in names(c) and not any(x in names(c) for x in ("play", "playBoth", "playOnly")), names(c))
        vis = await pg.evaluate("!document.querySelector('#mixer').hidden && document.querySelector('#mixer').classList.contains('on')")
        check("mixer sheet open", vis)
        # ---------------- mixer controls ----------------
        await pg.click('#mixer [data-act="tp-both"]'); await pg.wait_for_timeout(900)
        c = await calls(pg, clear=True)
        if stub: check("mixer נגן יחד → playBoth", "playBoth" in names(c), names(c))
        await shot(pg, "04-mixer-top-light")
        await pg.evaluate("document.querySelector('#mixer').scrollTo(0, document.querySelector('#orb').offsetTop - 170)"); await pg.wait_for_timeout(600)
        await shot(pg, "05-mixer-orb-light")
        await pg.evaluate("""(() => { const x = document.querySelector('#mixer [data-act=xf]'); x.value = '20'; x.dispatchEvent(new Event('input', {bubbles:true}));
            const e = document.querySelector('#dk-A [data-band=low]'); e.value = '-12'; e.dispatchEvent(new Event('input', {bubbles:true}));
            const v = document.querySelector('#dk-B [data-act=vol]'); v.value = '40'; v.dispatchEvent(new Event('input', {bubbles:true})); })()""")
        await pg.wait_for_timeout(200)
        c = await calls(pg, clear=True)
        if stub:
            check("crossfader → setCrossfader(0.2)", ["setCrossfader", 0.2] in c, c)
            check("EQ → setEq(A, low, -12)", ["setEq", "A", "low", -12] in c, c)
            check("volume → setVolume(B, 0.4)", ["setVolume", "B", 0.4] in c, c)
        await pg.click('#dk-A [data-act="sync"]'); await pg.click('#mixer [data-act="tp-loop"]'); await pg.wait_for_timeout(200)
        await pg.click('#mixer [data-act="tp-seq"]'); await pg.wait_for_timeout(300)
        c = await calls(pg, clear=True)
        if stub:
            check("SYNC → setSync(A,false)", ["setSync", "A", False] in c, c)
            check("לופ → loop(true)", ["loop", True] in c, c)
            check("רצף → stopAll + sequence(true)", "stopAll" in names(c) and ["sequence", True] in c, c)
        await pg.click('#dk-B [data-act="dk-toggle"]'); await pg.wait_for_timeout(200)
        c = await calls(pg, clear=True)
        if stub: check("deck play/pause → toggle(B)", ["toggle", "B"] in c, c)
        await pg.evaluate("(() => { const s = document.querySelector('#dk-A [data-act=seek]'); s.value = '12'; s.dispatchEvent(new Event('input', {bubbles:true})); s.dispatchEvent(new Event('change', {bubbles:true})); })()")
        c = await calls(pg, clear=True)
        if stub: check("progress slider → seek(A, 12)", ["seek", "A", 12] in c, c)
        before = await pg.evaluate("[MashApp.loaded.p.v.i, MashApp.loaded.p.b.i]")
        await pg.click('#mixer [data-act="tp-flip"]'); await pg.wait_for_timeout(300)
        c = await calls(pg, clear=True); after = await pg.evaluate("[MashApp.loaded.p.v.i, MashApp.loaded.p.b.i]")
        if stub: check("החלף תפקידים → loadPair(b, a)", "loadPair" in names(c) and after == before[::-1], [names(c), before, after])
        await pg.click('#mixer [data-act="tp-both"]'); await pg.wait_for_timeout(500)
        opt = await pg.evaluate("(() => { const s = document.querySelector('#dk-B [data-act=swap]'); const o = Array.from(s.options).find(o => !o.selected); return o ? o.value : null; })()")
        await calls(pg, clear=True)
        await pg.select_option('#dk-B [data-act="swap"]', opt); await pg.wait_for_timeout(300)
        c = await calls(pg, clear=True)
        if stub: check("swap select → loadDeck(B, track) and A keeps playing", any(x[0] == "loadDeck" and x[1] == "B" and str(x[2]["i"]) == str(opt) for x in c) and "loadPair" not in names(c) and "pauseAll" not in names(c), c)
        st = await pg.evaluate("MashApp.E.state().A.playing")
        if stub: check("deck A still playing after B swap", st, st)
        await pg.click('#mixer [data-act="sheet-close"]'); await pg.wait_for_timeout(700)
        c = await calls(pg, clear=True)
        st = await pg.evaluate("[document.querySelector('#mixer').hidden, !document.querySelector('#mini').classList.contains('off'), MashApp.E.state().A.playing || MashApp.E.state().B.playing]")
        check("closing mixer keeps music + mini-player", st[0] and st[1] and st[2] and not any(x in names(c) for x in ("pauseAll", "stopAll", "unload")), [st, names(c)])
        await pg.click('#mini [data-act="open-mixer"]'); await pg.wait_for_timeout(700)
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(700)
        check("Escape closes the mixer", await pg.evaluate("document.querySelector('#mixer').hidden"))
        await pg.click('#mini [data-act="unload"]'); await pg.wait_for_timeout(800)
        c = await calls(pg, clear=True)
        st = await pg.evaluate("[document.querySelector('#mini').classList.contains('off'), MashApp.loaded, document.querySelectorAll('.card.is-loaded').length]")
        check("mini ✕ → unload, mini hidden, no live cards", (not stub or "unload" in names(c)) and st[0] and st[1] is None and st[2] == 0, [names(c), st])
        # surprise
        await pg.evaluate("window.scrollTo(0, 0)")
        await pg.click('[data-act="surprise"]'); await pg.wait_for_timeout(900)
        c = await calls(pg, clear=True)
        sc = await pg.evaluate("MashApp.loaded && MashApp.loaded.p.score")
        check("תפתיע אותי → loads ≥85 pair, plays both, opens mixer", (not stub or (names(c)[0] == "gesture" and "loadPair" in names(c) and "playBoth" in names(c))) and sc >= 85 and await pg.evaluate("!document.querySelector('#mixer').hidden"), [names(c), sc])
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(600)
        # favorites
        await pg.evaluate("window.scrollTo(0, 1300)"); await pg.wait_for_timeout(200)
        await pg.locator("#list .card .star").nth(0).click(); await pg.locator("#list .card .star").nth(3).click(); await pg.wait_for_timeout(400)
        favs = await pg.evaluate("JSON.parse(localStorage.getItem('mashlab.favs'))")
        check("star saves to mashlab.favs", isinstance(favs, list) and len(favs) == 2, favs)
        await pg.click("#tab-saved"); await pg.wait_for_timeout(800)
        n_saved = await pg.evaluate("document.querySelectorAll('#savedList .card').length")
        check("saved view lists the 2 saved pairs", n_saved == 2, n_saved)
        await shot(pg, "06-saved-light")
        # search
        await pg.click("#tab-search"); await pg.wait_for_timeout(700)
        await shot(pg, "07-search-browse-light")
        await pg.fill("#q", "fisher"); await pg.wait_for_timeout(400)
        rows = await pg.evaluate("document.querySelectorAll('#sBody .srow').length")
        check("search finds song rows", rows > 0, rows)
        await pg.locator("#sBody .srow").nth(0).click(); await pg.wait_for_timeout(700)
        np_ = await pg.evaluate("document.querySelectorAll('#sCards .card').length")
        check("tapping a song shows partner cards", np_ > 0, np_)
        await pg.click('[data-act="s-role"][data-r="b"]'); await pg.wait_for_timeout(500)
        await shot(pg, "08-search-partners-light")
        await calls(pg, clear=True)
        await pg.locator("#sCards .card").nth(0).locator('[data-act="both"]').click(); await pg.wait_for_timeout(600)
        c = await calls(pg, clear=True)
        if stub: check("partner card plays (loadPair + playBoth)", "loadPair" in names(c) and "playBoth" in names(c), names(c))
        sw = await pg.evaluate("document.documentElement.scrollWidth")
        check("no horizontal overflow at 390 (search)", sw <= 390, sw)
        await pg.click("#tab-home"); await pg.wait_for_timeout(400)
        check("zero console errors (light run)", not pg.errs, pg.errs)
        await pg.context.close()

        # ---------------- dark mode ----------------
        pg = await new_page(b, scheme="dark")
        await shot(pg, "11-home-dark")
        await pg.evaluate("window.scrollTo(0, 1300)"); await pg.wait_for_timeout(400)
        await pg.locator("#list .card").nth(0).locator('[data-act="both"]').click(); await pg.wait_for_timeout(900)
        await shot(pg, "12-home-list-dark")
        await pg.click('#mini [data-act="open-mixer"]'); await pg.wait_for_timeout(900)
        await shot(pg, "13-mixer-top-dark")
        await pg.evaluate("document.querySelector('#mixer').scrollTo(0, document.querySelector('#orb').offsetTop - 170)"); await pg.wait_for_timeout(600)
        await shot(pg, "14-mixer-orb-dark")
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(600)
        await pg.click("#tab-search"); await pg.wait_for_timeout(500)
        await pg.fill("#q", "עומר"); await pg.wait_for_timeout(400)
        await shot(pg, "15-search-dark")
        await pg.click('[data-act="source"] >> visible=true'); await pg.wait_for_timeout(800)
        await shot(pg, "16-source-dark")
        check("zero console errors (dark run)", not pg.errs, pg.errs)
        await pg.context.close()

        # ---------------- Claude mode: DJ + source sheet ----------------
        pg = await new_page(b, init=MOCK_CLAUDE)
        if stub:
            c = await calls(pg)
            check("inside Claude → engine created with net:false", ["create", {"net": False}] in c, c[:2])
        vis = await pg.evaluate("!document.querySelector('#tab-dj').hidden")
        check("DJ tab visible when sample is available", vis)
        await pg.click("#tab-dj"); await pg.wait_for_timeout(500)
        await pg.click('#sugg button >> nth=0'); await pg.wait_for_timeout(1500)
        res = await pg.evaluate("[window.__sampleCalls, (window.__toolNames||[]).join(','), document.querySelectorAll('#chat .card').length, !!document.querySelector('#chat .goto'), document.querySelector('#chat .bub.dj:last-of-type') && document.querySelector('#chat').textContent.includes('שני זוגות')]")
        check("DJ ran sample with the 5 tools and rendered 2 cards", res[0] == 1 and res[1] == "find_pairs,search_tracks,partners_for_track,present_pairs,update_view" and res[2] == 2 and res[3], res)
        await shot(pg, "09-dj-light")
        await calls(pg, clear=True)
        await pg.locator("#chat .card").nth(0).locator('[data-act="both"]').click(); await pg.wait_for_timeout(700)
        c = await calls(pg, clear=True)
        if stub: check("DJ chat card plays (gesture, loadPair, playBoth)", names(c)[0] == "gesture" and "loadPair" in names(c) and "playBoth" in names(c), names(c))
        await shot(pg, "09b-dj-playing-light")
        await pg.click('#v-dj [data-act="source"]'); await pg.wait_for_timeout(800)
        dis = await pg.evaluate("[document.querySelector('#safariBtn').getAttribute('aria-disabled'), document.querySelector('#safariBtn').hasAttribute('href')]")
        check("Safari button disabled with no href until a URL is entered", dis == ["true", False], dis)
        await shot(pg, "10-source-claude-light")
        await pg.fill("#urlIn", "https://lidor.github.io/mashup-lab.html"); await pg.wait_for_timeout(200)
        st = await pg.evaluate("[document.querySelector('#safariBtn').getAttribute('href'), document.querySelector('#safariBtn').target, document.querySelector('#safariBtn').getAttribute('aria-disabled'), localStorage.getItem('mashlab.url'), Array.from(document.querySelectorAll('a[href]')).filter(a => /^https?:/i.test(a.getAttribute('href'))).length]")
        check("Safari link enabled after URL, target=_blank, saved, only external link", st[0] == "https://lidor.github.io/mashup-lab.html" and st[1] == "_blank" and st[2] == "false" and "lidor.github.io" in (st[3] or "") and st[4] == 1, st)
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(600)
        check("zero console errors (Claude run)", not pg.errs, pg.errs)
        await pg.context.close()

        # ---------------- reduced motion ----------------
        pg = await new_page(b, reduced="reduce")
        rm = await pg.evaluate("[REDUCED, getComputedStyle(document.querySelector('.pcard')).transitionDuration]")
        await pg.locator("#list .card").nth(0).locator('[data-act="both"]').click(); await pg.wait_for_timeout(300)
        await pg.click('#mini [data-act="open-mixer"]'); await pg.wait_for_timeout(600)
        t0 = await pg.evaluate("orbT"); await pg.wait_for_timeout(600); t1 = await pg.evaluate("orbT")
        check("reduced motion: CSS transitions off, orb not animating", rm[0] is True and rm[1].startswith("1e-") or rm[1] in ("0s", "1e-06s") and t0 == t1, [rm, t0, t1])
        check("zero console errors (reduced run)", not pg.errs, pg.errs)
        await pg.context.close()

        # ---------------- desktop ----------------
        pg = await new_page(b, w=1280, h=800)
        await shot(pg, "20-desktop-home")
        sw = await pg.evaluate("document.documentElement.scrollWidth")
        check("no horizontal overflow at 1280", sw <= 1280, sw)
        await pg.evaluate("window.scrollTo(0, 900)"); await pg.wait_for_timeout(300)
        await pg.locator("#list .card").nth(0).locator('[data-act="both"]').click(); await pg.wait_for_timeout(800)
        await shot(pg, "21-desktop-list-playing")
        await pg.click('#mini [data-act="open-mixer"]'); await pg.wait_for_timeout(900)
        await shot(pg, "22-desktop-mixer")
        check("zero console errors (desktop run)", not pg.errs, pg.errs)
        await pg.context.close()
        await b.close()
    bad = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} passed" + (f"; FAILED: {bad}" if bad else ""))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
