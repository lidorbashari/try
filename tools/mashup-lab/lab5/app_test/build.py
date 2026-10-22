"""Test build for the app template: injects data + an engine and wraps the fragment into a full document.
usage: python3 build.py [stub|real] [out.html]
Data: SP/lab5/data.json + src.json when present, else SP/lab/data1000.json + src1000.json."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
LAB5 = os.path.dirname(HERE)
SP = os.path.dirname(LAB5)

def pick_data():
    d, s = os.path.join(LAB5, "data.json"), os.path.join(LAB5, "src.json")
    if os.path.exists(d) and os.path.exists(s) and os.environ.get("APP_DATA") != "1000":
        return d, s
    return os.path.join(SP, "lab", "data1000.json"), os.path.join(SP, "lab", "src1000.json")

def js(obj):
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")

def build(engine="stub", out=None):
    tpl = open(os.environ.get("APP_TPL") or os.path.join(LAB5, "app.html"), encoding="utf-8").read()
    for ph in ("__DATA__", "__SRC__", "/*__ENGINE__*/", "<!--BODY-->"):
        assert tpl.count(ph) == 1, (ph, tpl.count(ph))
    dpath, spath = pick_data()
    data, src = json.load(open(dpath, encoding="utf-8")), json.load(open(spath, encoding="utf-8"))
    eng = open(os.path.join(LAB5, "engine_stub.js" if engine == "stub" else "engine.js"), encoding="utf-8").read()
    s = tpl.replace("__DATA__", js(data)).replace("__SRC__", js(src)).replace("/*__ENGINE__*/", eng.replace("</script", "<\\/script"))
    head, body = s.split("<!--BODY-->")
    doc = ('<!doctype html>\n<html lang="he" dir="rtl">\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
           '<meta name="apple-mobile-web-app-capable" content="yes">\n'
           '<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">\n'
           '<meta name="theme-color" content="#000000" media="(prefers-color-scheme: dark)">\n'
           + head + '\n</head>\n<body>\n' + body + '\n</body>\n</html>\n')
    out = out or os.path.join(HERE, f"out_{engine}.html")
    open(out, "w", encoding="utf-8").write(doc)
    return out, dpath, len(data)

if __name__ == "__main__":
    eng = sys.argv[1] if len(sys.argv) > 1 else "stub"
    print(build(eng, sys.argv[2] if len(sys.argv) > 2 else None))
