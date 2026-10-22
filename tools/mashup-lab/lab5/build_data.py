#!/usr/bin/env python3
"""Mashup Lab v5 - data build (adapted from SP/lab/build1000.py).

Reads   SP/lab/data1000.json + SP/lab/src1000.json   (v4 dataset, all rows kept)
        SP/lab5/data/*.tsv                           (new verified tracks)
Writes  SP/lab5/data.json  [{g,t,a,bpm,k,y,hot,s}]   (same row shape as v4)
        SP/lab5/src.json   [{id,n,u}]                (v4 shape {n,u} + id so every row's s resolves)
        SP/lab5/DATA_REPORT.md (auto tables + data/report_notes.md)

TSV columns (tab separated, '#' lines are comments):
  g  t  a  bpm  k  y  hot  s  [sg]  [e]  [v]
  y  = year or None, hot = 1/0, s = primary source id (defined below / data/sources_extra.py)
  sg = optional sub-genre label in English (see SUBGENRES; "-" or empty = none) -> data.json "sg"
  e  = optional energy from the source page: "NN%" -> round(NN/10) (half up, clamp 1-10), or a bare 1-10
       value when the page already shows a 0-10 scale (songdata playlist/album tables). Empty = no source
       value (the app then estimates it, SPEC 7). -> data.json "e"
  v  = optional second-source evidence: space separated source ids or page URLs
       (tunebat / songdata / beatport / mixgraph / songbpm / getsongbpm) that show the
       same BPM (or exact half/double) and the same Camelot key.
"""
import json, re, glob, os, sys
from collections import Counter, defaultdict
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.join(HERE, "..", "lab")
DATA_DIR = os.path.join(HERE, "data")

GENRES = {"mizr": "מזרחית", "ilpop": "פופ ישראלי", "house": "האוס", "techhouse": "טק האוס",
          "afrohouse": "אפרו האוס", "regg": "רגאטון", "latin": "לטיני", "hiphop": "היפ הופ",
          "rnb": "R&B", "pop": "פופ", "afro": "אפרוביטס", "amapiano": "אמאפיאנו",
          "dancehall": "דאנסהול", "techno": "טכנו", "edm": "EDM", "dnb": "דראם אנד בייס",
          "ukg": "UK גראז׳"}

SUBGENRES = {
    # techno
    "Melodic Techno", "Peak Time Techno", "Hard Techno", "Hypnotic Techno", "Minimal Techno", "Industrial Techno",
    "Indie Dance", "Classic Techno",
    # house family
    "Deep House", "Melodic House", "Progressive House", "Tech House", "Bass House", "Latin Tech", "Latin House",
    "Afro House", "Afro Tech", "Organic House", "Piano House", "UK House", "Classic House", "Disco House",
    "Funky House", "Vocal House", "Electro House", "Future House", "Jackin House", "Minimal Tech",
    # amapiano / afro
    "Private School Amapiano", "Log Drum Amapiano", "Amapiano", "Afro-fusion", "Street-pop", "Afrobeats",
    "Afro-pop", "Afro-R&B", "Afro-dancehall", "Highlife", "Gqom",
    # israeli
    "Mizrahi Pop", "Mizrahi Party", "Mizrahi Ballad", "Israeli Pop", "Israeli Dance-Pop", "Israeli Hip-Hop",
    "Israeli Rock", "Israeli Ballad",
    # global
    "Reggaeton", "Latin Pop", "Bachata", "Salsa", "Cumbia", "Dembow", "Brazilian Funk", "Latin Trap", "Corridos",
    "Dancehall", "Reggae", "Soca", "UK Garage", "2-Step", "Speed Garage", "Bassline",
    "Pop", "Dance-Pop", "Eurodance", "Synth-pop", "Disco", "Nu-Disco", "Funk",
    "Hip-Hop", "Trap", "Drill", "Boom Bap", "Crunk", "R&B", "Contemporary R&B",
    "Big Room", "Progressive EDM", "Future Bass", "Electro", "Moombahton", "Trance", "Slap House", "Hard Dance",
    "Drum & Bass", "Liquid DnB", "Jump Up", "Jungle",
}

