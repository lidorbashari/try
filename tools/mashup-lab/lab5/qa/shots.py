"""Review screenshots of the RELEASE file (390x844 light/dark, 1280x800). usage: python3 qa/shots.py [names...]"""
import sys
from e2e_audio import *
OUT = os.path.join(QA, "shots"); os.makedirs(OUT, exist_ok=True)
WANT = set(sys.argv[1:])
def ctx(b, w=390, h=844, scheme="light"):
    c = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if w < 800 else 1, color_scheme=scheme, has_touch=w < 800, is_mobile=w < 800)
    pg = c.new_page(); errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body="")); pg.route("**/fonts.gstatic.com/**", lambda r: r.abort())
    pg.route("**/itunes.apple.com/**", Mock()); pg.goto(PAGE); pg.wait_for_timeout(900); return c, pg, errs
def snap(pg, n):
    if not WANT or n in WANT: pg.screenshot(path=os.path.join(OUT, n + ".png"))
srv = [serve(PP, H, SP), serve(CP, HC, os.path.join(QA, "media")), serve(NP, H, os.path.join(QA, "media"))]
with sync_playwright() as pw:
    b = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    for sc in ("light", "dark"):
        c, pg, errs = ctx(b, scheme=sc); snap(pg, f"home-{sc}")
        pg.locator("#list .card").nth(0).locator('[data-act="both"]').click(); pg.wait_for_timeout(4500)
        pg.evaluate("window.scrollTo(0, document.querySelector('#list').offsetTop - 120)"); pg.wait_for_timeout(700); snap(pg, f"list-playing-{sc}")
        pg.click('#mini [data-act="open-mixer"]'); pg.wait_for_timeout(1200); snap(pg, f"mixer-{sc}")
        pg.evaluate("document.querySelector('#mixer').scrollTo(0, document.querySelector('#orb').offsetTop - 170)"); pg.wait_for_timeout(700); snap(pg, f"mixer-orb-{sc}")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(600)
        tabs = pg.locator('[role=tab], nav button')
        for i in range(tabs.count()):
            t = tabs.nth(i).inner_text().strip()
            if "חיפוש" in t: tabs.nth(i).click(); pg.wait_for_timeout(500); pg.keyboard.type("עומר"); pg.wait_for_timeout(900); snap(pg, f"search-{sc}")
            if "מעברים" in t: tabs.nth(i).click(); pg.wait_for_timeout(900); pg.evaluate("window.scrollTo(0,0)"); snap(pg, f"words-{sc}")
            if "שמורים" in t: tabs.nth(i).click(); pg.wait_for_timeout(600); snap(pg, f"saved-{sc}")
        print(sc, "errors:", errs[:3]); c.close()
    c, pg, errs = ctx(b, 1280, 800); snap(pg, "desktop-home")
    pg.locator("#list .card").nth(0).locator('[data-act="mixer"]').click(); pg.wait_for_timeout(1200); snap(pg, "desktop-mixer"); print("desktop errors:", errs[:3]); c.close()
    b.close()
for s in srv: s.shutdown()
