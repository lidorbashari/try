#!/usr/bin/env python3
"""
build_site.py - generate the DJ Lab static website into docs/.

    python tools/build_site.py                        # full build (waveform peaks via ffmpeg+numpy, cached)
    python tools/build_site.py --no-peaks             # never analyse audio; keep peaks already in docs/data/peaks.js
    python tools/build_site.py --no-peaks-if-missing  # analyse only what is possible here (CI-safe), keep the rest

Inputs (all optional - the build never fails on missing or partial content):
    guide/*.md (+ guide/assets/*), music/catalog.json and/or music/**/<id>.json sidecars,
    music/tracklist.plan.json, music/extras.plan.json, crates/*.md|*.csv, sets/*.md
Outputs:
    docs/index.html, docs/library.html, docs/practice.html, docs/about.html,
    docs/guide/*.html, docs/crates/*.html, docs/sets/*.html, docs/tools/*.html,
    docs/data/{catalog,peaks,guide,crates,sets}.js, docs/assets/guide/*, docs/assets/js/icons.gen.js

Every page carries <meta name="djlab-root"> (relative path to the repo root, used by JS to build media URLs
such as ROOT + "music/...mp3") and <meta name="djlab-base"> (relative path to docs/).
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA = DOCS / "data"
CACHE = ROOT / ".render_cache" / "peaks"
REPO_URL = "https://github.com/lidorbashari/try"
SITE_URL = "https://lidorbashari.github.io/try/"
PEAK_POINTS = 600
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}

try:
    import markdown  # type: ignore
    from markdown.extensions.toc import slugify_unicode  # type: ignore
except Exception:  # pragma: no cover - reported in summary
    markdown = None
    slugify_unicode = None

FAMILY_HE = {
    "house": "האוס",
    "techno": "טכנו",
    "mainstream": "מיינסטרים",
    "breadth": "עוד ז'אנרים",
}
LEVEL_HE = {
    "beginner": "מתחילים", "basic": "בסיס", "intermediate": "ביניים", "advanced": "מתקדמים",
}

STATS = {"warnings": []}
GENRE_NAMES: dict[str, str] = {}  # genre_slug -> display name, filled from the plan


def warn(msg: str) -> None:
    STATS["warnings"].append(msg)


# --------------------------------------------------------------------------------------------- utils
def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:  # pragma: no cover
        warn(f"cannot read {p}: {e}")
        return ""


def read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception as e:
        warn(f"bad JSON {p.relative_to(ROOT)}: {e}")
        return default


WRITTEN: set[Path] = set()
CHANGED: list[str] = []


def write(p: Path, content: str | bytes) -> None:
    """Write only when content changed (keeps git diffs and mtimes quiet)."""
    p.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8") if isinstance(content, str) else content
    WRITTEN.add(p.resolve())
    try:
        if p.exists() and p.read_bytes() == data:
            return
    except Exception:
        pass
    p.write_bytes(data)
    CHANGED.append(str(p.relative_to(ROOT)))


def js_global(name: str, obj) -> str:
    return f"window.{name} = " + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + ";\n"


def rel(from_file: Path, to_path: Path) -> str:
    r = os.path.relpath(to_path, from_file.parent).replace(os.sep, "/")
    return r


def asset_version(*paths: Path) -> str:
    h = hashlib.sha1()
    for p in paths:
        try:
            h.update(p.read_bytes())
        except Exception:
            pass
    return h.hexdigest()[:8]


def parse_front_matter(text: str):
    m = re.match(r"^\ufeff?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not m:
        return {}, text
    raw, body = m.group(1), text[m.end():]
    data = None
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(raw)
    except Exception:
        data = None
    if not isinstance(data, dict):
        data = {}
        for line in raw.splitlines():
            mm = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
            if not mm:
                continue
            k, v = mm.group(1), mm.group(2).strip()
            if v.startswith("[") and v.endswith("]"):
                data[k] = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
            else:
                v = v.strip("'\"")
                data[k] = int(v) if re.fullmatch(r"-?\d+", v) else v
    return data, body


def clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(",;:—–-(")
    return cut + "…"


def as_list(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [x.strip() for x in str(v).split(",") if x.strip()]


# --------------------------------------------------------------------------------------------- icons
ICONS = {
    "play": '<path d="M7 4.8v14.4a.8.8 0 0 0 1.2.7l11.6-7.2a.8.8 0 0 0 0-1.4L8.2 4.1A.8.8 0 0 0 7 4.8z" fill="currentColor" stroke="none"/>',
    "pause": '<rect x="6" y="4.5" width="4.2" height="15" rx="1.2" fill="currentColor" stroke="none"/><rect x="13.8" y="4.5" width="4.2" height="15" rx="1.2" fill="currentColor" stroke="none"/>',
    "prev": '<path d="M18.5 5.6v12.8a.8.8 0 0 1-1.2.7L8 13.2V18a1 1 0 0 1-2 0V6a1 1 0 0 1 2 0v4.8l9.3-5.9a.8.8 0 0 1 1.2.7z" fill="currentColor" stroke="none"/>',
    "next": '<path d="M5.5 5.6v12.8a.8.8 0 0 0 1.2.7L16 13.2V18a1 1 0 0 0 2 0V6a1 1 0 0 0-2 0v4.8L6.7 4.9a.8.8 0 0 0-1.2.7z" fill="currentColor" stroke="none"/>',
    "download": '<path d="M12 3.5v11.5m0 0-4.5-4.5M12 15l4.5-4.5M4.5 19.5h15"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6 6 6M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4"/>',
    "moon": '<path d="M20 14.6A8.2 8.2 0 1 1 9.4 4a6.6 6.6 0 0 0 10.6 10.6z"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "chev-left": '<path d="m14.5 6-6 6 6 6"/>',
    "chev-right": '<path d="m9.5 6 6 6-6 6"/>',
    "chev-down": '<path d="m6 9.5 6 6 6-6"/>',
    "external": '<path d="M14 4h6v6M20 4l-8.5 8.5M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "headphones": '<path d="M4 15.5V12a8 8 0 0 1 16 0v3.5"/><rect x="3" y="14" width="5" height="7" rx="2"/><rect x="16" y="14" width="5" height="7" rx="2"/>',
    "bulb": '<path d="M9.5 18h5M10.5 21h3M12 3a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.2h5c0-.9.4-1.7 1.1-2.2A6 6 0 0 0 12 3z"/>',
    "alert": '<path d="M10.3 4.3 2.8 17.5A2 2 0 0 0 4.5 20.5h15a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4.5M12 17h.01"/>',
    "sliders": '<path d="M6 3.5v17M12 3.5v17M18 3.5v17"/><rect x="3.5" y="13" width="5" height="3.2" rx="1" fill="currentColor"/><rect x="9.5" y="6.5" width="5" height="3.2" rx="1" fill="currentColor"/><rect x="15.5" y="15" width="5" height="3.2" rx="1" fill="currentColor"/>',
    "wheel": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 3v4.5M12 16.5V21M3 12h4.5M16.5 12H21M5.6 5.6l3.2 3.2M15.2 15.2l3.2 3.2M18.4 5.6l-3.2 3.2M8.8 15.2l-3.2 3.2"/>',
    "metronome": '<path d="M7 21 9.8 3.8A1 1 0 0 1 10.8 3h2.4a1 1 0 0 1 1 .8L17 21z"/><path d="m12 16 6.5-9.5M8.3 15.5h7.4"/>',
    "mixer": '<circle cx="7" cy="9" r="4"/><circle cx="17" cy="9" r="4"/><circle cx="7" cy="9" r="1" fill="currentColor"/><circle cx="17" cy="9" r="1" fill="currentColor"/><path d="M3.5 18.5h17"/><rect x="10" y="16.5" width="4" height="4" rx="1"/>',
    "setlist": '<path d="M4 6h11M4 11h11M4 16h7"/><circle cx="17.5" cy="17.5" r="2.5"/><path d="M20 17.5V7l-3 1"/>',
    "code": '<path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z"/><path d="M14 3v5h5M10 12l-2 2.5 2 2.5M14 12l2 2.5-2 2.5"/>',
    "disc": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.5"/><path d="M12 6.5a5.5 5.5 0 0 1 5.5 5.5"/>',
    "book": '<path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H7a2 2 0 0 0-2 2z"/><path d="M5 20a2 2 0 0 0 2 2h12v-4"/>',
    "crate": '<path d="M3 8 12 3l9 5v8l-9 5-9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
    "practice": '<path d="M6.5 7v10M17.5 7v10M3.5 9.5v5M20.5 9.5v5M6.5 12h11"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.8h.01"/>',
    "copy": '<rect x="8.5" y="8.5" width="11.5" height="11.5" rx="2"/><path d="M15.5 8.5V5.5a1.5 1.5 0 0 0-1.5-1.5H5.5A1.5 1.5 0 0 0 4 5.5V14a1.5 1.5 0 0 0 1.5 1.5h3"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12.5A1.5 1.5 0 0 0 8.5 21h7a1.5 1.5 0 0 0 1.5-1.5L18 7M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7"/>',
    "up": '<path d="m6 15 6-6 6 6"/>',
    "down": '<path d="m6 9 6 6 6-6"/>',
    "grip": '<circle cx="9" cy="6" r="1.2" fill="currentColor"/><circle cx="15" cy="6" r="1.2" fill="currentColor"/><circle cx="9" cy="12" r="1.2" fill="currentColor"/><circle cx="15" cy="12" r="1.2" fill="currentColor"/><circle cx="9" cy="18" r="1.2" fill="currentColor"/><circle cx="15" cy="18" r="1.2" fill="currentColor"/>',
    "wand": '<path d="m4 20 10-10M14.5 3.5l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9zM19 9.5l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z"/>',
    "volume": '<path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z"/><path d="M15.5 9a4.2 4.2 0 0 1 0 6M18.2 6.5a8 8 0 0 1 0 11"/>',
    "grid": '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01"/>',
    "filter": '<path d="M4 5h16l-6.2 7.5V19l-3.6-1.8v-4.7z"/>',
    "bolt": '<path d="M13 2.5 4.5 13.5H11l-1 8 8.5-11H12z"/>',
    "github": '<path d="M12 2.8a9.3 9.3 0 0 0-2.9 18.1c.5.1.6-.2.6-.5v-1.7c-2.6.6-3.1-1.2-3.1-1.2-.4-1.1-1-1.4-1-1.4-.9-.6 0-.6 0-.6.9.1 1.4 1 1.4 1 .8 1.4 2.2 1 2.7.8.1-.6.3-1 .6-1.2-2-.2-4.2-1-4.2-4.6 0-1 .4-1.8 1-2.5-.1-.2-.4-1.2.1-2.5 0 0 .8-.2 2.6 1a8.9 8.9 0 0 1 4.7 0c1.8-1.2 2.6-1 2.6-1 .5 1.3.2 2.3.1 2.5.6.7 1 1.5 1 2.5 0 3.6-2.2 4.4-4.2 4.6.3.3.6.8.6 1.6v2.4c0 .3.2.6.7.5A9.3 9.3 0 0 0 12 2.8z" fill="currentColor" stroke="none"/>',
    "arrow-left": '<path d="M19 12H5m0 0 6-6m-6 6 6 6"/>',
    "arrow-right": '<path d="M5 12h14m0 0-6-6m6 6-6 6"/>',
    "spark": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>',
    "wave": '<path d="M3 12h2M7 8v8M11 5v14M15 9v6M19 7v10M21 12h0"/>',
    "keyboard": '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 10h.01M9 10h.01M12 10h.01M15 10h.01M18 10h.01M7 14h10"/>',
    "repeat": '<path d="M17 3l3 3-3 3M20 6H8a4 4 0 0 0-4 4v1M7 21l-3-3 3-3M4 18h12a4 4 0 0 0 4-4v-1"/>',
    "star": '<path d="m12 3.5 2.6 5.3 5.8.8-4.2 4.1 1 5.8L12 16.8l-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z"/>',
    "heart": '<path d="M12 20s-7.5-4.5-7.5-10A4.3 4.3 0 0 1 12 7.4 4.3 4.3 0 0 1 19.5 10c0 5.5-7.5 10-7.5 10z"/>',
}


def icon(name: str, cls: str = "") -> str:
    body = ICONS.get(name, "")
    c = f"icon {cls}".strip()
    return (f'<svg class="{c}" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" '
            f'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{body}</svg>')


BRAND_MARK = (
    '<svg class="brand-mark" viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
    '<defs><linearGradient id="bm-g" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#ff2bd6"/><stop offset=".55" stop-color="#8a5cff"/><stop offset="1" stop-color="#22e1ff"/>'
    '</linearGradient></defs>'
    '<circle cx="20" cy="20" r="18" fill="none" stroke="url(#bm-g)" stroke-width="3"/>'
    '<circle cx="20" cy="20" r="11.5" fill="none" stroke="url(#bm-g)" stroke-width="1.5" opacity=".55"/>'
    '<g fill="url(#bm-g)"><rect x="11" y="16" width="2.6" height="8" rx="1.3"/><rect x="15.4" y="12" width="2.6" height="16" rx="1.3"/>'
    '<rect x="19.8" y="9.5" width="2.6" height="21" rx="1.3"/><rect x="24.2" y="13.5" width="2.6" height="13" rx="1.3"/>'
    '<rect x="28.6" y="17" width="2.6" height="6" rx="1.3"/></g></svg>'
)

# --------------------------------------------------------------------------------------------- page shell
NAV = [
    ("home", "index.html", "בית"),
    ("guide", "guide/index.html", "הקורס"),
    ("library", "library.html", "ספריית מוזיקה"),
    ("practice", "practice.html", "אימון"),
    ("crates", "crates/index.html", "ארגזים"),
    ("sets", "sets/index.html", "סטים"),
    ("tools", "tools/index.html", "כלים"),
    ("about", "about.html", "אודות"),
]

TOOLS = [
    ("mix-trainer", "מאמן מיקס", "Mix Trainer", "mixer",
     "שני דקים בדפדפן עם EQ, פילטר, Tempo fader ומד פאזה שמראה בזמן אמת אם הביטים מסונכרנים."),
    ("camelot", "גלגל קאמלוט", "Camelot Wheel", "wheel",
     "לחצו על סולם וראו מה מתאים לו - ואיזה טראקים מהספרייה ומהארגזים יושבים בדיוק שם."),
    ("bpm", "BPM ומחשבון טמפו", "BPM Tapper", "metronome",
     "טפטפו על המקלדת כדי למדוד BPM, וחשבו כמה אחוז Pitch צריך כדי לעבור מטמפו לטמפו."),
    ("set-builder", "בונה סטים", "Set Builder", "setlist",
     "בנו סט מהטראקים שלנו: התאמת סולם ו-BPM לכל מעבר, עקומת אנרגיה וייצוא ל-M3U8."),
    ("rekordbox", "מחולל Rekordbox XML", "Rekordbox XML", "code",
     "קובץ XML מותאם לתיקייה שלכם - כל הטראקים נכנסים ל-Rekordbox עם Hot Cues ופלייליסטים."),
]

VERSION = "dev"


def shell(out: Path, *, title: str, body: str, active: str = "", description: str = "",
          scripts: tuple = (), data: tuple = (), body_class: str = "", full_title: str | None = None,
          extra_head: str = "") -> str:
    depth = len(out.relative_to(DOCS).parts) - 1
    base = "../" * depth or "./"
    root = "../" * (depth + 1)
    desc = description or "DJ Lab - קורס Rekordbox בעברית, מוזיקה מקורית ברישיון CC0 לתרגול, ארגזים וכלים אינטראקטיביים לתקליטנים מתחילים."
    page_title = full_title or f"{title} · DJ Lab"
    canonical = SITE_URL + "docs/" + out.relative_to(DOCS).as_posix()
    nav_items = []
    for key, href, label in NAV:
        cur = ' aria-current="page"' if key == active else ""
        nav_items.append(f'<li><a href="{base}{href}"{cur}>{label}</a></li>')
    data_tags = "".join(f'<script src="{base}data/{d}.js?v={VERSION}" defer></script>' for d in data)
    script_tags = "".join(f'<script src="{base}assets/js/{s}.js?v={VERSION}" defer></script>' for s in
                          ("icons.gen", "core", "player") + tuple(scripts))
    year = "2026"
    tools_css = f'\n<link rel="stylesheet" href="{base}assets/css/tools.css?v={VERSION}">' if active == "tools" else ""
    return f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(page_title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="djlab-root" content="{root}">
<meta name="djlab-base" content="{base}">
<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="#07070c">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="DJ Lab">
<meta property="og:locale" content="he_IL">
<meta property="og:title" content="{esc(page_title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="{SITE_URL}docs/assets/img/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{base}assets/img/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700;800&family=Rubik:wght@400;500;600;700;800&family=Secular+One&display=swap">
<link rel="stylesheet" href="{base}assets/css/site.css?v={VERSION}">{tools_css}
<script>(function(){{try{{var t=localStorage.getItem('djlab:theme');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t)}}catch(e){{}}}})();</script>
{extra_head}</head>
<body class="page-{esc(active or 'misc')} {esc(body_class)}">
<a class="skip-link" href="#main">דלגו לתוכן</a>
<header class="site-header">
  <div class="container header-inner">
    <a class="brand" href="{base}index.html" aria-label="DJ Lab - דף הבית">{BRAND_MARK}<span class="brand-word">DJ<b>Lab</b></span></a>
    <nav class="site-nav" id="site-nav" aria-label="ניווט ראשי"><ul>{''.join(nav_items)}</ul></nav>
    <div class="header-actions">
      <button class="icon-btn" type="button" data-theme-toggle aria-label="החלפה בין מצב כהה למצב בהיר" title="מצב כהה / בהיר">{icon('sun', 'i-sun')}{icon('moon', 'i-moon')}</button>
      <a class="icon-btn hide-sm" href="{REPO_URL}" target="_blank" rel="noopener" aria-label="הקוד ב-GitHub" title="GitHub">{icon('github')}</a>
      <button class="icon-btn nav-toggle" type="button" data-nav-toggle aria-expanded="false" aria-controls="site-nav" aria-label="פתיחת תפריט">{icon('menu')}</button>
    </div>
  </div>
</header>
<main id="main" tabindex="-1">
{body}
</main>
<footer class="site-footer">
  <div class="container footer-grid">
    <div class="footer-brand">
      <a class="brand" href="{base}index.html">{BRAND_MARK.replace('bm-g', 'bm-f')}<span class="brand-word">DJ<b>Lab</b></span></a>
      <p>בית הספר לתקלוט שלך: קורס Rekordbox בעברית, מוזיקה מקורית לתרגול וכלים שעובדים ישר בדפדפן.</p>
    </div>
    <nav aria-label="ללמוד"><h2>ללמוד</h2><ul>
      <li><a href="{base}guide/index.html">הקורס</a></li><li><a href="{base}practice.html">אימון ומעברים</a></li><li><a href="{base}sets/index.html">סטים לדוגמה</a></li></ul></nav>
    <nav aria-label="מוזיקה"><h2>מוזיקה</h2><ul>
      <li><a href="{base}library.html">ספריית מוזיקה</a></li><li><a href="{base}crates/index.html">ארגזים</a></li><li><a href="{base}tools/rekordbox.html">ייבוא ל-Rekordbox</a></li></ul></nav>
    <nav aria-label="כלים"><h2>כלים</h2><ul>
      <li><a href="{base}tools/mix-trainer.html">מאמן מיקס</a></li><li><a href="{base}tools/camelot.html">גלגל קאמלוט</a></li><li><a href="{base}tools/set-builder.html">בונה סטים</a></li></ul></nav>
  </div>
  <div class="container footer-legal">
    <p>המוזיקה המקורית משוחררת ב-<a href="https://creativecommons.org/publicdomain/zero/1.0/deed.he" target="_blank" rel="noopener">CC0</a> · הקוד ב-MIT · הארגזים הם קישורים בלבד - קנו והזרימו ממקורות חוקיים.</p>
    <p class="muted"><a href="{base}about.html">אודות ורישיון</a> · © {year} DJ Lab</p>
  </div>
</footer>
{data_tags}{script_tags}
</body>
</html>
"""


