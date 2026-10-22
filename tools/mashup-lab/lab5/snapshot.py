#!/usr/bin/env python3
"""Copy Mashup Lab's sources and tests from the working tree (this scratchpad) into the repo: tools/mashup-lab/.
The layout mirrors the working tree, so the tests run from there too (generate the test media first, see README)."""
import os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__)); SP = os.path.dirname(HERE)
DST = os.path.join(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/try", "tools", "mashup-lab")
FILES = """
lab5/engine.js lab5/engine_stub.js lab5/app.html lab5/build.py lab5/build_data.py lab5/data.json lab5/src.json lab5/deploy.py lab5/snapshot.py
lab5/wordplay/links.json lab5/wordplay/wordplay.js lab5/wordplay/timing.js lab5/wordplay/wordplay_ui.js lab5/wordplay/test/t_timing.js
lab5/qa/e2e_audio.py lab5/qa/e2e_wordplay.py lab5/qa/grep_checks.py lab5/qa/run_all.sh lab5/qa/run_ui_suites.py lab5/qa/dom_meta.py lab5/qa/dom_tabs.py
lab5/qa/mock_claude.js lab5/qa/shots.py lab5/qa/media/art/100x100bb.png lab5/qa/media/art/600x600bb.png
lab5/engine_test/test_engine.py lab5/engine_test/test_levels.py lab5/engine_test/make_wavs.py lab5/engine_test/test.html
lab5/app_test/build.py lab5/app_test/run_tests.py lab5/app_test/run_s7.py
lead_check/common/rangehttp.py lead_check/beat/t_buf.py lead_check/beat/t_sync.py lead_check/beat/mkwav.py lead_check/beat/truth.json lead_check/beat/media/index.html
lead_check/wp/t_wp.py lead_check/wp/mkwav.py lead_check/wp/truth.json lead_check/wp/media/index.html
pwa/sw.js pwa/manifest.webmanifest pwa/icons/icon-192.png pwa/icons/icon-512.png pwa/icons/apple-touch-icon.png pwa/icons/favicon-64.png
previews.json beats.json analysis.json wordtimes.json
""".split()
n = 0
for f in FILES:
    src = os.path.join(SP, f)
    if not os.path.exists(src):
        print("missing", f); continue
    dst = os.path.join(DST, f); os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst); n += 1
print(n, "files →", DST)
