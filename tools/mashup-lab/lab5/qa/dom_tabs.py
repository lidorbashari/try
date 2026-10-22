import sys; sys.argv=[sys.argv[0]]
from e2e_audio import *
srv=[serve(PP,H,SP)]
with sync_playwright() as pw:
    b=pw.chromium.launch(); p=P(b, init=MOCK_CLAUDE); p.pg.wait_for_timeout(800)
    r=p.ev("""(() => { const tb = Array.from(document.querySelectorAll('[role=tab]')); return {labels: tb.map(t => t.textContent.trim()),
      sw: document.documentElement.scrollWidth, fit: tb.every(t => { const r = t.getBoundingClientRect(); return r.left >= 0 && r.right <= 390 && t.scrollWidth <= t.clientWidth + 1; })}; })()""")
    print(r, p.errs[:2]); b.close()