# --------------------------------------------------------------------------------------------- catalog
def load_plans():
    plan = read_json(ROOT / "music" / "tracklist.plan.json", []) or []
    extras = read_json(ROOT / "music" / "extras.plan.json", {}) or {}
    if not isinstance(plan, list):
        plan = []
    if not isinstance(extras, dict):
        extras = {}
    return plan, extras


def build_catalog(plan, extras):
    order = {t.get("id"): i for i, t in enumerate(plan)}
    for i, t in enumerate(extras.get("practice", [])):
        order.setdefault(t.get("id"), 1000 + i)
    for i, t in enumerate(extras.get("transitions", [])):
        order.setdefault(t.get("id"), 2000 + i)

    items: dict[str, dict] = {}
    cat = read_json(ROOT / "music" / "catalog.json", None)
    generated_at = None
    if isinstance(cat, dict):
        generated_at = cat.get("generated_at")
        for kind_key, kind in (("tracks", "track"), ("practice", "practice"), ("transitions", "transition")):
            for it in cat.get(kind_key, []) or []:
                if isinstance(it, dict) and it.get("id"):
                    it = dict(it)
                    it.setdefault("kind", kind)
                    items[it["id"]] = it
    # sidecars are the source of truth - they override catalog.json entries
    for sub, kind in (("tracks", "track"), ("practice", "practice"), ("transitions", "transition")):
        base = ROOT / "music" / sub
        if not base.exists():
            continue
        for js in sorted(base.rglob("*.json")):
            if js.name.endswith(".plan.json"):
                continue
            d = read_json(js, None)
            if not isinstance(d, dict) or not d.get("id"):
                continue
            d = dict(d)
            d["kind"] = d.get("kind") or kind
            if not d.get("file"):
                for ext in (".mp3", ".wav", ".ogg"):
                    if js.with_suffix(ext).exists():
                        d["file"] = js.with_suffix(ext).relative_to(ROOT).as_posix()
                        break
            if not d.get("cover") and js.with_suffix(".jpg").exists():
                d["cover"] = js.with_suffix(".jpg").relative_to(ROOT).as_posix()
            items[d["id"]] = d

    tracks, practice, transitions = [], [], []
    for it in items.values():
        f = it.get("file")
        fp = ROOT / f if f else None
        it["has_audio"] = bool(fp and fp.is_file())
        if it["has_audio"] and not it.get("size_bytes"):
            it["size_bytes"] = fp.stat().st_size
        c = it.get("cover")
        if c and not (ROOT / c).is_file():
            it.pop("cover", None)
        kind = it.get("kind", "track")
        (practice if kind == "practice" else transitions if kind == "transition" else tracks).append(it)
    key = lambda t: (order.get(t.get("id"), 5000), str(t.get("id")))
    tracks.sort(key=key)
    practice.sort(key=key)
    transitions.sort(key=key)
    out = {"tracks": tracks, "practice": practice, "transitions": transitions}
    if generated_at:
        out["generated_at"] = generated_at
    return out


def plan_summary(plan, extras):
    keep = ("id", "title", "title_he", "genre", "genre_slug", "family", "bpm", "key", "key_short", "camelot",
            "energy", "role", "target_minutes", "file_stem")
    return {
        "tracks": [{k: t.get(k) for k in keep if k in t} for t in plan],
        "practice": [dict(t) for t in extras.get("practice", [])],
        "transitions": [dict(t) for t in extras.get("transitions", [])],
    }


# --------------------------------------------------------------------------------------------- peaks
def _ffmpeg_ok() -> bool:
    return shutil.which("ffmpeg") is not None


def compute_peaks(path: Path, n: int = PEAK_POINTS):
    import numpy as np  # local import: optional dependency

    sr = 11025
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True, timeout=180).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    if x.size < n * 32:
        return None
    L = x.size // n
    x = x[: L * n].reshape(n, L).astype(np.float64)
    spec = np.abs(np.fft.rfft(x * np.hanning(L), axis=1)) ** 2
    freqs = np.fft.rfftfreq(L, 1.0 / sr)
    bands = [freqs < 200, (freqs >= 200) & (freqs < 2500), freqs >= 2500]
    weights = [1.0, 0.78, 0.55]
    out = np.zeros((n, 3))
    for i, (mask, w) in enumerate(zip(bands, weights)):
        amp = np.sqrt(spec[:, mask].sum(axis=1))
        ref = np.percentile(amp, 98) or 1.0
        out[:, i] = np.clip(amp / ref, 0, 1) ** 0.85 * w
    # overall loudness envelope keeps quiet passages quiet
    env = np.abs(x).max(axis=1)
    env = env / (np.percentile(env, 99) or 1.0)
    out *= np.clip(env, 0.08, 1.0)[:, None] ** 0.5
    b = np.clip(np.round(out * 255), 0, 255).astype(np.uint8).reshape(-1)
    return base64.b64encode(b.tobytes()).decode("ascii")


def load_existing_peaks() -> dict:
    p = DATA / "peaks.js"
    if not p.exists():
        return {}
    txt = read_text(p)
    m = re.search(r"=\s*(\{.*\})\s*;?\s*$", txt, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1)).get("files", {})
    except Exception:
        return {}


def build_peaks(catalog, mode: str):
    existing = load_existing_peaks()
    files = []
    for group in ("tracks", "practice", "transitions"):
        for it in catalog[group]:
            if it.get("file"):
                files.append(it["file"])
    result: dict[str, str] = {}
    todo = []
    can_compute = mode != "never" and _ffmpeg_ok()
    try:
        import numpy  # noqa: F401
    except Exception:
        can_compute = False
    if mode != "never" and not can_compute:
        warn("ffmpeg/numpy unavailable - waveform peaks reused from docs/data/peaks.js where possible")
    CACHE.mkdir(parents=True, exist_ok=True) if can_compute else None
    for f in files:
        fp = ROOT / f
        if not fp.is_file() or not can_compute:
            if f in existing:
                result[f] = existing[f]
            continue
        st = fp.stat()
        ck = CACHE / (hashlib.sha1(f.encode()).hexdigest()[:16] + ".json")
        c = read_json(ck, None)
        if isinstance(c, dict) and c.get("mtime") == st.st_mtime and c.get("size") == st.st_size and c.get("n") == PEAK_POINTS:
            if c.get("data"):
                result[f] = c["data"]
            continue
        todo.append((f, fp, st, ck))

    def work(job):
        f, fp, st, ck = job
        try:
            d = compute_peaks(fp)
        except Exception as e:
            warn(f"peaks failed for {f}: {e}")
            d = None
        try:
            ck.write_text(json.dumps({"mtime": st.st_mtime, "size": st.st_size, "n": PEAK_POINTS, "data": d}))
        except Exception:
            pass
        return f, d

    if todo:
        with ThreadPoolExecutor(max_workers=max(2, (os.cpu_count() or 2))) as ex:
            for f, d in ex.map(work, todo):
                if d:
                    result[f] = d
    STATS["peaks_computed"] = len(todo)
    ordered = {f: result[f] for f in files if f in result}
    return {"n": PEAK_POINTS, "bands": ["low", "mid", "high"], "files": ordered}


# --------------------------------------------------------------------------------------------- markdown
CALLOUT_TYPES = [
    ("tip", ("💡",), "טיפ", "bulb"),
    ("warn", ("⚠", "❗", "🚫"), "זהירות", "alert"),
    ("exercise", ("🎧",), "תרגיל", "headphones"),
    ("rekordbox", ("🎚", "🎛"), "ב-Rekordbox", "sliders"),
    ("note", ("📌", "ℹ", "📝", "🧠", "🔎"), "שימו לב", "info"),
]
_EMOJI_RE = "|".join(re.escape(e) for t in CALLOUT_TYPES for e in t[1])
CALLOUT_RE = re.compile(
    r"^\s*<p>\s*(?:<(?:strong|b)>\s*)?(" + _EMOJI_RE + r")\ufe0f?\s*(?:<(?:strong|b)>\s*)?([^<:\n]{0,40}?:)?\s*(?:</(?:strong|b)>)?\s*",
    re.S,
)