# ---------------------------------------------------------------- v4 source registry
# src1000.json has no ids; rebuild id -> url from src600.json + the ids build1000.py added.
mg = lambda slug: "https://www.mixgraph.io/artists/" + slug
V4_ADDED = {"mg_sza": "sza", "mg_weeknd": "the-weeknd", "mg_cb": "chris-brown", "mg_riri": "rihanna",
            "mg_dua": "dua-lipa", "mg_bruno": "bruno-mars", "mg_gaga": "lady-gaga", "mg_sabrina": "sabrina-carpenter",
            "mg_shakira": "shakira", "mg_seanpaul": "sean-paul", "mg_shenseea": "shenseea", "mg_kartel": "vybz-kartel",
            "mg_kabza": "kabza-de-small", "mg_phori": "dj-maphorisa", "mg_chase": "chase-and-status",
            "mg_subfocus": "sub-focus", "mg_pendulum": "pendulum", "mg_virji": "sammy-virji", "mg_mk": "mk",
            "mg_anitta": "anitta", "mg_bey": "beyonce", "mg_usher": "usher", "mg_maluma": "maluma",
            "mg_guetta": "david-guetta", "mg_avicii": "avicii", "mg_garrix": "martin-garrix", "mg_coffee": "black-coffee",
            "mg_romeo": "romeo-santos", "mg_shm": "swedish-house-mafia", "mg_skrillex": "skrillex"}
V4_ADDED_URL = {k: mg(v) for k, v in V4_ADDED.items()}
V4_ADDED_URL.update({
    "sd_rec_static": "https://songdata.io/track/4N73xWDRMVO462UXiabr1C/-by-Static-Ben-El-Rami-Kleinstein",
    "sd_rec_itay3": "https://songdata.io/track/0tewqHTtZMfb7sPsqTyRVc/-by-Itay-Levi",
    "sd_rec_peer2": "https://songdata.io/track/2SHgmGUeF1WnoS4N37waU6/-by-"})

# ---------------------------------------------------------------- new sources (v5)
# id: (display name, url).  MixGraph artist pages list each track with BPM + Camelot + key name.
NEW_SRC = {}
def add_mg(i, name, slug): NEW_SRC[i] = ("MixGraph · " + name, mg(slug))
for i, name, slug in [
    ("mg_hugel", "HUGEL", "hugel"), ("mg_hoffstadt", "Marlon Hoffstadt", "marlon-hoffstadt"),
    ("mg_cajmere", "Cajmere", "cajmere"), ("mg_shadu", "SHADU", "shadu"), ("mg_marasi", "Marasi", "marasi"),
    ("mg_adamport", "Adam Port", "adam-port"), ("mg_andme", "&ME", "and-me"), ("mg_rampa", "Rampa", "rampa"),
    ("mg_enoo", "Enoo Napa", "enoo-napa"), ("mg_mercier", "Francis Mercier", "francis-mercier"),
    ("mg_dacapo", "Da Capo", "da-capo"), ("mg_caiiro", "Caiiro", "caiiro"), ("mg_moojo", "Moojo", "moojo"),
    ("mg_omahlay", "Omah Lay", "omah-lay"), ("mg_joeboy", "Joeboy", "joeboy"), ("mg_fireboy", "Fireboy DML", "fireboy-dml"),
    ("mg_victony", "Victony", "victony"), ("mg_shallipopi", "Shallipopi", "shallipopi"),
    ("mg_wiz", "Wizkid", "wizkid"), ("mg_burna", "Burna Boy", "burna-boy"), ("mg_davido", "Davido", "davido"),
    ("mg_rema", "Rema", "rema"), ("mg_ayra", "Ayra Starr", "ayra-starr"), ("mg_asake", "Asake", "asake"),
    ("mg_fisher", "FISHER", "fisher"), ("mg_lake", "Chris Lake", "chris-lake"), ("mg_summit", "John Summit", "john-summit"),
    ("mg_maup", "Mau P", "mau-p"), ("mg_cloonee", "Cloonee", "cloonee"), ("mg_dolla", "Dom Dolla", "dom-dolla"),
    ("mg_fred", "Fred again..", "fred-again"), ("mg_fodera", "Sonny Fodera", "sonny-fodera"),
    ("mg_vintage", "Vintage Culture", "vintage-culture"), ("mg_disclosure", "Disclosure", "disclosure"),
    ("mg_duke", "Duke Dumont", "duke-dumont"), ("mg_calvin", "Calvin Harris", "calvin-harris"),
    ("mg_pdm", "Purple Disco Machine", "purple-disco-machine"), ("mg_mochakk", "Mochakk", "mochakk"),
    ("mg_acraze", "ACRAZE", "acraze"), ("mg_camelphat", "CamelPhat", "camelphat"), ("mg_discolines", "Disco Lines", "disco-lines"),
]:
    add_mg(i, name, slug)
