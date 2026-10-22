"""QA lead: "מעברי מילים" (wordplay) E2E on the RELEASE file with the real engine + CORS WAV previews.
usage: python3 qa/e2e_wordplay.py      prints FAIL lines + summary; exit 1 on failure."""
import re, sys, time
from e2e_audio import *

RES2 = RESULTS
LOGGER = """(() => { const E = MashApp.E; window.__wlog = [];
  ['gesture','playOnly','play','pause','pauseAll','loadPair','setCrossfader'].forEach(k => { const f = E[k]; E[k] = function () { __wlog.push(k); return f.apply(this, arguments); }; }); })()"""


def tab_btn(p, label): return p.pg.locator(f'nav button:has-text("{label}"), [role=tablist] button:has-text("{label}"), button[data-tab="words"]').first


def run(b, scheme):
    p = P(b, scheme=scheme)
    labels = p.ev("Array.from(document.querySelectorAll('[role=tab], .tab, nav button')).map(x => x.textContent.trim()).filter(Boolean)")
    check(f"wp[{scheme}]: tab 'מעברים' present", any("מעברים" in x for x in labels), labels)
    tab_btn(p, "מעברים").click(); p.pg.wait_for_timeout(900)
    info = p.ev("""(() => { const v = document.querySelector('section.wp'); return { vis: !!v && v.offsetParent !== null, cards: document.querySelectorAll('.wp-card').length,
        h1: v && v.querySelector('h1').textContent, sub: v && v.querySelector('.wp-sub').textContent, n: WordplayUI.links.length, cur: WordplayUI.curated,
        sw: document.documentElement.scrollWidth }; })()""")
    check(f"wp[{scheme}]: view visible with title 'מעברי מילים' and 20 cards", info["vis"] and info["h1"] == "מעברי מילים" and info["cards"] == 20, info)
    check(f"wp[{scheme}]: 95 curated links resolve, sub line counts match", info["cur"] == 95 and re.match(rf"{info['n']} מעברים · 95 נבחרו ביד", info["sub"] or ""), info)
    check(f"wp[{scheme}]: no horizontal overflow at 390", info["sw"] <= 390, info["sw"])
    marks = p.ev("Array.from(document.querySelectorAll('.wp-card .wp-t')).map(t => { const m = t.querySelector('mark'); return !m || t.textContent.includes(m.textContent); })")
    check(f"wp[{scheme}]: highlighted words are title words (no lyric lines)", all(marks), marks)
    if scheme == "dark":
        p.pg.screenshot(path=os.path.join(QA, "shots", "wp-dark.png")); p.close(); return
    p.pg.screenshot(path=os.path.join(QA, "shots", "wp-light.png"))
    p.ev(LOGGER)
    btn = p.pg.locator('.wp-card').nth(0).locator('[data-wact="play"]')
    btn.click()
    log0 = p.ev("__wlog.slice()")
    check("wp: 'נגן מעבר' calls E.gesture() synchronously first", log0[:1] == ["gesture"], log0)
    check("wp: button reads 'עצור מעבר' while running", "עצור מעבר" in btn.inner_text())
    live = p.ev("(() => { const b = document.querySelector('.wp-card .wp-live'); return b ? b.querySelector('.wp-now').textContent : null; })()")
    check("wp: the card shows the live transition box at once (preparing…)", bool(live), live)
    ok = p.wait("MashApp.E.wpState().phase === 'a'", 9000)
    w = p.ev("(() => { const w = MashApp.E.wpState(), s = MashApp.E.state(); return {ph: w.phase, plan: w.plan && {cut: w.plan.cut, aStart: w.plan.aStart, r: w.plan.r, style: w.plan.style, synced: w.plan.synced}, cut: w.cut, total: w.total, decks: [s.A.playing, s.B.playing]}; })()")
    check("wp: the word play runs on the decoded previews (phase a: A plays, B waits for the word)", ok and w["plan"], w)
    check("wp: the decks stay paused while the word-play player runs", w["decks"] == [False, False], w)
    if ok:
        p.pg.wait_for_timeout(600)
        bar = p.ev("(() => { const b = document.querySelector('.wp-card .wp-live'); if (!b) return null; return {fill: parseFloat(b.querySelector('.fill').style.width) || 0, cut: b.querySelector('.cutm').style.insetInlineStart, now: b.querySelector('.wp-now').textContent, how: b.querySelectorAll('.wp-how li').length}; })()")
        check("wp: progress bar moves, the cut is marked, a status line and the plan (Hebrew) show", bar and bar["fill"] > 0 and bar["cut"] and bar["now"] and bar["how"] >= 2, bar)
        okb = p.wait("MashApp.E.wpState().phase === 'b'", int((w["cut"] + 3) * 1000))
        now = p.ev("(() => { const b = document.querySelector('.wp-card .wp-now'); return b && b.textContent; })()")
        check("wp: B takes over at the cut (phase b) and the status says so", okb and now and "B" in now, [okb, now])
        lv = p.ev("""(() => { const n = MashApp.E._wpNodes(); if (!n) return null; const c = MashApp.E._ctx(), an = c.createAnalyser(); an.fftSize = 2048; n.bus.connect(an);
          return new Promise(r => setTimeout(() => { const d = new Float32Array(an.fftSize); an.getFloatTimeDomainData(d); let q = 0; for (const v of d) q += v * v; try { n.bus.disconnect(an); } catch (e) {} r(Math.sqrt(q / d.length)); }, 300)); })()""")
        check("wp: B is audible on the word-play output", lv is not None and lv > .005, lv)
    btn = p.pg.locator('.wp-card').nth(0).locator('[data-wact="play"]')
    if "עצור מעבר" in btn.inner_text(): btn.click(); p.pg.wait_for_timeout(500)
    st = p.ev("(() => ({ph: MashApp.E.wpState().phase, how: document.querySelectorAll('.wp-card')[0].querySelectorAll('.wp-how li').length, live: !!document.querySelector('.wp-card .wp-live')}))()")
    check("wp: stop ends it; the card keeps the plan (how the transition was built)", st["ph"] == "idle" and st["how"] >= 2 and not st["live"], st)
    check("wp: button back to 'נגן מעבר'", "נגן מעבר" in btn.inner_text(), btn.inner_text())
    # no decoded audio (fetch fails): the streamed fallback still plays the transition
    p.ev("(() => { MashApp.E.wordplay = () => Promise.reject(new Error('test: no decoded audio')); return true; })()")
    btn1 = p.pg.locator('.wp-card').nth(2).locator('[data-wact="play"]'); btn1.click()
    ok = p.wait("(() => { const s = MashApp.E.state(); return s.mode === 'A' && s.A.playing && !s.B.playing && s.xf < 0.05; })()", 9000)
    check("wp fallback: without decoded audio the streamed player plays A first", ok, p.st())
    if "עצור מעבר" in btn1.inner_text(): btn1.click(); p.pg.wait_for_timeout(400)
    p.pg.locator('.wp-card').nth(0).locator('[data-wact="mixer"]').click(); p.pg.wait_for_timeout(900)
    check("wp: 'פתח במיקסר' opens the mixer", p.ev("!document.querySelector('#mixer').hidden && document.querySelector('#mixer').classList.contains('on')"))
    if w.get("plan"):
        pos = p.ev("(() => { const s = MashApp.E.state(); return [s.A.pos, s.B.pos]; })()")
        check("wp: the mixer opens cued where the transition starts (A at its lead-in)", abs(pos[0] - w["plan"]["aStart"]) < .35, [pos, w["plan"]])
    p.pg.keyboard.press("Escape"); p.pg.wait_for_timeout(600)
    p.pg.locator('section.wp [data-wf="compat"]').click(); p.pg.wait_for_timeout(400)
    sub = p.ev("document.querySelector('section.wp .wp-sub').textContent")
    n = int(sub.split()[0]); check("wp: compatible-only filter narrows the list", 0 < n < info["n"], sub)
    check("wp: zero console errors", not p.errors(), p.errors()[:4]); p.close()


def main():
    os.makedirs(os.path.join(QA, "shots"), exist_ok=True)
    srv = [serve(PP, H, SP), serve(CP, HC, os.path.join(QA, "media")), serve(NP, H, os.path.join(QA, "media"))]
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        for sc in ("light", "dark"):
            try: run(b, sc)
            except Exception as e: check(f"wp[{sc}] crashed", False, repr(e)[:400])
        b.close()
    for s in srv: s.shutdown()
    bad = [n for n, ok in RESULTS if not ok]
    print(f"e2e_wordplay: {len(RESULTS) - len(bad)}/{len(RESULTS)} passed" + (f"; FAILED: {bad}" if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