def md_to_html(text: str):
    if markdown is None:
        return "<pre>" + esc(text) + "</pre>", []
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "attr_list", "md_in_html", "sane_lists"],
        extension_configs={"toc": {"slugify": slugify_unicode, "permalink": "#", "permalink_class": "anchor",
                                   "permalink_title": "קישור ישיר לסעיף", "toc_depth": "2-3"}},
        output_format="html",
    )
    out = md.convert(text)
    return out, getattr(md, "toc_tokens", [])


class Ctx:
    """Link-rewriting context for one rendered markdown document."""

    def __init__(self, src: Path, out: Path, catalog_files: set[str], track_ids: set[str]):
        self.src, self.out, self.files, self.ids = src, out, catalog_files, track_ids
        self.audio_refs: list[str] = []
        self.track_refs: list[str] = []


def map_repo_path(rp: str, ctx: Ctx):
    """Map a repo-relative path to (href, kind). kind: page|published|audio|github"""
    p = rp.rstrip("/")
    low = p.lower()
    if re.fullmatch(r"guide/\d\d[^/]*\.md", p):
        return rel(ctx.out, DOCS / "guide" / (Path(p).stem + ".html")), "page"
    if low in ("guide", "guide/readme.md", "guide/index.md"):
        return rel(ctx.out, DOCS / "guide" / "index.html"), "page"
    if re.fullmatch(r"guide/[^/]+\.md", p) and (ROOT / p).is_file():
        return rel(ctx.out, DOCS / "guide" / (Path(p).stem + ".html")), "page"
    if re.fullmatch(r"crates/[^/]+\.md", p) and not low.endswith("readme.md"):
        return rel(ctx.out, DOCS / "crates" / (Path(p).stem + ".html")), "page"
    if low in ("crates", "crates/readme.md", "crates/index.json"):
        return rel(ctx.out, DOCS / "crates" / "index.html"), "page"
    if re.fullmatch(r"sets/[^/]+\.md", p) and not low.endswith("readme.md"):
        return rel(ctx.out, DOCS / "sets" / (Path(p).stem + ".html")), "page"
    if low in ("sets", "sets/readme.md"):
        return rel(ctx.out, DOCS / "sets" / "index.html"), "page"
    if low.startswith("docs/"):
        return rel(ctx.out, ROOT / p), "page"
    if low in ("music/license.md",):
        return rel(ctx.out, DOCS / "about.html"), "page"
    if low.startswith("music/") and Path(p).suffix.lower() in AUDIO_EXT:
        return rel(ctx.out, ROOT / p), "audio"
    if low in ("music/tracks", "music"):
        return rel(ctx.out, DOCS / "library.html"), "page"
    if low in ("music/practice", "music/transitions"):
        return rel(ctx.out, DOCS / "practice.html"), "page"
    if (low.startswith("music/") or low.startswith("crates/")) and Path(p).suffix:
        return rel(ctx.out, ROOT / p), "published"
    kind = "blob" if Path(p).suffix else "tree"
    return f"{REPO_URL}/{kind}/HEAD/{p}", "github"


def resolve_href(href: str, ctx: Ctx):
    if not href or href.startswith(("#", "mailto:", "tel:", "data:", "javascript:")):
        return href, "anchor"
    if re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I):
        return href, "external"
    path, frag = (href.split("#", 1) + [""])[:2]
    path = path.split("?", 1)[0]
    if not path:
        return href, "anchor"
    from urllib.parse import unquote

    path = unquote(path)
    if path.startswith("/"):
        target = (ROOT / path.lstrip("/")).resolve()
    else:
        target = (ctx.src.parent / path).resolve()
        if not str(target).startswith(str(ROOT)) or not (target.exists() or target.parent.exists()):
            # authors sometimes write repo-root-relative paths without ../
            alt = (ROOT / path).resolve()
            if alt.exists():
                target = alt
    try:
        rp = target.relative_to(ROOT).as_posix()
    except ValueError:
        return href, "external"
    new, kind = map_repo_path(rp, ctx)
    if kind == "audio":
        return rp, kind
    if frag and kind in ("page", "github"):
        new += "#" + frag
    return new, kind


A_RE = re.compile(r'<a\s+([^>]*?)href="([^"]*)"([^>]*)>(.*?)</a>', re.S)
IMG_RE = re.compile(r'<img\s+([^>]*?)src="([^"]*)"([^>]*?)\s*/?>', re.S)


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def mini_player(rp: str, label: str, ctx: Ctx) -> str:
    exists = (ROOT / rp).is_file()
    ctx.audio_refs.append(rp)
    title = strip_tags(label) or Path(rp).stem
    href = rel(ctx.out, ROOT / rp)
    missing = "" if exists else ' data-missing="1"'
    return (f'<span class="mp" data-src="{esc(rp)}" data-title="{esc(title)}"{missing}>'
            f'<a class="mp-fallback" href="{esc(href)}" download>{label}</a></span>')


def postprocess(h: str, ctx: Ctx) -> str:
    # links
    def a_repl(m):
        pre, href, post, inner = m.group(1), html.unescape(m.group(2)), m.group(3), m.group(4)
        if 'class="anchor"' in pre + post:
            return m.group(0)
        new, kind = resolve_href(href, ctx)
        if kind == "audio":
            return mini_player(new, inner, ctx)
        attrs = f'{pre}href="{esc(new)}"{post}'
        if kind in ("external", "github") and "target=" not in attrs:
            attrs += ' target="_blank" rel="noopener"'
        if kind == "published" and new.lower().endswith((".csv", ".xml", ".m3u8", ".zip", ".jpg", ".json")):
            attrs += " download"
        return f"<a {attrs}>{inner}</a>"

    h = A_RE.sub(a_repl, h)

    # images
    def img_repl(m):
        pre, src, post = m.group(1), m.group(2), m.group(3)
        if re.match(r"^[a-z]+:", src, re.I):
            new = src
        else:
            target = (ctx.src.parent / src.split("#")[0]).resolve()
            try:
                rp = target.relative_to(ROOT).as_posix()
            except ValueError:
                rp = None
            if rp and rp.startswith("guide/assets/"):
                new = rel(ctx.out, DOCS / "assets" / "guide" / rp[len("guide/assets/"):])
            elif rp:
                new = rel(ctx.out, ROOT / rp)
                if not rp.startswith(("music/", "crates/", "docs/")):
                    new = f"{REPO_URL}/raw/HEAD/{rp}"
            else:
                new = src
        extra = "" if "loading=" in pre + post else ' loading="lazy" decoding="async"'
        return f'<img {pre}src="{esc(new)}"{post}{extra}>'

    h = IMG_RE.sub(img_repl, h)

    # lone images -> figures
    def fig_repl(m):
        img = m.group(1)
        alt = re.search(r'alt="([^"]*)"', img)
        cap = f"<figcaption>{alt.group(1)}</figcaption>" if alt and alt.group(1).strip() else ""
        return f'<figure class="figure">{img}{cap}</figure>'

    h = re.sub(r"<p>\s*(<img [^>]+>)\s*</p>", fig_repl, h)

    # callouts
    def bq_repl(m):
        inner = m.group(1)
        cm = CALLOUT_RE.match(inner)
        if not cm:
            return f'<blockquote class="quote">{inner}</blockquote>'
        emo = cm.group(1)
        ctype, label, ic = "note", "שימו לב", "info"
        for t, emojis, lab, icn in CALLOUT_TYPES:
            if any(emo.startswith(e) for e in emojis):
                ctype, label, ic = t, lab, icn
                break
        if cm.group(2):
            label = cm.group(2).rstrip(":").strip() or label
        rest = "<p>" + inner[cm.end():]
        rest = re.sub(r"^<p>\s*(?:</(?:strong|b)>\s*)?</p>\s*", "", rest)
        return (f'<aside class="callout callout--{ctype}" role="note">'
                f'<div class="callout-head">{icon(ic)}<span>{esc(label)}</span></div>'
                f'<div class="callout-body">{rest}</div></aside>')

    start_re = re.compile(r"<p>\s*(?:<(?:strong|b)>\s*)?(?:" + _EMOJI_RE + r")")

    def bq_split(m):
        inner = m.group(1)
        # one blockquote may hold several callouts (e.g. an exercise followed by a "💡 טיפ:" paragraph)
        cuts = [mm.start() for mm in start_re.finditer(inner)]
        if len(cuts) <= 1 or cuts[0] != 0 and len(cuts) == 1:
            return bq_repl(m)
        if cuts[0] != 0:
            cuts = [0] + cuts
        parts = [inner[a:b].strip() for a, b in zip(cuts, cuts[1:] + [len(inner)])]
        return "".join(bq_repl(re.match(r"(.*)", p_, re.S)) for p_ in parts if p_)

    h = re.sub(r"<blockquote>\s*(.*?)\s*</blockquote>", bq_split, h, flags=re.S)

    # bidi: numeric ranges written with an en/em dash ("95–130") would render reversed in RTL text
    def bidi_ranges(seg):
        return re.sub(r"(?<![\w.])(\d+(?:[.,]\d+)?%?\s?[–—]\s?\d+(?:[.,]\d+)?%?)(?![\w])", r'<bdi dir="ltr">\1</bdi>', seg)

    out, pos = [], 0
    for mm in re.finditer(r"<pre[\s>].*?</pre>|<[^>]+>", h, re.S):
        out.append(bidi_ranges(h[pos:mm.start()]))
        out.append(mm.group(0))
        pos = mm.end()
    out.append(bidi_ranges(h[pos:]))
    h = "".join(out)

    # tables
    h = re.sub(r"<table>", '<div class="table-wrap" role="region" aria-label="טבלה" tabindex="0"><table>', h)
    h = h.replace("</table>", "</table></div>")
    # code blocks LTR
    h = h.replace("<pre>", '<pre dir="ltr">')

    # inline references to our track ids: <code>house-05</code>
    def code_repl(m):
        tid = m.group(1)
        if tid in ctx.ids:
            ctx.track_refs.append(tid)
            return f'<span class="tref" data-id="{tid}"><code>{tid}</code></span>'
        return m.group(0)

    h = re.sub(r"<code>((?:house|techno|mainstream|breadth|practice|transition)-\d\d)</code>", code_repl, h)

    # inline code that names an audio file in the repo: <code>music/tracks/x/y.mp3</code> -> inline play chip
    def file_repl(m):
        rp = html.unescape(m.group(1)).lstrip("./")
        if not (ROOT / rp).is_file() and rp not in ctx.files:
            return f'<span class="tref" data-file="{esc(rp)}" data-missing="1">{m.group(0)}</span>'
        ctx.audio_refs.append(rp)
        return f'<span class="tref" data-file="{esc(rp)}">{m.group(0)}</span>'

    h = re.sub(r"<code>((?:\.\./)?music/[^<\s]+\.(?:mp3|wav|ogg))</code>", file_repl, h)
    return h


def toc_html(tokens, max_level=3) -> str:
    if not tokens:
        return ""
    items = []
    for t in tokens:
        if t.get("level", 2) > max_level:
            continue
        sub = toc_html(t.get("children", []), max_level)
        name = strip_tags(t.get("name", ""))
        items.append(f'<li><a href="#{esc(t["id"])}" data-toc-link>{esc(name)}</a>{sub}</li>')
    return f"<ol>{''.join(items)}</ol>" if items else ""


def flatten_toc(tokens):
    out = []
    for t in tokens or []:
        out.append({"id": t.get("id"), "title": strip_tags(t.get("name", "")), "level": t.get("level")})
        out.extend(flatten_toc(t.get("children", [])))
    return out


# --------------------------------------------------------------------------------------------- guide
def build_guide(ctx_base):
    src_dir = ROOT / "guide"
    files = sorted(p for p in src_dir.glob("*.md") if re.match(r"^\d{2}-", p.name)) if src_dir.exists() else []
    extra = sorted(p for p in src_dir.glob("*.md") if not re.match(r"^\d{2}-", p.name)
                   and p.stem.lower() not in ("readme", "index")) if src_dir.exists() else []
    # assets
    adir = src_dir / "assets"
    if adir.exists():
        for f in adir.rglob("*"):
            if f.is_file():
                dst = DOCS / "assets" / "guide" / f.relative_to(adir)
                write(dst, f.read_bytes())
    chapters = []
    for f in files + extra:
        text = read_text(f)
        fm, body = parse_front_matter(text)
        appendix = f in extra
        num = fm.get("chapter")
        try:
            num = int(num)
        except Exception:
            num = int(f.name[:2]) if not appendix else 0
        if appendix:
            num = 900 + extra.index(f)
        out = DOCS / "guide" / (f.stem + ".html")
        # drop a leading H1 (the page renders its own title)
        h1 = re.match(r"^\s*#\s+(.+?)\s*\n", body)
        title = str(fm.get("title") or (h1.group(1) if h1 else f.stem))
        if h1:
            body = body[h1.end():]
        chapters.append({
            "src": f, "out": out, "fm": fm, "body": body,
            "chapter": num, "slug": str(fm.get("slug") or (f.stem if appendix else f.stem[3:])), "file": f.stem, "appendix": appendix,
            "title": title, "title_en": str(fm.get("title_en") or ""), "summary": str(fm.get("summary") or ""),
            "level": str(fm.get("level") or ""), "reading_minutes": fm.get("reading_minutes"),
        })
    chapters.sort(key=lambda c: (c["chapter"], c["file"]))
    toc_data = []
    for i, c in enumerate(chapters):
        ctx = Ctx(c["src"], c["out"], *ctx_base)
        body_html, toc = md_to_html(c["body"])
        body_html = postprocess(body_html, ctx)
        words = len(strip_tags(body_html).split())
        rm = c["reading_minutes"]
        try:
            rm = int(rm)
        except Exception:
            rm = max(1, round(words / 180))
        c["reading_minutes"] = rm
        prev_c = chapters[i - 1] if i > 0 else None
        next_c = chapters[i + 1] if i + 1 < len(chapters) else None
        c["toc"] = flatten_toc(toc)
        c["html"] = body_html
        c["toc_html"] = toc_html(toc)
        c["audio"] = ctx.audio_refs
        c["prev"], c["next"] = prev_c, next_c
        toc_data.append({
            "chapter": c["chapter"], "num": "" if c["appendix"] else f"{c['chapter']:02d}", "appendix": c["appendix"], "slug": c["slug"], "file": c["file"],
            "title": c["title"], "title_en": c["title_en"], "summary": c["summary"], "level": c["level"],
            "level_he": LEVEL_HE.get(c["level"].lower(), c["level"]), "reading_minutes": rm,
            "href": f"guide/{c['file']}.html", "headings": [t for t in c["toc"] if t["level"] == 2],
            "audio_count": len(ctx.audio_refs),
        })
    n_main = sum(1 for c in chapters if not c["appendix"])
    for c in chapters:
        write(c["out"], render_chapter(c, n_main))
    return chapters, toc_data