# single pages (songdata / tunebat / beatport) are added here as they are used
NEW_SRC.update({
    "bp_shadu_contigo": ("Beatport · Shadu - Contigo (Extended Mix)", "https://www.beatport.com/track/contigo/19956330"),
    "sd_peru": ("songdata · Peru (Fireboy DML), incl. recommendations", "https://songdata.io/track/0lk5tzmaJWVAv5GBvpm3xu/Peru-by-Fireboy-DML"),
})
try:
    sys.path.insert(0, DATA_DIR)
    from sources_extra import EXTRA_SRC  # data/sources_extra.py: more ids, kept next to the TSVs
    NEW_SRC.update(EXTRA_SRC)
except ImportError:
    pass

# second-source evidence: a page URL on one of these sites (or any defined id)
SITES = {"tunebat.com": ("tb", "Tunebat (track pages)", "https://tunebat.com"),
         "songdata.io": ("sd", "songdata.io (track pages)", "https://songdata.io"),
         "beatport.com": ("bp", "Beatport (track pages)", "https://www.beatport.com"),
         "mixgraph.io": ("mg", "MixGraph (artist/track pages)", "https://www.mixgraph.io"),
         "songbpm.com": ("sb", "SongBPM (track pages)", "https://songbpm.com"),
         "getsongbpm.com": ("gsb", "GetSongBPM (track pages)", "https://getsongbpm.com")}
def site_of(url):
    h = urlparse(url).netloc.lower()
    for dom in SITES:
        if h == dom or h.endswith("." + dom):
            return dom
    return None

# existing rows moved into the new genre ids (artist-level, documented in DATA_REPORT.md).
# Set MOVE_EXISTING = False to keep every v4 row in its v4 genre.
MOVE_EXISTING = True
MOVE_BY_FIRST_ARTIST = {("house", "fisher"): "techhouse", ("house", "mau p"): "techhouse",
                        ("house", "chris lake"): "techhouse", ("house", "black coffee"): "afrohouse"}

# ---------------------------------------------------------------- helpers
def norm_title(s):
    s = s.lower().replace("’", "'")
    s = re.sub(r"\s*[\(\[](?:feat\.?|ft\.?|with)\s[^\)\]]*[\)\]]", "", s)
    s = re.sub(r"\s*[\(\[](?:extended|extended mix|extended version|original mix|radio edit|club mix)[\)\]]", "", s)
    s = re.sub(r"\s+-\s+(?:extended|extended mix|original mix|radio edit)$", "", s)
    s = re.sub(r"[^\w֐-׿']+", " ", s)
    return re.sub(r"\s+", " ", s).strip()
def first_artist(a):
    return re.split(r",|&| x | feat\.? | ft\.? ", a.lower())[0].strip()
def key_of(t, a):
    return (norm_title(t), first_artist(a))

KEY_RE = re.compile(r"(1[0-2]|[1-9])[AB]")

