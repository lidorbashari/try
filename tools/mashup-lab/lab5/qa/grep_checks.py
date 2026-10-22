"""Static checks on the release files (SPEC §6 items 5 + document shape). usage: python3 qa/grep_checks.py"""
import json, os, re, sys
QA = os.path.dirname(os.path.abspath(__file__)); LAB = os.path.dirname(QA); SP = os.path.dirname(LAB)
R = []
def check(n, ok, info=""):
    R.append((n, bool(ok)))
    if not ok: print("FAIL " + n + ("  " + str(info)[:300] if info != "" else ""))
doc = open(os.path.join(SP, "mashup-lab.html"), encoding="utf-8").read()
frag = open(os.path.join(SP, "mashup-lab-artifact.html"), encoding="utf-8").read()
for name, s in (("doc", doc), ("fragment", frag)):
    low = s.lower()
    check(f"{name}: no 'spotify'", "spotify" not in low, low.count("spotify"))
    check(f"{name}: no 'open.spotify.com'", "open.spotify.com" not in low)
    check(f"{name}: no 'אין לשיר הזה קובץ'", "אין לשיר הזה קובץ" not in s)
    check(f"{name}: no window.open", "window.open" not in s)
    check(f"{name}: no placeholders left", not any(p in s for p in ("__DATA__", "__SRC__", "/*__ENGINE__*/", "__WORDPLAY")))
    tb = len(re.findall(r'target\s*=\s*["\']?_blank', s))
    check(f"{name}: exactly one target=_blank (the Safari link)", tb == 1, tb)
    check(f"{name}: no download/cache of audio bytes (no caches.open / blob(), no <a download>)", not re.search(r"caches\.open|\.blob\(\)|\sdownload=", s))
    check(f"{name}: iTunes attribution text present (§4.9b)", "תצוגה מקדימה באדיבות iTunes" in s)
    check(f"{name}: MashEngine + Wordplay inlined", "window.MashEngine" in s or "W.MashEngine" in s)
    check(f"{name}: wordplay inlined", "window.WORDPLAY_LINKS" in s and "WordplayUI" in s)
    check(f"{name}: no stray '</script' inside inlined code", s.count("<script") == s.count("</script>"), (s.count("<script"), s.count("</script>")))
head = doc.split("</head>")[0]
check("doc: <!doctype html> first", doc.lower().startswith("<!doctype html>"))
check("doc: <html lang=he dir=rtl>", '<html lang="he" dir="rtl">' in doc)
check("doc: charset", '<meta charset="utf-8">' in head)
check("doc: viewport with viewport-fit=cover", 'content="width=device-width, initial-scale=1, viewport-fit=cover"' in head)
check("doc: apple-mobile-web-app-capable", 'name="apple-mobile-web-app-capable" content="yes"' in head)
check("doc: theme-color light + dark", head.count('name="theme-color"') == 2 and "(prefers-color-scheme: dark)" in head)
check("doc: <title> + <style> in head, app markup in body", "<title>" in head and "<style>" in head and 'id="mini"' in doc.split("<body>")[1])
check("fragment: starts with <title>, no <html>/<body>/doctype", frag.lstrip().startswith("<title>") and not re.search(r"<html|<body|<!doctype", frag, re.I))
check("sizes < 16 MB", len(doc.encode()) < 16e6 and len(frag.encode()) < 16e6, (len(doc), len(frag)))
# lyrics: the only song text shown is titles; wordplay link words must be title words
L = json.load(open(os.path.join(LAB, "wordplay", "links.json"), encoding="utf-8"))
def inn(w, t):
    w = w.lower().strip(" ?!."); return w in t or any(x.strip("?!.,") in t for x in w.split() if len(x) >= 2)
bad = []
for l in L:
    p = re.split(r"\s+(?:→|=)\s+", l["word"]); ta, tb = l["a"].split(" | ")[0].lower(), l["b"].split(" | ")[0].lower()
    if not inn(p[0], ta) or (len(p) > 1 and not inn(p[1], tb) and p[1] not in ("הדרופ",)): bad.append(l["word"])
    if any(len(re.findall(r'["“”״]', l.get(f) or "")) >= 2 for f in ("why_he", "cueA", "cueB")): bad.append("quote:" + l["word"])
check(f"wordplay: {len(L)} link words are title words, no quoted lyric lines", not bad, bad[:5])
bad = [n for n, ok in R if not ok]
print(f"grep_checks: {len(R) - len(bad)}/{len(R)} passed" + (f"; FAILED: {bad}" if bad else ""))
sys.exit(1 if bad else 0)