def level_badge(level: str) -> str:
    if not level:
        return ""
    he = LEVEL_HE.get(level.lower(), level)
    return f'<span class="badge badge--level" data-level="{esc(level.lower())}">{esc(he)}</span>'


def render_chapter(c, total) -> str:
    num = f"{c['chapter']:02d}" if not c.get("appendix") else ""

    def nav_card(o, dirn):
        if not o:
            return '<span class="pn-spacer"></span>'
        lab = "הפרק הקודם" if dirn == "prev" else "הפרק הבא"
        ic = icon("arrow-right" if dirn == "prev" else "arrow-left")
        return (f'<a class="pn-card pn-{dirn}" href="{esc(o["file"])}.html">'
                f'<span class="pn-label">{ic if dirn == "prev" else ""}{lab}{ic if dirn == "next" else ""}</span>'
                f'<span class="pn-title">' + ("" if o.get("appendix") else f'<span class="pn-num">{o["chapter"]:02d}</span>') + f'{esc(o["title"])}</span></a>')

    toc_block = ""
    if c["toc_html"]:
        toc_block = f"""<aside class="chapter-toc" aria-label="תוכן הפרק">
  <details class="toc-box" open data-toc-details>
    <summary>{icon('list')}<span>בפרק הזה</span>{icon('chev-down', 'toc-chev')}</summary>
    <nav class="toc-nav">{c['toc_html']}</nav>
  </details>
</aside>"""
    title_en = f'<p class="chapter-en" dir="ltr">{esc(c["title_en"])}</p>' if c["title_en"] else ""
    summary = f'<p class="lead">{esc(c["summary"])}</p>' if c["summary"] else ""
    audio_note = ""
    if c["audio"]:
        audio_note = f'<span class="meta-item">{icon("headphones")}{len(c["audio"])} קטעי שמע</span>'
    body = f"""<div class="reading-progress" aria-hidden="true"><span data-reading-bar></span></div>
<article class="chapter" data-chapter="{esc(c['file'])}" data-chapter-num="{num}">
  <header class="chapter-hero">
    <div class="container">
      <nav class="crumbs" aria-label="פירורי לחם"><a href="../index.html">בית</a><span aria-hidden="true">/</span><a href="index.html">הקורס</a><span aria-hidden="true">/</span><span aria-current="page">{f"פרק {num}" if num else esc(c["title"])}</span></nav>
      <div class="chapter-hero-grid">
        <div class="chapter-num{'' if num else ' chapter-num--icon'}" aria-hidden="true">{num or icon('book')}</div>
        <div>
          <p class="eyebrow">{f"פרק {num} מתוך {total}" if num else "נספח לקורס"}</p>
          <h1 class="chapter-title">{esc(c['title'])}</h1>
          {title_en}
          {summary}
          <div class="chapter-meta">
            <span class="meta-item">{icon('clock')}{c['reading_minutes']} דק' קריאה</span>
            {level_badge(c['level'])}
            {audio_note}
            <span class="meta-item read-state" data-read-state hidden>{icon('check')}נקרא</span>
          </div>
        </div>
      </div>
    </div>
  </header>
  <div class="container chapter-layout{' no-toc' if not toc_block else ''}">
    {toc_block}
    <div class="prose" data-prose>
      {c['html']}
      <div class="chapter-done">
        <button class="btn btn--ghost" type="button" data-mark-read>{icon('check')}<span>סימון הפרק כנקרא</span></button>
      </div>
    </div>
  </div>
  <nav class="container pn" aria-label="ניווט בין פרקים">{nav_card(c['prev'], 'prev')}{nav_card(c['next'], 'next')}</nav>
</article>"""
    return shell(c["out"], title=f"{num} · {c['title']}" if num else c["title"], body=body, active="guide",
                 description=c["summary"] or c["title"], scripts=("guide",), data=("catalog", "peaks", "guide"),
                 body_class="has-progress")


def render_guide_index(toc_data) -> str:
    out = DOCS / "guide" / "index.html"
    appendices = [t for t in toc_data if t.get("appendix")]
    toc_data = [t for t in toc_data if not t.get("appendix")]
    if toc_data:
        rows = []
        for t in toc_data:
            heads = "".join(f"<li>{esc(h['title'])}</li>" for h in t["headings"][:4])
            heads_html = f'<ul class="ch-heads">{heads}</ul>' if heads else ""
            en = f'<span class="ch-en" dir="ltr">{esc(t["title_en"])}</span>' if t["title_en"] else ""
            rows.append(f"""<li class="ch-row" data-chapter="{esc(t['file'])}">
  <a class="ch-link" href="{esc(t['file'])}.html">
    <span class="ch-num" aria-hidden="true">{t['num']}</span>
    <span class="ch-main">
      <span class="ch-title">{esc(t['title'])}</span>{en}
      <span class="ch-summary">{esc(t['summary'])}</span>
      {heads_html}
    </span>
    <span class="ch-side">
      <span class="meta-item">{icon('clock')}{t['reading_minutes']} דק'</span>
      {level_badge(t['level'])}
      <span class="ch-check" aria-hidden="true">{icon('check')}</span>
      <span class="sr-only ch-sr" data-sr-read></span>
    </span>
  </a>
</li>""")
        total_min = sum(t["reading_minutes"] for t in toc_data)
        listing = f'<ol class="ch-list" data-guide-list>{"".join(rows)}</ol>'
        if appendices:
            listing += '<h2 class="section-title" style="margin-top:var(--s6)">נספחים</h2><ul class="appx-grid">' + "".join(
                f'<li><a class="card card--link appx" href="{esc(t["file"])}.html">{icon("book")}<span><b>{esc(t["title"])}</b><span class="muted small">{esc(t["summary"])}</span></span></a></li>'
                for t in appendices) + '</ul>'
        stats = f"""<div class="guide-progress card" data-guide-progress>
  <div class="gp-ring" aria-hidden="true"><svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="52" class="gp-track"/><circle cx="60" cy="60" r="52" class="gp-fill" data-gp-fill/></svg><span data-gp-pct>0%</span></div>
  <div class="gp-text">
    <p class="gp-title"><span data-gp-done>0</span> מתוך {len(toc_data)} פרקים הושלמו</p>
    <p class="muted">{len(toc_data)} פרקים · כ-{total_min} דקות קריאה · ההתקדמות נשמרת בדפדפן שלכם</p>
    <div class="gp-actions"><a class="btn btn--primary" href="{esc(toc_data[0]['file'])}.html" data-continue>{icon('play')}<span>להתחיל מההתחלה</span></a>
    <button class="btn btn--ghost btn--sm" type="button" data-reset-progress>איפוס התקדמות</button></div>
  </div>
</div>"""
    else:
        listing = empty_state("הקורס נכתב ממש עכשיו", "הפרקים יופיעו כאן אוטומטית ברגע שיתווספו לתיקייה guide/ ויריצו את build_site.py.", "book")
        stats = ""
    body = f"""<section class="page-hero">
  <div class="container">
    <p class="eyebrow">{icon('book')}קורס Rekordbox בעברית</p>
    <h1 class="display">הקורס</h1>
    <p class="lead">מאפס ועד הסט הראשון: ציוד, Rekordbox, ביטמאצ'ינג באוזן, פרייזים, EQ, מיקס הרמוני ובניית סט. כל פרק עם תרגילים וקטעי שמע מהספרייה שלנו.</p>
  </div>
</section>
<section class="container guide-index">
  {stats}
  {listing}
</section>"""
    return shell(out, title="הקורס", body=body, active="guide", scripts=("guide",), data=("guide",),
                 description="כל פרקי קורס ה-Rekordbox של DJ Lab - בעברית, עם תרגילים ומוזיקה לתרגול.")


def empty_state(title: str, text: str, ic: str = "info") -> str:
    return f'<div class="empty card">{icon(ic, "empty-icon")}<h2>{esc(title)}</h2><p>{esc(text)}</p></div>'


# --------------------------------------------------------------------------------------------- crates
def read_csv_rows(p: Path):
    try:
        txt = p.read_text(encoding="utf-8-sig")
    except Exception:
        return []
    rows = []
    try:
        for r in csv.DictReader(io.StringIO(txt)):
            rows.append({(k or "").strip(): (v or "").strip() for k, v in r.items() if k})
    except Exception as e:
        warn(f"bad CSV {p.relative_to(ROOT)}: {e}")
    return rows


def md_table_sections(md: str) -> list:
    """Section heading (h3/h4) for every row of the markdown track tables, in order."""
    out, sec, lines, i = [], None, md.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        m = re.match(r"^(#{2,4})\s+(.+?)\s*#*\s*$", ln)
        if m:
            sec = None if len(m.group(1)) == 2 else re.sub(r"[`*_]", "", m.group(2)).strip()
        if ln.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|\s*:?-", lines[i + 1]):
            is_tracks = "bpm" in ln.lower()
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                if is_tracks:
                    out.append(sec)
                i += 1
            continue
        i += 1
    return out


def build_crates(ctx_base):
    cdir = ROOT / "crates"
    index_json = read_json(cdir / "index.json", []) or []
    meta_by_slug = {str(x.get("slug")): x for x in index_json if isinstance(x, dict) and x.get("slug")}
    slugs = set()
    if cdir.exists():
        for p in cdir.iterdir():
            if p.suffix in (".md", ".csv") and p.stem.lower() not in ("readme", "index"):
                slugs.add(p.stem)
    crates = []
    for slug in sorted(slugs):
        mdp, csvp = cdir / f"{slug}.md", cdir / f"{slug}.csv"
        fm, body = ({}, "")
        if mdp.exists():
            fm, body = parse_front_matter(read_text(mdp))
        meta = meta_by_slug.get(slug, {})
        rows = read_csv_rows(csvp) if csvp.exists() else []
        secs = md_table_sections(body) if body else []
        if rows and len(secs) == len(rows) and len({x for x in secs if x}) > 1:
            for r, sec in zip(rows, secs):
                if sec:
                    r["section"] = sec
        h1 = re.match(r"^\s*#\s+(.+?)\s*\n", body)
        title_he = str(fm.get("title_he") or meta.get("title_he") or (h1.group(1) if h1 else "") or slug)
        if h1:
            body = body[h1.end():]
        title = str(fm.get("title") or meta.get("title") or slug.replace("_", " ").replace("-", " ").title())
        genres = [GENRE_NAMES.get(g, g.replace("_", " ").title() if re.fullmatch(r"[a-z0-9_]+", g) else g)
                  for g in as_list(fm.get("genres") or meta.get("genres"))]
        count = len(rows) or fm.get("count") or meta.get("count") or 0
        verified = sum(1 for r in rows if r.get("verified", "").lower() == "yes")
        bpms = [float(r["bpm"]) for r in rows if re.fullmatch(r"\d+(\.\d+)?", r.get("bpm", "") or "")]
        intro = ""
        m = re.search(r"^(?!\s*[#|>\-*!\[])(\S.+)$", body, re.M)
        if m:
            intro = clip(strip_tags(md_to_html(m.group(1))[0]), 300)
        crates.append({
            "slug": slug, "title": title, "title_he": title_he, "genres": genres, "count": int(count or 0),
            "verified": verified, "bpm_min": min(bpms) if bpms else None, "bpm_max": max(bpms) if bpms else None,
            "href": f"crates/{slug}.html", "csv": f"crates/{slug}.csv" if csvp.exists() else None,
            "intro": str(fm.get("summary") or fm.get("description") or intro), "tracks": rows,
            "_body": body, "_src": mdp if mdp.exists() else csvp,
        })
    for c in crates:
        out = DOCS / "crates" / f"{c['slug']}.html"
        ctx = Ctx(c["_src"], out, *ctx_base)
        body_html = ""
        if c["_body"].strip():
            body_html, _ = md_to_html(c["_body"])
            body_html = postprocess(body_html, ctx)
        write(out, render_crate(c, body_html, out))
    write(DOCS / "crates" / "index.html", render_crates_index(crates))
    return [{k: v for k, v in c.items() if not k.startswith("_")} for c in crates]


