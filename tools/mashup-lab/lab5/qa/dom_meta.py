import sys; sys.argv=[sys.argv[0]]
from e2e_audio import *
srv=[serve(PP,H,SP),serve(CP,HC,os.path.join(QA,"media")),serve(NP,H,os.path.join(QA,"media"))]
with sync_playwright() as pw:
    b=pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"]); p=P(b)
    r=p.ev("""(() => { const out = {split:0, lines3:0, n:0, first:''}; document.querySelectorAll('#list .card .ar').forEach((a,i) => { out.n++;
        const lh = parseFloat(getComputedStyle(a).lineHeight); if (a.scrollHeight > lh*2+2) out.lines3++;
        const an = a.querySelector('.an'); if (an && new Set(Array.from(an.getClientRects()).map(r => Math.round(r.top))).size > 1) { out.split++; out.ex = (out.ex||[]).concat([a.textContent.slice(0,60)]); } if (!i) out.first = a.textContent; }); return out; })()""")
    print("meta:", r)
    p.pg.click('[data-act="source"] >> nth=0'); p.pg.wait_for_timeout(700)
    t=p.ev("document.querySelector('#srcBody').textContent")
    print("sheet has attribution:", "באדיבות iTunes" in t, "| Studio Groove:", "גרוב סטודיו" in t, "| links:", p.ev("document.querySelectorAll('#srcSheet a[href^=http]').length"))
    p.close(); p=P(b, init=MOCK_CLAUDE); p.pg.click('[data-act="source"] >> nth=0'); p.pg.wait_for_timeout(700)
    t=p.ev("document.querySelector('#srcBody').textContent")
    print("claude sheet: Safari:", "Safari" in t, "| blocked explained:", ("חסום" in t or "חסומ" in t), "| errs:", p.errs[:2]); b.close()
