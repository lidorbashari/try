#!/usr/bin/env python3
"""Mashup Lab v5 - release build (QA lead).

Inputs   SP/lab5/app.html      template: __DATA__, __SRC__, /*__ENGINE__*/, <!--BODY--> exactly once
         SP/lab5/wordplay/{links.json, wordplay.js, wordplay_ui.js}   appended after the app script (UI_SPEC.md §1);
                               NO_WORDPLAY=1 builds without them
         SP/lab5/engine.js     window.MashEngine
         SP/lab5/data.json + src.json   (fallback SP/lab/data1000.json + src1000.json)
         SP/lab5/wordplay/new_tracks.tsv + new_sources.json   merged only if present and valid
Outputs  SP/mashup-lab-artifact.html   the fragment (head part + <!--BODY--> + body)
         SP/mashup-lab.html            standalone full document
usage: python3 build.py [--out-dir DIR]
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))          # SP/lab5
SP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build_data as BD                                   # GENRES, SUBGENRES, KEY_RE, key_of, check_data, check_src


def js(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("<!--", "<\\!--")


def pick_data():
    d, s = os.path.join(HERE, "data.json"), os.path.join(HERE, "src.json")
    if os.path.exists(d) and os.path.exists(s):
        return d, s
    return os.path.join(SP, "lab", "data1000.json"), os.path.join(SP, "lab", "src1000.json")


def merge_wordplay_tracks(data, src, log):
    """Merge SP/lab5/wordplay/new_tracks.tsv with the same validations as build_data.py. All-or-nothing per row."""
    tsv = os.path.join(HERE, "wordplay", "new_tracks.tsv")
    if not os.path.exists(tsv):
        return 0
    srcj = os.path.join(HERE, "wordplay", "new_sources.json")
    extra = json.load(open(srcj, encoding="utf-8")) if os.path.exists(srcj) else []
    ids = {x["id"] for x in src}
    for x in extra:
        if x.get("id") and x.get("n") and str(x.get("u", "")).startswith("https://") and x["id"] not in ids:
            src.append({"id": x["id"], "n": x["n"], "u": x["u"]}); ids.add(x["id"])
    seen = {BD.key_of(r["t"], r["a"]) for r in data}
    added, bad = 0, []
    for ln, line in enumerate(open(tsv, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        p = [x.strip() for x in line.split("\t")]
        try:
            assert len(p) in (8, 9, 10, 11), "columns"
            g, t, a, b, k, y, h, s = p[:8]
            assert g in BD.GENRES and t and a and BD.KEY_RE.fullmatch(k), "g/t/a/k"
            b = int(b); assert 55 <= b <= 200, "bpm"
            y = None if y == "None" else int(y); assert y is None or 1950 <= y <= 2026, "year"
            assert h in ("0", "1") and s in ids, "hot/source"
            r = {"g": g, "t": t, "a": a, "bpm": b, "k": k, "y": y, "hot": h == "1", "s": s}
            sg = p[8] if len(p) >= 9 else ""
            if sg not in ("", "-"):
                assert sg in BD.SUBGENRES, "sg"; r["sg"] = sg
            ev = p[9] if len(p) >= 10 else ""
            if ev not in ("", "-"):
                en = max(1, min(10, int(float(ev[:-1]) / 10 + 0.5))) if ev.endswith("%") else int(ev)
                assert 1 <= en <= 10, "e"; r["e"] = en
            kk = BD.key_of(t, a)
            if kk in seen:
                continue
            seen.add(kk); data.append(r); added += 1
        except Exception as e:
            bad.append(f"new_tracks.tsv:{ln}: {e}")
    if bad:
        log.append(f"wordplay tsv: {len(bad)} rows rejected: " + "; ".join(bad[:5]))
    return added


def build(out_dir=SP):
    log = []
    tpl = open(os.path.join(HERE, "app.html"), encoding="utf-8").read()
    for ph in ("__DATA__", "__SRC__", "/*__ENGINE__*/", "<!--BODY-->", "/*__LIQUID__*/", "/*__LIQUID_CSS__*/", "/*__MATCH__*/"):
        assert tpl.count(ph) == 1, (ph, tpl.count(ph))
    dpath, spath = pick_data()
    data = json.load(open(dpath, encoding="utf-8"))
    src = json.load(open(spath, encoding="utf-8"))
    n0 = len(data)
    added = merge_wordplay_tracks(data, src, log)
    BD.check_data(data); BD.check_src(src, data)
    eng = open(os.path.join(HERE, "engine.js"), encoding="utf-8").read()
    assert "MashEngine" in eng
    s = tpl.replace("__DATA__", js(data)).replace("__SRC__", js(src))
    s = s.replace("/*__ENGINE__*/", eng.replace("</script", "<\\/script"))
    # the Liquid Glass motion layer (ui/): its CSS joins the main stylesheet, its script runs before the app script
    ui = lambda n: open(os.path.join(HERE, "ui", n), encoding="utf-8").read()
    s = s.replace("/*__LIQUID_CSS__*/", ui("liquid.css").replace("</style", "<\\/style"))
    s = s.replace("/*__LIQUID__*/", ui("liquid.js").replace("</script", "<\\/script"))
    s = s.replace("/*__MATCH__*/", open(os.path.join(HERE, "match.js"), encoding="utf-8").read().replace("</script", "<\\/script"))
    # Wordplay ("מעברי מילים", wordplay/UI_SPEC.md §1): appended after the app script, in this order
    wp = {n: os.path.join(HERE, "wordplay", n) for n in ("links.json", "wordplay.js", "timing.js", "wordplay_ui.js")}
    wp_on = all(os.path.exists(x) for x in wp.values()) and os.environ.get("NO_WORDPLAY") != "1"
    if wp_on:
        links = json.load(open(wp["links.json"], encoding="utf-8"))
        jsf = lambda n: open(wp[n], encoding="utf-8").read().replace("</script", "<\\/script")
        s = (s.rstrip() + "\n<script>window.WORDPLAY_LINKS = " + js(links) + ";</script>\n<script>" + jsf("wordplay.js")
             + "</script>\n<script>" + jsf("timing.js") + "</script>\n<script>" + jsf("wordplay_ui.js") + "</script>\n")
    assert "__DATA__" not in s and "__SRC__" not in s
    frag_path = os.path.join(out_dir, "mashup-lab-artifact.html")
    open(frag_path, "w", encoding="utf-8").write(s)
    head, body = s.split("<!--BODY-->")
    doc = ('<!doctype html>\n<html lang="he" dir="rtl">\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
           '<meta name="apple-mobile-web-app-capable" content="yes">\n'
           '<meta name="mobile-web-app-capable" content="yes">\n'
           '<meta name="apple-mobile-web-app-status-bar-style" content="default">\n'
           '<meta name="apple-mobile-web-app-title" content="מעבדת המשאפים">\n'
           '<meta name="color-scheme" content="light dark">\n'
           '<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">\n'
           '<meta name="theme-color" content="#000000" media="(prefers-color-scheme: dark)">\n'
           '<link rel="manifest" href="manifest.webmanifest">\n'
           '<link rel="icon" type="image/png" href="icons/favicon-64.png">\n'
           '<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">\n'
           + head.strip() + '\n</head>\n<body>\n' + body.strip() +
           '\n<script>if ("serviceWorker" in navigator && location.protocol === "https:") addEventListener("load", function () { navigator.serviceWorker.register("sw.js").catch(function () {}); });</script>'
           '\n</body>\n</html>\n')
    doc_path = os.path.join(out_dir, "mashup-lab.html")
    open(doc_path, "w", encoding="utf-8").write(doc)
    return {"doc": doc_path, "frag": frag_path, "data": dpath, "tracks": len(data), "v5": n0,
            "wordplay_added": added, "wordplay_inlined": wp_on, "log": log,
            "kb": (os.path.getsize(doc_path) // 1024, os.path.getsize(frag_path) // 1024)}


if __name__ == "__main__":
    od = sys.argv[sys.argv.index("--out-dir") + 1] if "--out-dir" in sys.argv else SP
    print(json.dumps(build(od), ensure_ascii=False))