def render_crate(c, body_html: str, out: Path) -> str:
    placeholder = '<div class="crate-table" id="crate-table" data-crate="' + esc(c["slug"]) + '"></div>'
    if c["tracks"]:
        # the CSV is the source of truth: drop every markdown track table (and the sub-heading right above it)
        # and put the interactive table where the first one was
        pat = re.compile(r'(?:<h[34][^>]*>(?:(?!</h[34]>).)*</h[34]>\s*)?<div class="table-wrap"[^>]*><table>\s*<thead>(?:(?!</thead>).)*?BPM(?:(?!</table>).)*</table></div>', re.S)
        first = pat.search(body_html)
        if first:
            body_html = body_html[: first.start()] + "\x00" + body_html[first.end():]
            body_html = pat.sub("", body_html).replace("\x00", placeholder)
        else:
            body_html = body_html + placeholder
    genres = "".join(f'<span class="chip chip--static">{esc(g)}</span>' for g in c["genres"])
    bpm = ""
    if c["bpm_min"]:
        bpm = f'<span class="meta-item">{icon("metronome")}<bdi dir="ltr">{c["bpm_min"]:g}–{c["bpm_max"]:g} BPM</bdi></span>'
    csv_btn = ""
    if c["csv"]:
        csv_btn = f'<a class="btn btn--ghost btn--sm" href="{rel(out, ROOT / c["csv"])}" download>{icon("download")}<span>הורדת CSV</span></a>'
    body = f"""<section class="page-hero page-hero--crate">
  <div class="container">
    <nav class="crumbs" aria-label="פירורי לחם"><a href="../index.html">בית</a><span aria-hidden="true">/</span><a href="index.html">ארגזים</a><span aria-hidden="true">/</span><span aria-current="page">{esc(c['title_he'])}</span></nav>
    <p class="eyebrow">{icon('crate')}ארגז · <span dir="ltr">{esc(c['title'])}</span></p>
    <h1 class="display">{esc(c['title_he'])}</h1>
    <div class="chip-row">{genres}</div>
    <div class="chapter-meta">
      <span class="meta-item">{icon('disc')}{c['count']} טראקים</span>
      <span class="meta-item">{icon('check')}{c['verified']} מאומתים</span>
      {bpm}
      {csv_btn}
    </div>
  </div>
</section>
<section class="container crate-page">
  <div class="callout callout--note crate-legal" role="note"><div class="callout-head">{icon('info')}<span>שירים אמיתיים - קישורים בלבד</span></div>
  <div class="callout-body"><p>הארגז הזה הוא רשימת קניות: אין כאן קבצי אודיו. קנו ב-Beatport / Bandcamp / Traxsource או הזרימו מתוך Rekordbox (Beatport Streaming, SoundCloud, TIDAL). ערכי BPM ו-Key עם תג <b>מאומת</b> נבדקו מול מקור אמין.</p></div></div>
  <div class="prose prose--wide">{body_html or placeholder}</div>
</section>"""
    return shell(out, title=c["title_he"], body=body, active="crates", scripts=("crates",), data=("catalog", "crates"),
                 description=f"ארגז {c['title_he']} ({c['title']}): {c['count']} טראקים עם BPM, Key ו-Camelot.")


def render_crates_index(crates) -> str:
    out = DOCS / "crates" / "index.html"
    if crates:
        cards = []
        for c in crates:
            genres = "".join(f'<span class="chip chip--static chip--sm">{esc(g)}</span>' for g in c["genres"][:4])
            pct = round(100 * c["verified"] / c["count"]) if c["count"] else 0
            bpm = f'<bdi dir="ltr">{c["bpm_min"]:g}–{c["bpm_max"]:g} BPM</bdi>' if c["bpm_min"] else ""
            cards.append(f"""<li><a class="crate-card card card--link" href="{esc(c['slug'])}.html">
  <span class="crate-art" aria-hidden="true" data-seed="{esc(c['slug'])}"></span>
  <span class="crate-body">
    <span class="crate-en" dir="ltr">{esc(c['title'])}</span>
    <span class="crate-title">{esc(c['title_he'])}</span>
    <span class="crate-intro">{esc(c['intro'])}</span>
    <span class="chip-row">{genres}</span>
    <span class="crate-stats"><span>{icon('disc')}{c['count']} טראקים</span><span>{bpm}</span><span class="verified-bar" title="{pct}% מאומתים"><i style="--p:{pct}%"></i></span></span>
  </span></a></li>""")
        listing = f'<ul class="crate-grid">{"".join(cards)}</ul>'
    else:
        listing = empty_state("הארגזים בדרך", "רשימות השירים האמיתיים (עם BPM, Key וקישורי קנייה) יופיעו כאן ברגע שיתווספו לתיקייה crates/.", "crate")
    body = f"""<section class="page-hero">
  <div class="container">
    <p class="eyebrow">{icon('crate')}שירים אמיתיים לסטים שלכם</p>
    <h1 class="display">ארגזים</h1>
    <p class="lead">רשימות שירים נבחרות לכל ז'אנר - עם BPM, Key ו-Camelot, תפקיד בסט והערות בעברית. אין כאן קבצים: רק מה לחפש ואיפה לקנות או להזרים באופן חוקי.</p>
  </div>
</section>
<section class="container">{listing}</section>"""
    return shell(out, title="ארגזים", body=body, active="crates", data=("crates",), scripts=("crates",),
                 description="ארגזי שירים אמיתיים לפי ז'אנר עם BPM, Key ו-Camelot - לקנייה והזרמה חוקית.")


# --------------------------------------------------------------------------------------------- sets
def build_sets(ctx_base, track_ids):
    sdir = ROOT / "sets"
    files = sorted(p for p in sdir.glob("*.md") if p.stem.lower() not in ("readme", "index")) if sdir.exists() else []
    sets = []
    for f in files:
        fm, body = parse_front_matter(read_text(f))
        h1 = re.match(r"^\s*#\s+(.+?)\s*\n", body)
        title_he = str(fm.get("title_he") or fm.get("title") or (h1.group(1) if h1 else f.stem))
        if h1:
            body = body[h1.end():]
        slug = str(fm.get("slug") or f.stem)
        out = DOCS / "sets" / f"{f.stem}.html"
        ctx = Ctx(f, out, *ctx_base)
        body_html, toc = md_to_html(body)
        body_html = postprocess(body_html, ctx)
        tracks = [t for t in as_list(fm.get("tracks")) if t in track_ids]
        if not tracks:
            seen = []
            for t in re.findall(r"\b((?:house|techno|mainstream|breadth)-\d\d)\b", body):
                if t in track_ids and t not in seen:
                    seen.append(t)
            tracks = seen
        intro = str(fm.get("summary") or fm.get("description") or "")
        if not intro:
            m = re.search(r"^(?!\s*[#|>\-*!\[])(\S.+)$", body, re.M)
            intro = clip(strip_tags(md_to_html(m.group(1))[0]), 300) if m else ""
        s = {
            "slug": slug, "file": f.stem, "title_he": title_he, "title": str(fm.get("title_en") or fm.get("title") or ""),
            "duration": fm.get("duration") or fm.get("duration_min") or fm.get("minutes"),
            "genres": [GENRE_NAMES.get(g, g.replace("_", " ").title() if re.fullmatch(r"[a-z0-9_]+", g) else g) for g in as_list(fm.get("genres"))],
            "level": str(fm.get("level") or ""),
            "bpm": str(fm.get("bpm") or fm.get("bpm_range") or ""), "tracks": tracks, "intro": intro,
            "href": f"sets/{f.stem}.html", "source": str(fm.get("source") or ("ours" if tracks else "")),
        }
        sets.append(s)
        write(out, render_set(s, body_html, toc, out))
    write(DOCS / "sets" / "index.html", render_sets_index(sets))
    return sets


def render_set(s, body_html, toc, out) -> str:
    chips = "".join(f'<span class="chip chip--static">{esc(g)}</span>' for g in s["genres"])
    meta = []
    if s["duration"]:
        meta.append(f'<span class="meta-item">{icon("clock")}{esc(s["duration"])} דק\'</span>')
    if s["bpm"]:
        meta.append(f'<span class="meta-item">{icon("metronome")}<span dir="ltr">{esc(s["bpm"])}</span> BPM</span>')
    if s["tracks"]:
        meta.append(f'<span class="meta-item">{icon("disc")}{len(s["tracks"])} טראקים מהספרייה</span>')
    meta.append(level_badge(s["level"]))
    builder = ""
    if s["tracks"]:
        q = ",".join(s["tracks"])
        builder = f"""<div class="set-tools card" data-set-tracks="{esc(q)}">
  <div class="set-tools-head"><h2>עקומת האנרגיה של הסט</h2>
  <div class="btn-row"><button class="btn btn--primary btn--sm" type="button" data-play-set>{icon('play')}<span>האזנה רצופה</span></button>
  <a class="btn btn--ghost btn--sm" href="../tools/set-builder.html?load={esc(q)}">{icon('setlist')}<span>פתיחה בבונה הסטים</span></a></div></div>
  <div class="energy-chart" data-energy-chart></div>
</div>"""
    en = f'<p class="chapter-en" dir="ltr">{esc(s["title"])}</p>' if s["title"] and s["title"] != s["title_he"] else ""
    body = f"""<section class="page-hero">
  <div class="container">
    <nav class="crumbs" aria-label="פירורי לחם"><a href="../index.html">בית</a><span aria-hidden="true">/</span><a href="index.html">סטים</a><span aria-hidden="true">/</span><span aria-current="page">{esc(s['title_he'])}</span></nav>
    <p class="eyebrow">{icon('setlist')}סט לדוגמה</p>
    <h1 class="display">{esc(s['title_he'])}</h1>{en}
    <div class="chip-row">{chips}</div>
    <div class="chapter-meta">{''.join(meta)}</div>
  </div>
</section>
<section class="container set-page">
  {builder}
  <div class="prose prose--wide">{body_html}</div>
</section>"""
    return shell(out, title=s["title_he"], body=body, active="sets", scripts=("sets",), data=("catalog", "peaks", "sets"),
                 description=s["intro"] or s["title_he"])


def render_sets_index(sets) -> str:
    out = DOCS / "sets" / "index.html"
    if sets:
        cards = []
        for s in sets:
            chips = "".join(f'<span class="chip chip--static chip--sm">{esc(g)}</span>' for g in s["genres"][:4])
            meta = []
            if s["duration"]:
                meta.append(f'<span>{icon("clock")}{esc(s["duration"])} דק\'</span>')
            if s["tracks"]:
                meta.append(f'<span>{icon("disc")}{len(s["tracks"])} טראקים</span>')
            if s["bpm"]:
                meta.append(f'<span dir="ltr">{esc(s["bpm"])} BPM</span>')
            cards.append(f"""<li><a class="set-card card card--link" href="{esc(s['file'])}.html">
  <span class="set-spark" aria-hidden="true" data-set-spark="{esc(','.join(s['tracks']))}"></span>
  <span class="set-title">{esc(s['title_he'])}</span>
  <span class="set-intro">{esc(s['intro'])}</span>
  <span class="chip-row">{chips}</span>
  <span class="crate-stats">{''.join(meta)}</span>
</a></li>""")
        listing = f'<ul class="set-grid">{"".join(cards)}</ul>'
    else:
        listing = empty_state("הסטים בדרך", "סטים לדוגמה עם הערות מעבר יופיעו כאן ברגע שיתווספו לתיקייה sets/.", "setlist")
    body = f"""<section class="page-hero">
  <div class="container">
    <p class="eyebrow">{icon('setlist')}ללמוד מסטים אמיתיים</p>
    <h1 class="display">סטים לדוגמה</h1>
    <p class="lead">סטים מתוכננים מקצה לקצה: סדר הטראקים, עקומת האנרגיה ומה בדיוק קורה בכל מעבר - איזה EQ, כמה תיבות ולמה.</p>
    <p><a class="btn btn--ghost btn--sm" href="../tools/set-builder.html">{icon('wand')}<span>לבנות סט משלכם</span></a></p>
  </div>
</section>
<section class="container">{listing}</section>"""
    return shell(out, title="סטים", body=body, active="sets", scripts=("sets",), data=("catalog", "sets"),
                 description="סטים לדוגמה עם סדר טראקים, עקומת אנרגיה והערות מעבר בעברית.")


