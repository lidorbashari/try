#!/usr/bin/env python3
"""Copy the release build into the repo: docs/mashup-lab/ (index.html + PWA files) and tools/verify/mashup-lab-next.html.
usage: python3 deploy.py [REPO]   (build.py must have run; REPO defaults to /home/claude/try)"""
import hashlib, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__)); SP = os.path.dirname(HERE)
inside = os.path.dirname(os.path.dirname(SP))                      # tools/mashup-lab/lab5/deploy.py → the repo root
repo = sys.argv[1] if len(sys.argv) > 1 else inside if os.path.isdir(os.path.join(inside, "docs", "mashup-lab")) else "/home/claude/try"
doc = open(os.path.join(SP, "mashup-lab.html"), encoding="utf-8").read()
assert "MashEngine" in doc and "WordTiming" in doc and 'rel="manifest"' in doc
dst = os.path.join(repo, "docs", "mashup-lab")
open(os.path.join(dst, "index.html"), "w", encoding="utf-8").write(doc)
open(os.path.join(repo, "tools", "verify", "mashup-lab-next.html"), "w", encoding="utf-8").write(doc)
build = hashlib.sha1(doc.encode("utf-8")).hexdigest()[:10]
sw = open(os.path.join(SP, "pwa", "sw.js"), encoding="utf-8").read().replace("__BUILD__", build)
open(os.path.join(dst, "sw.js"), "w", encoding="utf-8").write(sw)
shutil.copy(os.path.join(SP, "pwa", "manifest.webmanifest"), os.path.join(dst, "manifest.webmanifest"))
os.makedirs(os.path.join(dst, "icons"), exist_ok=True)
for f in os.listdir(os.path.join(SP, "pwa", "icons")):
    shutil.copy(os.path.join(SP, "pwa", "icons", f), os.path.join(dst, "icons", f))
print("deployed build", build, len(doc) // 1024, "KB")