def main():
    old = json.load(open(os.path.join(LAB, "data1000.json"), encoding="utf-8"))
    oldsrc = json.load(open(os.path.join(LAB, "src1000.json"), encoding="utf-8"))
    s600 = json.load(open(os.path.join(LAB, "src600.json"), encoding="utf-8"))
    S = {x["id"]: x["u"] for x in s600}
    S.update(V4_ADDED_URL)
    name_by_url = {x["u"]: x["n"] for x in oldsrc}
    N = {k: name_by_url.get(u, k) for k, u in S.items()}
    # v4 integrity: the rebuilt registry must cover exactly the URLs of src1000.json
    assert {S[r["s"]] for r in old} == set(name_by_url), "v4 source registry mismatch"
    errors = []
    for k, (n, u) in NEW_SRC.items():
        if k in S:
            # reusing a v4 id for the same page is fine (e.g. mg_fisher); a different URL is not
            if S[k] != u: errors.append(f"source id {k} redefined with another URL")
            continue
        if u in S.values():
            errors.append(f"source {k}: URL already registered under another id")
        S[k] = u; N[k] = n

    before = Counter(r["g"] for r in old)
    data = [dict(r) for r in old]
    moved = []
    if MOVE_EXISTING:
        for r in data:
            to = MOVE_BY_FIRST_ARTIST.get((r["g"], first_artist(r["a"])))
            if to:
                moved.append((r["t"], r["a"], r["g"], to)); r["g"] = to

    seen = {key_of(r["t"], r["a"]): "v4" for r in data}
    added, dups, dbl, same_site2, per_file = [], [], 0, 0, Counter()
    evidence_sites = Counter()
    for f in sorted(glob.glob(os.path.join(DATA_DIR, "*.tsv"))):
        fn = os.path.basename(f)
        for ln, line in enumerate(open(f, encoding="utf-8"), 1):
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            p = line.split("\t")
            where = f"{fn}:{ln}"
            if len(p) not in (8, 9, 10, 11):
                errors.append(f"{where}: {len(p)} columns"); continue
            g, t, a, b, k, y, h, s = [x.strip() for x in p[:8]]
            sg = p[8].strip() if len(p) >= 9 else ""
            sg = "" if sg in ("", "-") else sg
            if sg and sg not in SUBGENRES: errors.append(f"{where}: sub-genre '{sg}' not in SUBGENRES")
            # e = energy 1-10 from the source page: "NN%" (MixGraph / tunebat / songdata track page) -> round half up
            # of NN/10, or a bare 1-10 value (songdata playlist / album tables already show energy on a 0-10 scale)
            ev = p[9].strip() if len(p) >= 10 else ""
            en = None
            if ev not in ("", "-"):
                try:
                    if ev.endswith("%"):
                        pct = float(ev[:-1]); assert 0 <= pct <= 100
                        en = max(1, min(10, int(pct / 10 + 0.5)))
                    else:
                        en = int(ev); assert 1 <= en <= 10
                except Exception:
                    errors.append(f"{where}: energy {ev}"); continue
            v = p[10].split() if len(p) == 11 else []
            if g not in GENRES: errors.append(f"{where}: genre {g}")
            if not t or not a: errors.append(f"{where}: empty title/artist")
            if not KEY_RE.fullmatch(k): errors.append(f"{where}: key {k}")
            try:
                b = int(b); assert 55 <= b <= 200
            except Exception:
                errors.append(f"{where}: bpm {b}"); continue
            if y != "None":
                try:
                    y = int(y); assert 1950 <= y <= 2026
                except Exception:
                    errors.append(f"{where}: year {y}"); continue
            else:
                y = None
            if h not in ("0", "1"): errors.append(f"{where}: hot {h}")
            if s not in S: errors.append(f"{where}: source {s} undefined"); continue
            psite = site_of(S[s])
            two = False
            for e in v:
                if e in S:
                    es = site_of(S[e])
                elif e.startswith("http"):
                    es = site_of(e)
                    if es is None: errors.append(f"{where}: evidence site not allowed {e}"); continue
                else:
                    errors.append(f"{where}: evidence {e} undefined"); continue
                evidence_sites[es] += 1
                if es != psite: two = True
            if v and not two: same_site2 += 1
            kk = key_of(t, a)
            if kk in seen:
                dups.append((t, a, seen[kk], where)); continue
            seen[kk] = where
            row = {"g": g, "t": t, "a": a, "bpm": b, "k": k, "y": y, "hot": h == "1", "s": s}
            if sg: row["sg"] = sg
            if en is not None: row["e"] = en
            data.append(row); added.append((row, two, fn)); per_file[fn] += 1
            dbl += two

    # placeholder-album guard: a new source whose rows (>=4) all share one BPM+key is rejected
    by_src = defaultdict(list)
    for row, _, _ in added:
        by_src[row["s"]].append((row["bpm"], row["k"]))
    for sid, vals in by_src.items():
        if len(vals) >= 4 and len(set(vals)) == 1:
            errors.append(f"source {sid}: all {len(vals)} rows share {vals[0]} (placeholder album?)")
    grp = defaultdict(list)
    for row, _, _ in added:
        grp[(row["s"], first_artist(row["a"]), row["y"], row["bpm"], row["k"], row.get("e"))].append(row["t"])
    for kk, ts in grp.items():
        if len(ts) >= 3:
            errors.append(f"source {kk[0]}: {len(ts)} rows of {kk[1]} ({kk[2]}) share {kk[3]} {kk[4]} e={kk[5]}: {ts} (placeholder album?)")
    # final validation of every row (old + new)
    for r in data:
        assert KEY_RE.fullmatch(r["k"]), r
        assert 55 <= r["bpm"] <= 200, r
        assert r["s"] in S, r
        assert r["g"] in GENRES, r
    if errors:
        print("VALIDATION FAILED:"); print("\n".join(errors)); sys.exit(1)

    used = sorted({r["s"] for r in data})
    src = [{"id": k, "n": N[k], "u": S[k]} for k in used]
    for dom in sorted(evidence_sites):
        sid, n, u = SITES[dom]
        if not any(x["u"] == u for x in src):
            src.append({"id": "site_" + sid, "n": n + " · אימות שני", "u": u})
    src.sort(key=lambda x: (not x["n"].startswith("MixGraph"), x["n"]))
    atomic_json(os.path.join(HERE, "data.json"), data, check_data)
    atomic_json(os.path.join(HERE, "src.json"), src, lambda x: check_src(x, data))

    after = Counter(r["g"] for r in data)
    new_by_g = Counter(r["g"] for r, _, _ in added)
    stats = {"v4_total": len(old), "total": len(data), "new": len(added), "double_verified": dbl,
             "second_page_same_site": same_site2, "dups_skipped": len(dups), "moved": len(moved),
             "before": before, "after": after, "new_by_genre": new_by_g, "files": per_file,
             "evidence_sites": evidence_sites, "sources": len(src),
             "sg": Counter(r.get("sg") for r, _, _ in added if r.get("sg")),
             "sg_new": sum(1 for r, _, _ in added if r.get("sg")), "e_new": sum(1 for r, _, _ in added if "e" in r),
             "e_all": sum(1 for r in data if "e" in r), "sg_all": sum(1 for r in data if r.get("sg")),
             "e_by_g": Counter(r["g"] for r in data if "e" in r), "hot_new": sum(1 for r, _, _ in added if r["hot"])}
    write_report(stats, moved, dups, added)
    print(f"v4 {len(old)} + new {len(added)} = {len(data)} | double-verified {dbl} | dups skipped {len(dups)} | moved {len(moved)} | sources {len(src)}")
    print("new by genre:", dict(new_by_g.most_common()))
    print("after:", dict(after.most_common()))
    if dups: print("dups:", [(d[0], d[3]) for d in dups][:60])