# --------------------------------------------------------------------------------------------- static pages
def render_home(catalog, plan, extras, toc_data, crates, sets) -> str:
    out = DOCS / "index.html"
    rendered = len([t for t in catalog["tracks"] if t.get("has_audio")])
    planned = len(plan)
    genres = sorted({t.get("genre") for t in plan if t.get("genre")} | {t.get("genre") for t in catalog["tracks"] if t.get("genre")})
    n_practice = len(extras.get("practice", [])) + len(extras.get("transitions", []))
    track_stat = f"{rendered}" if rendered >= planned or not planned else f"{rendered}<small>/{planned}</small>"
    stats = [
        (track_stat, "טראקים מקוריים", "CC0 · מוכנים ל-Rekordbox", "library.html"),
        (str(len(genres)), "ז'אנרים", "מדיפ האוס ועד DnB", "library.html"),
        (str(len(toc_data)) if toc_data else "22", "פרקי קורס", "בעברית, צעד אחר צעד", "guide/index.html"),
        (str(len(crates)) if crates else "—", "ארגזים", "שירים אמיתיים עם BPM ו-Key", "crates/index.html"),
    ]
    stat_html = "".join(
        f'<li><a class="stat" href="{h}"><span class="stat-num">{n}</span><span class="stat-label">{l}</span><span class="stat-sub">{s}</span></a></li>'
        for n, l, s, h in stats)
    # learning path: chapters 00-06
    path_items = [t for t in toc_data if t["chapter"] <= 6][:7]
    if path_items:
        path_html = "".join(f"""<li class="path-step" data-chapter="{esc(t['file'])}"><a href="{esc(t['href'])}">
  <span class="path-num">{t['num']}</span>
  <span class="path-title">{esc(t['title'])}</span>
  <span class="path-sum">{esc(t['summary'])}</span>
  <span class="path-meta">{icon('clock')}{t['reading_minutes']} דק'<span class="path-check">{icon('check')}</span></span>
</a></li>""" for t in path_items)
        rest = len(toc_data) - len(path_items)
        if rest > 0:
            path_html += f"""<li class="path-step path-more"><a href="guide/index.html">
  <span class="path-num">+{rest}</span>
  <span class="path-title">עוד {rest} פרקים</span>
  <span class="path-sum">ספרייה, מיקס הרמוני, אפקטים, בניית סט, אירועים וחתונות ועוד.</span>
  <span class="path-meta">לכל הקורס {icon('arrow-left')}</span>
</a></li>"""
    else:
        demo = [("00", "ברוכים הבאים", "מה זה תקלוט, מה נלמד ואיך משתמשים ברפו"), ("01", "הציוד", "קונטרולר, אוזניות ומה באמת צריך"),
                ("02", "הכירו את Rekordbox", "ספרייה, דקים ומיקסר"), ("03", "ספירת ביטים ופרייזים", "4/4, תיבות ופרייזים של 8"),
                ("04", "ביטמאצ'ינג", "Tempo fader, Jog ואוזניים"), ("05", "EQ ופילטרים", "Low / Mid / High ו-Bass Swap"),
                ("06", "המעבר הראשון", "בלנד ארוך מהתחלה ועד הסוף")]
        path_html = "".join(f"""<li class="path-step is-soon"><span class="path-link">
  <span class="path-num">{n}</span><span class="path-title">{t}</span><span class="path-sum">{s}</span>
  <span class="path-meta">בקרוב</span></span></li>""" for n, t, s in demo)
    tools_html = "".join(f"""<li><a class="tool-card card card--link" href="tools/{slug}.html">
  <span class="tool-icon">{icon(ic)}</span>
  <span class="tool-name">{he}</span><span class="tool-en" dir="ltr">{en}</span>
  <span class="tool-desc">{desc}</span>
  <span class="tool-go">{icon('arrow-left')}</span>
</a></li>""" for slug, he, en, ic, desc in TOOLS)
    fam_counts = {}
    for t in plan:
        fam_counts.setdefault(t.get("family"), {}).setdefault(t.get("genre"), 0)
        fam_counts[t.get("family")][t.get("genre")] += 1
    fam_html = ""
    for fam, gs in fam_counts.items():
        chips = "".join(
            f'<a class="chip" href="library.html?genre={esc(g)}">{esc(g)} <small>{n}</small></a>' for g, n in gs.items())
        fam_html += f'<div class="fam-row" data-family="{esc(fam)}"><h3>{esc(FAMILY_HE.get(fam, fam))}</h3><div class="chip-row">{chips}</div></div>'
    bars = "".join(f'<i style="--i:{i}"></i>' for i in range(28))
    body = f"""<section class="hero">
  <div class="hero-bg" aria-hidden="true"><div class="hero-glow g1"></div><div class="hero-glow g2"></div><div class="hero-grid"></div></div>
  <div class="container hero-inner">
    <div class="hero-copy">
      <p class="eyebrow eyebrow--pill"><span class="live-dot" aria-hidden="true"></span>קורס Rekordbox · מוזיקה ב-CC0 · כלים בדפדפן</p>
      <h1 class="hero-title"><span class="hero-brand" dir="ltr">DJ Lab</span><span class="hero-sub">מבית הספר לתקלוט שלך</span></h1>
      <p class="hero-lead">לומדים לתקלט ב-Rekordbox מאפס: קורס מלא בעברית, {planned or 52} טראקים מקוריים שנבנו בדיוק לתרגול - אינטרו נקי, פרייזים של 8 תיבות ו-Hot Cues מוכנים - ומאמן מיקס שרץ ישר בדפדפן.</p>
      <div class="btn-row hero-cta">
        <a class="btn btn--primary btn--lg" href="guide/index.html">{icon('book')}<span>מתחילים ללמוד</span></a>
        <a class="btn btn--glass btn--lg" href="tools/mix-trainer.html">{icon('mixer')}<span>למאמן המיקס</span></a>
        <a class="btn btn--text" href="library.html"><span>לספריית המוזיקה</span>{icon('arrow-left')}</a>
      </div>
    </div>
    <div class="hero-visual" aria-hidden="true">
      <div class="deck-art">
        <div class="platter"><div class="platter-grooves"></div><div class="platter-label"><span>DJ</span><b>LAB</b></div><div class="platter-mark"></div></div>
        <div class="eq-bars">{bars}</div>
        <div class="hero-wave"><canvas data-hero-wave></canvas><span class="hero-playhead"></span></div>
        <div class="hero-readout"><span><b data-hero-bpm>126.00</b> BPM</span><span class="cam-badge" style="--cam:var(--cam-8a)">8A</span><span dir="ltr" data-hero-time>01:04</span></div>
      </div>
    </div>
  </div>
</section>
<section class="container stats-band" aria-label="במספרים"><ul class="stats">{stat_html}</ul></section>

<section class="container section">
  <div class="section-head">
    <div><p class="eyebrow">{icon('spark')}מתחילים כאן</p><h2 class="section-title">מסלול הלמידה</h2>
    <p class="section-lead">שבעה פרקים שלוקחים אתכם מ"מה זה BPM?" ועד המעבר הראשון שלכם. כל פרק קצר, מעשי ומלווה בקטעי שמע.</p></div>
    <a class="btn btn--ghost" href="guide/index.html"><span>לכל הפרקים</span>{icon('arrow-left')}</a>
  </div>
  <ol class="path">{path_html}</ol>
</section>

<section class="container section">
  <div class="section-head">
    <div><p class="eyebrow">{icon('headphones')}האזינו עכשיו</p><h2 class="section-title">טראקים נבחרים</h2>
    <p class="section-lead">כל טראק הוא מקורי, חופשי לשימוש (CC0) ובנוי לפי חוקי התקלוט: מתחיל בדיוק על הביט, אינטרו של תופים בלבד ו-Hot Cues צבועים כמו ב-Rekordbox.</p></div>
    <a class="btn btn--ghost" href="library.html"><span>לכל הספרייה</span>{icon('arrow-left')}</a>
  </div>
  <div class="track-grid track-grid--featured" data-featured></div>
</section>

<section class="container section">
  <div class="section-head">
    <div><p class="eyebrow">{icon('sliders')}משחקים עם הסאונד</p><h2 class="section-title">כלים לתקליטנים</h2>
    <p class="section-lead">כל מה שצריך לתרגל בין השיעורים - בלי להתקין כלום.</p></div>
  </div>
  <ul class="tool-grid">{tools_html}</ul>
</section>

<section class="container section">
  <div class="section-head">
    <div><p class="eyebrow">{icon('disc')}{len(genres)} ז'אנרים · 4 משפחות</p><h2 class="section-title">מה יש בספרייה</h2>
    <p class="section-lead">האוס, טק האוס ואפרו; טכנו ומלודיק; מיינסטרים, היפ-הופ וים-תיכוני - ועוד ז'אנרים כדי להרחיב את האוזן.</p></div>
  </div>
  <div class="fam-grid card">{fam_html}</div>
</section>

<section class="container section">
  <div class="cta-band card">
    <div><h2>מוכנים להכניס הכל ל-Rekordbox?</h2>
    <p>מורידים את תיקיית המוזיקה, מקלידים איפה שמרתם אותה - ומקבלים קובץ XML עם כל הטראקים, ה-Hot Cues והפלייליסטים.</p></div>
    <a class="btn btn--primary btn--lg" href="tools/rekordbox.html">{icon('code')}<span>למחולל ה-XML</span></a>
  </div>
</section>"""
    return shell(out, title="DJ Lab", full_title="DJ Lab — מבית הספר לתקלוט שלך", body=body, active="home",
                 scripts=("home",), data=("catalog", "peaks", "guide"), body_class="is-home")


FILTER_SHELL = ""


def render_library() -> str:
    out = DOCS / "library.html"
    body = f"""<section class="page-hero page-hero--compact">
  <div class="container">
    <p class="eyebrow">{icon('disc')}מוזיקה מקורית · CC0 · מוכנה לתקלוט</p>
    <h1 class="display">ספריית המוזיקה</h1>
    <p class="lead">כל הטראקים של DJ Lab עם BPM, Key ו-Camelot, אנרגיה ותפקיד בסט. לחצו על טראק כדי לראות Hot Cues, מבנה ומה מתאים לו למיקס.</p>
  </div>
</section>
<section class="container library" data-library>
  <div class="lib-toolbar">
    <label class="search-field">{icon('search')}<span class="sr-only">חיפוש</span><input type="search" placeholder="חיפוש לפי שם, ז'אנר, סולם…" data-lib-search autocomplete="off"></label>
    <div class="toolbar-group">
      <label class="select-field"><span class="sr-only">מיון</span><select data-lib-sort>
        <option value="default">מיון: לפי משפחה</option><option value="bpm">BPM (נמוך לגבוה)</option><option value="bpm-desc">BPM (גבוה לנמוך)</option>
        <option value="energy">אנרגיה (נמוך לגבוה)</option><option value="energy-desc">אנרגיה (גבוה לנמוך)</option><option value="camelot">Camelot</option>
        <option value="title">שם (A-Z)</option><option value="duration">אורך</option></select></label>
      <div class="seg" role="group" aria-label="תצוגה"><button type="button" data-view="grid" aria-pressed="true" aria-label="תצוגת רשת">{icon('grid')}</button><button type="button" data-view="list" aria-pressed="false" aria-label="תצוגת רשימה">{icon('list')}</button></div>
      <button class="btn btn--ghost btn--sm filters-toggle" type="button" data-filters-toggle aria-expanded="false" aria-controls="lib-filters">{icon('filter')}<span>סינון</span><span class="count-dot" data-filter-count hidden></span></button>
    </div>
  </div>
  <div class="lib-layout">
    <aside class="lib-filters" id="lib-filters" aria-label="סינון טראקים" data-lib-filters></aside>
    <div class="lib-results">
      <div class="lib-status"><p data-lib-count aria-live="polite"></p><div class="btn-row" data-lib-actions></div></div>
      <div class="track-grid" data-lib-grid></div>
    </div>
  </div>
</section>"""
    return shell(out, title="ספריית מוזיקה", body=body, active="library", scripts=("library",), data=("catalog", "peaks", "crates"),
                 description="ספריית המוזיקה של DJ Lab: טראקים מקוריים ב-CC0 עם BPM, Key, Camelot, Hot Cues ונגן עם Waveform.")


def render_practice() -> str:
    out = DOCS / "practice.html"
    body = f"""<section class="page-hero page-hero--compact">
  <div class="container">
    <p class="eyebrow">{icon('practice')}תרגול יומי</p>
    <h1 class="display">אימון</h1>
    <p class="lead">קבצי תרגול שנבנו במיוחד ללימוד: לופים לביטמאצ'ינג באוזן, ספירת פרייזים, החלפת באס ואימון אוזן ל-EQ - ומעברים לדוגמה שמראים כל טכניקה מההתחלה ועד הסוף.</p>
    <div class="btn-row"><a class="btn btn--ghost btn--sm" href="#drills">תרגילים</a><a class="btn btn--ghost btn--sm" href="#transitions">מעברים לדוגמה</a><a class="btn btn--ghost btn--sm" href="tools/mix-trainer.html">{icon('mixer')}<span>מאמן המיקס</span></a></div>
  </div>
</section>
<section class="container section" id="drills" aria-labelledby="drills-h">
  <div class="section-head"><div><h2 class="section-title" id="drills-h">תרגילים</h2><p class="section-lead">כל תרגיל מגיע עם הוראות. מומלץ לטעון אותם ב-Rekordbox, או לתרגל ישר כאן במאמן המיקס.</p></div></div>
  <div class="practice-grid" data-practice-list></div>
</section>
<section class="container section" id="transitions" aria-labelledby="tr-h">
  <div class="section-head"><div><h2 class="section-title" id="tr-h">מעברים לדוגמה</h2><p class="section-lead">הקלטות של מעבר בין שני טראקים מהספרייה, כל אחת בטכניקה אחרת - עם השלבים המדויקים כדי שתוכלו לשחזר.</p></div></div>
  <div class="practice-grid" data-transition-list></div>
</section>"""
    return shell(out, title="אימון", body=body, active="practice", scripts=("practice",), data=("catalog", "peaks"),
                 description="קבצי תרגול לביטמאצ'ינג, פרייזים, EQ ומעברים לדוגמה - עם הוראות בעברית.")


def render_about(catalog) -> str:
    out = DOCS / "about.html"
    team = [
        ("מנהל הפרויקט (Orchestrator)", "מתכנן, מחלק עבודה ושומר על חוזה הנתונים."),
        ("מפיקי האוס, טכנו ומיינסטרים", "כותבים מתכונים במנוע הסינתזה ומרנדרים את הטראקים."),
        ("מהנדס האודיו", "בונה את מנוע djlab: סינתזה, מיקס, מאסטרינג ו-QA לכל קובץ."),
        ("כותבי הקורס", "כותבים את הפרקים בעברית, עם תרגילים ודוגמאות."),
        ("חוקרי המוזיקה", "בונים את הארגזים: שירים אמיתיים עם BPM ו-Key מאומתים."),
        ("מעצב האתר", "האתר הזה: עיצוב, נגנים, מאמן המיקס והכלים."),
    ]
    team_html = "".join(f'<li class="card"><h3>{esc(n)}</h3><p>{esc(d)}</p></li>' for n, d in team)
    body = f"""<section class="page-hero">
  <div class="container">
    <p class="eyebrow">{icon('info')}על הפרויקט</p>
    <h1 class="display">אודות ורישיון</h1>
    <p class="lead">DJ Lab הוא מעבדה ללימוד תקלוט: קורס, מוזיקה מקורית לתרגול וכלים - הכל פתוח וחופשי.</p>
  </div>
</section>
<section class="container prose prose--wide about">
  <h2 id="music-license">המוזיקה: CC0 - נחלת הכלל</h2>
  <p>כל קובצי האודיו בתיקיות <code>music/tracks</code>, <code>music/practice</code> ו-<code>music/transitions</code> הם יצירות מקוריות שהופקו באופן אלגוריתמי ע"י מנוע <code>engine/djlab</code> שבריפו - בלי סמפלים, בלי סטמים ובלי קטעים מיצירות קיימות. הם משוחררים תחת <a href="https://creativecommons.org/publicdomain/zero/1.0/deed.he" target="_blank" rel="noopener">CC0 1.0 Universal</a>.</p>
  <aside class="callout callout--tip" role="note"><div class="callout-head">{icon('bulb')}<span>מה מותר?</span></div><div class="callout-body"><p>הכל: לנגן בהופעות, להקליט ולהעלות מיקסים ל-SoundCloud / Mixcloud / YouTube, לערוך, לעשות רמיקסים ולהשתמש לכל מטרה - בלי לבקש רשות ובלי חובת קרדיט. קרדיט ל-"DJ Lab Originals" תמיד יתקבל בברכה.</p></div></aside>
  <h2 id="crates">הארגזים: קישורים בלבד</h2>
  <p>הרשימות בעמוד <a href="crates/index.html">ארגזים</a> מתארות שירים מסחריים של אמנים אמיתיים. הם <b>לא</b> כלולים באתר או בריפו - יש לקנות או להזרים אותם ממקורות חוקיים: Beatport, Bandcamp, Traxsource, iTunes, או שירותי הזרמה מתוך Rekordbox (Beatport Streaming, SoundCloud, TIDAL).</p>
  <h2 id="code">הקוד: MIT</h2>
  <p>הקוד של האתר, מנוע הסינתזה והכלים זמין ב-<a href="{REPO_URL}" target="_blank" rel="noopener">GitHub</a> תחת רישיון MIT.</p>
  <h2 id="team">הצוות</h2>
  <p>DJ Lab נבנה ע"י צוות סוכני AI שעבדו במקביל, כל אחד בתחום שלו:</p>
  <ul class="team-grid">{team_html}</ul>
  <h2 id="local">איך מריצים את האתר אצלכם</h2>
<pre dir="ltr"><code>git clone {REPO_URL}.git
cd try
python tools/build_site.py
python -m http.server 8000
# open http://localhost:8000/docs/</code></pre>
  <p>חשוב להריץ את השרת מתיקיית השורש של הריפו (ולא מתוך <code>docs</code>), כדי שהאתר יוכל לגשת לקבצים בתיקייה <code>music/</code>.</p>
</section>"""
    return shell(out, title="אודות ורישיון", body=body, active="about",
                 description="על DJ Lab: רישיון CC0 למוזיקה, ארגזים כקישורים בלבד, והצוות שבנה את הפרויקט.")


def tool_hero(slug, he, en, ic, lead) -> str:
    return f"""<section class="page-hero page-hero--compact page-hero--tool">
  <div class="container">
    <nav class="crumbs" aria-label="פירורי לחם"><a href="../index.html">בית</a><span aria-hidden="true">/</span><a href="index.html">כלים</a><span aria-hidden="true">/</span><span aria-current="page">{esc(he)}</span></nav>
    <p class="eyebrow">{icon(ic)}<span dir="ltr">{esc(en)}</span></p>
    <h1 class="display">{esc(he)}</h1>
    <p class="lead">{lead}</p>
  </div>
</section>"""


def render_tools_index() -> str:
    out = DOCS / "tools" / "index.html"
    cards = "".join(f"""<li><a class="tool-card tool-card--lg card card--link" href="{slug}.html">
  <span class="tool-icon">{icon(ic)}</span>
  <span class="tool-name">{he}</span><span class="tool-en" dir="ltr">{en}</span>
  <span class="tool-desc">{desc}</span>
  <span class="tool-go">{icon('arrow-left')}</span>
</a></li>""" for slug, he, en, ic, desc in TOOLS)
    body = f"""<section class="page-hero">
  <div class="container">
    <p class="eyebrow">{icon('sliders')}עובד ישר בדפדפן</p>
    <h1 class="display">כלים</h1>
    <p class="lead">מאמן מיקס עם שני דקים, גלגל קאמלוט אינטראקטיבי, מודד BPM, בונה סטים ומחולל XML ל-Rekordbox. בלי התקנות, בלי הרשמה.</p>
  </div>
</section>
<section class="container"><ul class="tool-grid tool-grid--page">{cards}</ul></section>"""
    return shell(out, title="כלים", body=body, active="tools", description="כלים לתקליטנים: מאמן מיקס, גלגל קאמלוט, BPM, בונה סטים ו-Rekordbox XML.")


def render_tool_camelot() -> str:
    out = DOCS / "tools" / "camelot.html"
    body = tool_hero("camelot", "גלגל קאמלוט", "Camelot Wheel", "wheel",
                     "כל סולם מוזיקלי מקבל מספר ואות. לחצו על סולם בגלגל: נראה לכם אילו סולמות מתאימים למיקס הרמוני - ואילו טראקים מהספרייה ומהארגזים יושבים בדיוק שם.")
    body += f"""<section class="container camelot-tool" data-camelot-tool>
  <div class="camelot-layout">
    <div class="wheel-card card">
      <div class="wheel-wrap" data-wheel></div>
      <div class="wheel-legend" data-wheel-legend></div>
    </div>
    <div class="camelot-side">
      <div class="card key-info" data-key-info aria-live="polite"></div>
      <div class="card" data-key-tracks></div>
      <div class="card" data-key-crates></div>
    </div>
  </div>
  <div class="card camelot-explain prose prose--wide">
    <h2>איך קוראים את הגלגל?</h2>
    <ul>
      <li><b>הטבעת הפנימית (A)</b> - סולמות מינוריים. <b>הטבעת החיצונית (B)</b> - סולמות מז'וריים.</li>
      <li><b>אותו מספר ואות</b> - אותו סולם בדיוק. המעבר הכי בטוח.</li>
      <li><b>±1 באותה טבעת</b> (למשל 8A → 9A או 7A) - שכנים. כמעט תמיד נשמע טוב.</li>
      <li><b>החלפת אות באותו מספר</b> (8A ↔ 8B) - סולם יחסי: מעבר ממינור למז'ור, משנה מצב רוח בלי לזייף.</li>
      <li><b>+2</b> (8A → 10A) - Energy Boost: הקפצה של טון שלם, מרגישה כמו "הרמה" בסט.</li>
      <li><b>+7</b> (8A → 3A) - חצי טון למעלה. מעבר דרמטי - קצר, על דרופ או אחרי ברייקדאון.</li>
    </ul>
    <aside class="callout callout--rekordbox" role="note"><div class="callout-head">{icon('sliders')}<span>ב-Rekordbox</span></div><div class="callout-body"><p>כדי לראות Camelot במקום שמות סולמות: <b>Preferences → View → Key display format → Alphanumeric</b>. אחרי ניתוח הטראקים (Analyze Track) עמודת ה-Key תציג 8A, 9B וכו'.</p></div></aside>
  </div>
</section>"""
    return shell(out, title="גלגל קאמלוט", body=body, active="tools", scripts=("camelot",), data=("catalog", "peaks", "crates"),
                 description="גלגל קאמלוט אינטראקטיבי: סולמות תואמים למיקס הרמוני וטראקים בכל סולם.")


def render_tool_bpm() -> str:
    out = DOCS / "tools" / "bpm.html"
    body = tool_hero("bpm", "BPM ומחשבון טמפו", "BPM Tapper · Pitch Calculator", "metronome",
                     "הקישו בקצב השיר כדי למדוד BPM, וחשבו בכמה אחוז צריך להזיז את ה-Tempo fader כדי לעבור מטמפו אחד לאחר.")
    body += f"""<section class="container bpm-tool">
  <div class="bpm-grid">
    <div class="card tapper" data-tapper>
      <h2 class="card-title">{icon('metronome')}מודד BPM</h2>
      <button class="tap-pad" type="button" data-tap aria-describedby="tap-help">
        <span class="tap-bpm" data-tap-bpm>--</span><span class="tap-unit">BPM</span>
        <span class="tap-hint" data-tap-hint>הקישו כאן או על מקש הרווח</span>
        <span class="tap-ring" aria-hidden="true"></span>
      </button>
      <p id="tap-help" class="muted small">הקישו לפחות 8 פעמים על הקיק (התוף הנמוך). המדידה מתאפסת אחרי 2.5 שניות בלי הקשה.</p>
      <div class="tap-stats"><div><span class="k">הקשות</span><span class="v" data-tap-count>0</span></div><div><span class="k">יציבות</span><span class="v" data-tap-stab>--</span></div><div><span class="k">×½ / ×2</span><span class="v" data-tap-alt>--</span></div></div>
      <div class="btn-row"><button class="btn btn--ghost btn--sm" type="button" data-tap-reset>איפוס</button><button class="btn btn--ghost btn--sm" type="button" data-tap-use>להעביר למחשבון</button></div>
      <div class="tap-metro"><label class="switch"><input type="checkbox" data-metro-toggle><span></span>מטרונום</label><span class="muted small" data-metro-label>ינגן קליק ב-BPM שנמדד (או 124)</span></div>
    </div>
    <div class="card pitch-calc" data-pitch-calc>
      <h2 class="card-title">{icon('sliders')}מחשבון Pitch</h2>
      <div class="calc-inputs">
        <label class="field"><span>BPM של הטראק</span><input type="number" inputmode="decimal" step="0.01" min="40" max="250" value="124" data-calc-from></label>
        <span class="calc-arrow" aria-hidden="true">{icon('arrow-left')}</span>
        <label class="field"><span>BPM יעד</span><input type="number" inputmode="decimal" step="0.01" min="40" max="250" value="128" data-calc-to></label>
      </div>
      <div class="calc-result" data-calc-result aria-live="polite"></div>
      <div class="range-fit" data-calc-ranges></div>
      <div class="calc-notes" data-calc-notes></div>
    </div>
  </div>
  <div class="card bpm-ref">
    <h2 class="card-title">{icon('disc')}טווחי BPM לפי ז'אנר (מהספרייה שלנו)</h2>
    <div class="bpm-ruler" data-bpm-ruler></div>
  </div>
</section>"""
    return shell(out, title="BPM ומחשבון טמפו", body=body, active="tools", scripts=("bpm",), data=("catalog",),
                 description="מודד BPM בהקשה ומחשבון Pitch: כמה אחוז צריך כדי לעבור בין טמפואים, וטווחי ±6/±8/±16.")


def render_tool_mixer() -> str:
    out = DOCS / "tools" / "mix-trainer.html"
    body = tool_hero("mix-trainer", "מאמן מיקס", "Mix Trainer", "mixer",
                     "שני דקים ומיקסר בדפדפן. טענו טראק לכל דק, התאימו טמפו עם ה-Tempo fader, יישרו ביטים עם ה-Jog - ומד הפאזה יראה לכם בזמן אמת כמה אתם רחוקים.")
    body += f"""<section class="container-wide mixer-app" data-mixer>
  <div class="mixer-topbar card">
    <div class="mt-toggles">
      <label class="switch"><input type="checkbox" checked data-opt-bpm><span></span>הצגת BPM</label>
      <label class="switch"><input type="checkbox" checked data-opt-phase><span></span>מד פאזה</label>
      <label class="switch"><input type="checkbox" data-opt-quantize><span></span>Quantize ל-Cue</label>
    </div>
    <div class="mt-zoom" data-zoom-slot></div>
    <div class="mt-presets"><label class="select-field select-field--sm"><span class="sr-only">תרגיל מוכן</span><select data-preset><option value="">תרגיל מוכן…</option></select></label>
    <button class="btn btn--ghost btn--sm" type="button" data-help-toggle aria-expanded="false" aria-controls="mixer-help">{icon('keyboard')}<span>מקלדת ועזרה</span></button></div>
  </div>
  <div class="mixer-help card" id="mixer-help" hidden data-help></div>
  <div class="console" dir="ltr" data-console>
    <div class="deck deck--a" data-deck="A"></div>
    <div class="mixer-center" data-mixer-center></div>
    <div class="deck deck--b" data-deck="B"></div>
  </div>
  <div class="card mixer-notes prose prose--wide">
    <h2>למה ה-Pitch משתנה כשמזיזים את הטמפו?</h2>
    <p>במאמן הזה אין <b>Master Tempo</b> (Key Lock): כמו בפטיפון, כשמאיצים את הטראק גם הצליל עולה. ב-Rekordbox תדליקו Master Tempo כדי לשנות טמפו בלי לשנות סולם - אבל לתרגול ביטמאצ'ינג באוזן זה בדיוק מה שאנחנו רוצים לשמוע.</p>
    <h2>איך מתרגלים?</h2>
    <ol>
      <li>טענו טראק ל-A, הפעילו אותו ושמעו את הקיק.</li>
      <li>טענו טראק ל-B, הפעילו בדיוק על "1" של תיבה (ה-Cue נמצא בהתחלה - הטראקים שלנו מתחילים על הביט).</li>
      <li>הזיזו את ה-Tempo fader של B עד שה-BPM תואם. כבו את "הצגת BPM" כדי לעשות את זה רק באוזן.</li>
      <li>אם הקיקים "דוהרים" אחד אחרי השני - דחפו קדימה או אחורה עם כפתורי ה-Nudge או ה-Jog עד שהם נשמעים כמו קיק אחד.</li>
      <li>מד הפאזה במרכז מראה בכמה מילישניות B מקדים או מאחר. המטרה: מחוג באמצע ונשאר שם.</li>
    </ol>
  </div>
</section>"""
    return shell(out, title="מאמן מיקס", body=body, active="tools", scripts=("knob", "mixer"), data=("catalog", "peaks"),
                 body_class="is-mixer", description="מאמן מיקס בדפדפן: שני דקים, EQ, פילטר, Tempo fader, Jog ומד פאזה לתרגול ביטמאצ'ינג.")


def render_tool_setbuilder() -> str:
    out = DOCS / "tools" / "set-builder.html"
    body = tool_hero("set-builder", "בונה סטים", "Set Builder", "setlist",
                     "בחרו טראקים וסדרו אותם לסט. לכל מעבר תקבלו בדיקת התאמה של סולם ו-BPM, תראו את עקומת האנרגיה ותוכלו לייצא פלייליסט.")
    body += f"""<section class="container setb" data-setbuilder>
  <div class="setb-layout">
    <div class="card setb-picker">
      <div class="setb-picker-head"><h2 class="card-title">{icon('disc')}טראקים</h2>
      <label class="search-field search-field--sm">{icon('search')}<span class="sr-only">חיפוש</span><input type="search" placeholder="חיפוש…" data-sb-search></label></div>
      <div class="chip-row" data-sb-fams></div>
      <div class="sb-suggest" data-sb-suggest hidden></div>
      <ul class="sb-list" data-sb-list></ul>
    </div>
    <div class="setb-main">
      <div class="card setb-head">
        <label class="field field--title"><span class="sr-only">שם הסט</span><input type="text" value="הסט שלי" maxlength="60" data-sb-name></label>
        <div class="sb-summary" data-sb-summary></div>
        <div class="btn-row">
          <button class="btn btn--primary btn--sm" type="button" data-sb-play>{icon('play')}<span>האזנה</span></button>
          <button class="btn btn--ghost btn--sm" type="button" data-sb-m3u>{icon('download')}<span>M3U8</span></button>
          <button class="btn btn--ghost btn--sm" type="button" data-sb-txt>{icon('copy')}<span>טראקליסט</span></button>
          <a class="btn btn--ghost btn--sm" href="rekordbox.html">{icon('code')}<span>ל-Rekordbox XML</span></a>
          <button class="btn btn--ghost btn--sm btn--danger" type="button" data-sb-clear>{icon('trash')}<span>ניקוי</span></button>
        </div>
      </div>
      <div class="card"><h2 class="card-title">{icon('bolt')}עקומת אנרגיה</h2><div class="energy-chart" data-sb-chart></div></div>
      <ol class="sb-set" data-sb-set aria-label="הטראקים בסט"></ol>
    </div>
  </div>
</section>"""
    return shell(out, title="בונה סטים", body=body, active="tools", scripts=("setbuilder",), data=("catalog", "peaks", "sets"),
                 description="בונה סטים: התאמת Key ו-BPM לכל מעבר, עקומת אנרגיה וייצוא M3U8 וטראקליסט.")