def write_report(st, moved, dups, added):
    notes_path = os.path.join(DATA_DIR, "report_notes.md")
    notes = open(notes_path, encoding="utf-8").read() if os.path.exists(notes_path) else ""
    excl_path = os.path.join(DATA_DIR, "excluded.txt")
    excl = [l.rstrip("\n") for l in open(excl_path, encoding="utf-8")] if os.path.exists(excl_path) else []
    L = ["# Mashup Lab v5 — data report", "",
         f"_Generated by `build_data.py`._ v4 rows: **{st['v4_total']}** → v5 rows: **{st['total']}** "
         f"(**{st['new']} new**, {st['double_verified']} of them confirmed by a second site, "
         f"{st['second_page_same_site']} by a second page of the same site). Sources listed in `src.json`: {st['sources']}.", "",
         "## Tracks per genre", "", "| genre | Hebrew | v4 | moved in/out | new | v5 |", "|---|---|---:|---:|---:|---:|"]
    mv = Counter()
    for _, _, fr, to in moved:
        mv[fr] -= 1; mv[to] += 1
    for g in GENRES:
        b, a, n = st["before"].get(g, 0), st["after"].get(g, 0), st["new_by_genre"].get(g, 0)
        if a or b:
            L.append(f"| {g} | {GENRES[g]} | {b} | {mv.get(g, 0):+d} | {n} | {a} |")
    L += ["", f"Second-source pages used: " + ", ".join(f"{d} ×{c}" for d, c in st["evidence_sites"].most_common()), ""]
    L += ["## Coverage of the optional fields", "",
          f"- `sg` (sub-genre): {st['sg_new']} of {st['new']} new rows; {st['sg_all']} of {st['total']} rows overall.",
          f"- `e` (energy from a source page): {st['e_new']} of {st['new']} new rows; {st['e_all']} of {st['total']} rows overall "
          f"(the app estimates the rest per SPEC §7). By genre: " + ", ".join(f"{g} {c}" for g, c in st["e_by_g"].most_common()) + ".",
          f"- `hot=1` on {st['hot_new']} of {st['new']} new rows.", ""]
    if st["sg"]:
        L += ["## Sub-genres (`sg`) on new rows", "", ", ".join(f"{k} {v}" for k, v in sorted(st["sg"].items(), key=lambda x: -x[1])), ""]
    if moved:
        L += ["## Existing rows moved to the new genre ids", "",
              "Artist-level moves only (everything else stays where v4 had it): " +
              "; ".join(f"{a} → {to}" for (g, a), to in MOVE_BY_FIRST_ARTIST.items()) +
              f" — {len(moved)} rows.", ""]
    if dups:
        L += ["## Skipped duplicates (already in v4 or another TSV)", ""] + [f"- {t} — {a} ({w})" for t, a, _, w in dups] + [""]
    if excl:
        L += ["## Excluded candidates", ""] + [f"- {x}" for x in excl if x.strip()] + [""]
    L += [notes]
    atomic_text(os.path.join(HERE, "DATA_REPORT.md"), "\n".join(L))

def atomic_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def atomic_json(path, obj, check):
    """write temp file, re-read + validate it, then rename over the target (readers never see a partial file)"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False); f.flush(); os.fsync(f.fileno())
    check(json.load(open(tmp, encoding="utf-8")))
    os.replace(tmp, path)

def check_data(rows):
    assert isinstance(rows, list) and rows
    for r in rows:
        assert set(r) <= {"g", "t", "a", "bpm", "k", "y", "hot", "s", "sg", "e"} and {"g", "t", "a", "bpm", "k", "y", "hot", "s"} <= set(r), r
        assert r["g"] in GENRES and KEY_RE.fullmatch(r["k"]) and 55 <= r["bpm"] <= 200 and isinstance(r["hot"], bool), r
        assert "e" not in r or (isinstance(r["e"], int) and 1 <= r["e"] <= 10), r
        assert r["y"] is None or 1950 <= r["y"] <= 2026, r

def check_src(src, rows):
    ids = {x["id"] for x in src}
    assert all(x.get("n") and x.get("u", "").startswith("https://") for x in src)
    assert all(r["s"] in ids for r in rows), "row source missing from src.json"

if __name__ == "__main__":
    main()