def render_tool_rekordbox() -> str:
    out = DOCS / "tools" / "rekordbox.html"
    body = tool_hero("rekordbox", "מחולל Rekordbox XML", "rekordbox.xml generator", "code",
                     "מקלידים איפה שמרתם את תיקיית <code>music</code> של DJ Lab - ומקבלים קובץ <code>rekordbox.xml</code> עם כל הטראקים, BPM, Key, Hot Cues צבעוניים ופלייליסטים מסודרים.")
    body += f"""<section class="container rbx" data-rekordbox>
  <div class="rbx-layout">
    <form class="card rbx-form" data-rbx-form onsubmit="return false">
      <h2 class="card-title"><span class="step-num">1</span>איפה שמרתם את המוזיקה?</h2>
      <fieldset class="seg-field"><legend>מערכת הפעלה</legend>
        <div class="seg seg--lg" role="radiogroup" aria-label="מערכת הפעלה">
          <label><input type="radio" name="os" value="win" checked><span>Windows</span></label>
          <label><input type="radio" name="os" value="mac"><span>macOS</span></label>
        </div>
      </fieldset>
      <label class="field"><span>הנתיב המלא לתיקייה <code>music</code></span>
        <input type="text" dir="ltr" spellcheck="false" autocomplete="off" data-rbx-path placeholder="C:\\Users\\Name\\Music\\DJ-Lab\\music"></label>
      <p class="muted small" data-rbx-path-hint></p>
      <h2 class="card-title"><span class="step-num">2</span>מה להכניס?</h2>
      <div class="check-grid">
        <label class="check"><input type="checkbox" checked data-rbx-opt="hotcues"><span>Hot Cues (A-H בצבעים)</span></label>
        <label class="check"><input type="checkbox" checked data-rbx-opt="memory"><span>Memory Cues</span></label>
        <label class="check"><input type="checkbox" checked data-rbx-opt="practice"><span>קבצי תרגול</span></label>
        <label class="check"><input type="checkbox" checked data-rbx-opt="transitions"><span>מעברים לדוגמה</span></label>
        <label class="check"><input type="checkbox" checked data-rbx-opt="genres"><span>פלייליסט לכל ז'אנר</span></label>
        <label class="check"><input type="checkbox" checked data-rbx-opt="myset"><span>הסט שלי (מבונה הסטים)</span></label>
      </div>
      <div class="rbx-summary" data-rbx-summary aria-live="polite"></div>
      <div class="btn-row">
        <button class="btn btn--primary btn--lg" type="button" data-rbx-download>{icon('download')}<span>הורדת rekordbox.xml</span></button>
        <button class="btn btn--ghost" type="button" data-rbx-copy>{icon('copy')}<span>העתקה</span></button>
      </div>
    </form>
    <div class="rbx-side">
      <div class="card rbx-steps">
        <h2 class="card-title"><span class="step-num">3</span>הייבוא ל-Rekordbox</h2>
        <ol class="steps">
          <li><b>שמרו את הקובץ</b> <code>rekordbox.xml</code> במקום קבוע (למשל ליד תיקיית <code>music</code>).</li>
          <li>ב-Rekordbox: <b>Preferences</b> (גלגל השיניים) ← <b>Advanced</b> ← <b>Database</b>.</li>
          <li>תחת <b>rekordbox xml</b> ← <b>Imported Library</b> לחצו <b>Browse</b> ובחרו את הקובץ.</li>
          <li>ב-<b>View</b> ודאו ש-<b>rekordbox xml</b> מסומן כדי שיופיע בעץ הספרייה (צד שמאל).</li>
          <li>פתחו את <b>rekordbox xml</b> ← <b>Playlists</b> ← <b>DJ Lab</b>.</li>
          <li>קליק ימני על פלייליסט (או על התיקייה כולה) ← <b>Import Playlist</b>. הטראקים נכנסים ל-Collection עם BPM, Key וה-Hot Cues.</li>
          <li>מומלץ: בחרו את כל הטראקים ← קליק ימני ← <b>Analyze Track</b> כדי ש-Rekordbox יבנה Waveform.</li>
        </ol>
        <aside class="callout callout--warn" role="note"><div class="callout-head">{icon('alert')}<span>זהירות</span></div><div class="callout-body"><p>אם Rekordbox מציג טראקים באדום / "File not found" - הנתיב שהקלדתם לא תואם למיקום האמיתי. תקנו את הנתיב, צרו קובץ חדש וייבאו שוב. אל תשנו שמות קבצים בתוך <code>music</code>.</p></div></aside>
        <aside class="callout callout--tip" role="note"><div class="callout-head">{icon('bulb')}<span>טיפ</span></div><div class="callout-body"><p>ה-Beatgrid נטען מוכן: כל הטראקים שלנו מתחילים בדיוק על הביט הראשון, כך שה-Grid יושב מושלם בלי תיקונים. אם Rekordbox ניתח מחדש ושינה את ה-Grid - אפשר לייבא שוב מה-XML.</p></div></aside>
      </div>
      <details class="card rbx-preview"><summary>{icon('code')}<span>תצוגה מקדימה של ה-XML</span></summary><pre dir="ltr" data-rbx-preview></pre></details>
    </div>
  </div>
</section>"""
    return shell(out, title="מחולל Rekordbox XML", body=body, active="tools", scripts=("rekordbox",), data=("catalog",),
                 description="מחולל rekordbox.xml: כל טראקי DJ Lab עם BPM, Key, Hot Cues צבעוניים ופלייליסטים, מותאם לנתיב אצלכם.")


def render_404() -> str:
    """Self-contained 404 (works at any URL depth on GitHub Pages: no relative assets)."""
    return f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>לא נמצא · DJ Lab</title>
<meta name="robots" content="noindex">
<style>
:root{{color-scheme:dark}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#07070c radial-gradient(60vw 50vh at 80% 0%,rgba(255,43,214,.18),transparent 70%);color:#f4f3fa;font-family:Heebo,system-ui,-apple-system,"Segoe UI",Arial,sans-serif;padding:16px;text-align:center}}
.b{{font:800 clamp(64px,18vw,140px)/1 Rubik,system-ui,sans-serif;background:linear-gradient(100deg,#fff,#ff2bd6 50%,#22e1ff);-webkit-background-clip:text;background-clip:text;color:transparent;direction:ltr}}
h1{{font-size:clamp(24px,5vw,36px);margin:8px 0}}p{{color:#c9c8d8;max-width:46ch;margin:0 auto 24px;line-height:1.7}}
a{{display:inline-block;padding:12px 22px;border-radius:999px;background:linear-gradient(135deg,#ff2bd6,#8a5cff);color:#fff;text-decoration:none;font-weight:700}}
a:focus-visible{{outline:2px solid #22e1ff;outline-offset:3px}}
</style>
</head>
<body>
<main>
<div class="b" aria-hidden="true">404</div>
<h1>הטראק הזה לא בסט</h1>
<p>העמוד שחיפשתם לא קיים או שעבר מקום. נחזור לרחבה?</p>
<a id="home" href="./">לדף הבית של DJ Lab</a>
</main>
<script>(function(){{var p=location.pathname,i=p.indexOf('/docs/'),h;if(i>=0)h=p.slice(0,i)+'/docs/index.html';else{{var s=p.split('/').filter(Boolean);h=(location.hostname.indexOf('github.io')>=0&&s.length?'/'+s[0]:'')+'/docs/index.html';}}document.getElementById('home').href=h;}})();</script>
</body>
</html>
"""


# --------------------------------------------------------------------------------------------- main
def clean_stale():
    removed = 0
    for sub in ("guide", "crates", "sets"):
        d = DOCS / sub
        if not d.exists():
            continue
        for p in d.glob("*.html"):
            if p.resolve() not in WRITTEN:
                p.unlink()
                removed += 1
    gdir = DOCS / "assets" / "guide"
    if gdir.exists():
        for p in gdir.rglob("*"):
            if p.is_file() and p.resolve() not in WRITTEN:
                p.unlink()
                removed += 1
    return removed


def main(argv=None) -> int:
    global VERSION
    ap = argparse.ArgumentParser(description="Build the DJ Lab static site into docs/")
    ap.add_argument("--no-peaks", action="store_true", help="never analyse audio; reuse docs/data/peaks.js")
    ap.add_argument("--no-peaks-if-missing", action="store_true",
                    help="CI mode: analyse only when ffmpeg+audio exist, otherwise reuse committed peaks")
    args = ap.parse_args(argv)
    t0 = time.time()

    if markdown is None:
        warn("python 'markdown' package missing: pip install markdown")
    plan, extras = load_plans()
    for t in plan:
        if t.get("genre_slug") and t.get("genre"):
            GENRE_NAMES.setdefault(t["genre_slug"], t["genre"])
    GENRE_NAMES.update({"dnb": "Drum & Bass", "drum_and_bass": "Drum & Bass", "ukg": "UK Garage", "uk_garage": "UK Garage", "lofi": "Lo-Fi", "edm": "EDM", "rnb": "R&B"})
    catalog = build_catalog(plan, extras)
    peaks_mode = "never" if args.no_peaks else "auto"
    peaks = build_peaks(catalog, peaks_mode)

    track_ids = {t.get("id") for t in plan} | {t.get("id") for t in catalog["tracks"]} | \
                {t.get("id") for t in extras.get("practice", [])} | {t.get("id") for t in extras.get("transitions", [])}
    track_ids.discard(None)
    files = {it.get("file") for g in catalog.values() if isinstance(g, list) for it in g}
    ctx_base = (files, track_ids)

    # icons for JS
    write(DOCS / "assets" / "js" / "icons.gen.js",
          "/* generated by tools/build_site.py - do not edit */\n" + js_global("DJ_ICONS", ICONS))
    asset_files = sorted((DOCS / "assets").rglob("*.css")) + sorted((DOCS / "assets" / "js").glob("*.js"))
    VERSION = asset_version(*asset_files)

    cat_out = dict(catalog)
    cat_out["plan"] = plan_summary(plan, extras)
    write(DATA / "catalog.js", "/* generated by tools/build_site.py */\n" + js_global("DJLAB_CATALOG", cat_out))
    write(DATA / "peaks.js", "/* generated by tools/build_site.py - 3-band waveform peaks (low,mid,high bytes) */\n"
          + js_global("DJLAB_PEAKS", peaks))

    chapters, toc_data = build_guide(ctx_base)
    write(DATA / "guide.js", "/* generated by tools/build_site.py */\n" + js_global("DJLAB_GUIDE", toc_data))
    write(DOCS / "guide" / "index.html", render_guide_index(toc_data))

    crates = build_crates(ctx_base)
    write(DATA / "crates.js", "/* generated by tools/build_site.py */\n" + js_global("DJLAB_CRATES", crates))
    sets = build_sets(ctx_base, track_ids)
    write(DATA / "sets.js", "/* generated by tools/build_site.py */\n" + js_global("DJLAB_SETS", sets))

    write(DOCS / "index.html", render_home(catalog, plan, extras, [t for t in toc_data if not t.get("appendix")], crates, sets))
    write(DOCS / "library.html", render_library())
    write(DOCS / "practice.html", render_practice())
    write(DOCS / "about.html", render_about(catalog))
    write(DOCS / "tools" / "index.html", render_tools_index())
    write(DOCS / "tools" / "camelot.html", render_tool_camelot())
    write(DOCS / "tools" / "bpm.html", render_tool_bpm())
    write(DOCS / "tools" / "mix-trainer.html", render_tool_mixer())
    write(DOCS / "tools" / "set-builder.html", render_tool_setbuilder())
    write(DOCS / "tools" / "rekordbox.html", render_tool_rekordbox())
    write(DOCS / ".nojekyll", "")
    write(DOCS / "404.html", render_404())
    removed = clean_stale()

    dt = time.time() - t0
    n_audio = sum(1 for g in ("tracks", "practice", "transitions") for t in catalog[g] if t.get("has_audio"))
    print("DJ Lab site build")
    print(f"  tracks       {len(catalog['tracks'])} in catalog ({sum(1 for t in catalog['tracks'] if t.get('has_audio'))} with audio) / {len(plan)} planned")
    print(f"  practice     {len(catalog['practice'])} / {len(extras.get('practice', []))} planned · transitions {len(catalog['transitions'])} / {len(extras.get('transitions', []))} planned")
    print(f"  peaks        {len(peaks['files'])}/{n_audio} audio files ({STATS.get('peaks_computed', 0)} analysed this run)")
    print(f"  guide        {sum(1 for t in toc_data if not t.get('appendix'))} chapters (+{sum(1 for t in toc_data if t.get('appendix'))} appendix) · crates {len(crates)} · sets {len(sets)}")
    print(f"  files        {len(WRITTEN)} written, {len(CHANGED)} changed, {removed} stale removed")
    for w in STATS["warnings"]:
        print(f"  warning: {w}")
    print(f"  done in {dt:.1f}s -> {DOCS.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
