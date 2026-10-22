#!/usr/bin/env python3
"""Listen to every Mashup Lab preview on GitHub's servers and keep only numbers.

For each Apple Music preview (downloaded to a temporary file, deleted right after):
  * Demucs (htdemucs) separates the vocals from the instrumental, in memory
  * vocal activity and instrumental energy per beat (on the Beat This! grid from beats.json)
  * the key (Camelot + strength) of the harmony without drums and vocals
  * pitch-class profiles of the harmony and of the sung melody (to test which transposition fits a vocal over a beat)
  * loudness (LUFS) of the preview and how loud the vocal is inside the mix
  * section changes (bars where the music changes the most: drops, breaks, hooks)
For every word-play link (docs/mashup-lab/wordplay-links.json):
  * Whisper (faster-whisper; ivrit.ai's Hebrew model for Hebrew words) on the separated vocals finds WHEN the link's
    word is sung, and the vocal envelope trims the start and end of that word to about 10 ms.
    Only the timestamps of that one word are kept: never a transcript or any other lyric.

    python tools/mashup_lab_analyze.py tracks --shard 0 --shards 16 --out an-0.json
    python tools/mashup_lab_analyze.py words  --shard 0 --shards 6  --out wd-0.json
    python tools/mashup_lab_analyze.py merge  --parts parts
    python tools/mashup_lab_analyze.py selftest          (pure-python checks, no models)
    python tools/mashup_lab_analyze.py keytest FILES...  (key estimate on audio files with known keys)

analysis.json  {"meta", "map": {"title | artist": {...}}}
  h     FNV-1a hash of the preview URL (a changed link is re-analysed)
  key   Camelot key of the preview's harmony ("8A"), ks its strength 0..1, km the method (e = essentia, n = numpy)
  hc    pitch-class profile of the harmony (bass + other stems), 12 digits 0-9 starting at C
  vc    pitch-class profile of the sung melody (vocal stem), 12 digits 0-9 starting at C
  lufs  integrated loudness of the preview, vdb the vocal level inside the mix (dB, vocal RMS / mix RMS)
  t0    time of the first bar line of the grid (s), the beats below start there
  voc   vocal activity per beat, one digit 0-9 per beat (0 = no vocal)
  nrg   instrumental energy per beat, one digit 0-9 per beat
  sec   bar indices (from t0) where a new section starts
  vs    share of beats with a clear vocal (0..1)
wordtimes.json {"meta", "links": {"A key || B key": {"a": [[start, end, p, n], ...], "b": [[start, end, p, n], ...]}}}
  a = when A's word (before the arrow) is sung in A's preview, b = when B's word is sung in B's preview,
  p = Whisper's confidence, n = how many words of the phrase matched
"""
import argparse
import datetime
import glob
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAB = os.path.join(ROOT, "docs", "mashup-lab")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
SR = 44100
AN_VERSION = 1
WD_VERSION = 1
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mashup_lab_beats import fnv32  # noqa: E402  (same hash as the app)


def key(t):
    return f'{t["t"]} | {t["a"]}'


# ------------------------------------------------------------------ word matching (pure, unit-tested)
HEB = re.compile(r"[א-ת]")
HEB_PREFIX = "והבלמשכ"
SPANISH = re.compile(r"[ñáéíóúü¿¡]", re.I)


def norm_word(w):
    w = unicodedata.normalize("NFKC", w or "").lower()
    w = re.sub(r"[֑-ׇ]", "", w)                      # niqqud / cantillation
    w = w.replace("’", "'").replace("‘", "'").replace("׳", "'").replace("״", "")
    if not HEB.search(w):                                       # accents: llamó ~ llamo
        w = "".join(c for c in unicodedata.normalize("NFKD", w) if not unicodedata.combining(c))
    w = re.sub(r"[^\wא-ת]+", "", w)
    for a, b in (("ך", "כ"), ("ם", "מ"), ("ן", "נ"), ("ף", "פ"), ("ץ", "צ")):   # final letters
        w = w.replace(a, b)
    return w


def skeleton(w):
    """Hebrew spelling varies (ktiv male / haser): drop inner vav / yod; English: crude stem"""
    if HEB.search(w):
        return w[:1] + re.sub(r"[וי]", "", w[1:])
    for suf in ("ing", "in", "ed", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def lev(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


NUM = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
       "10": "ten", "11": "eleven", "12": "twelve", "911": "nineoneone"}


def same_word(heard, want):
    h, w = norm_word(heard), norm_word(want)
    if not h or not w:
        return False
    if NUM.get(h) == w or NUM.get(w) == h:
        return True
    cands = {h}
    if HEB.search(h):                                           # Hebrew: up to two prefix letters (ו ה ב ל מ ש כ)
        if len(h) > 2 and h[0] in HEB_PREFIX:
            cands.add(h[1:])
            if len(h) > 3 and h[1] in HEB_PREFIX:
                cands.add(h[2:])
    for c in cands:
        if c == w or skeleton(c) == skeleton(w):
            return True
        if len(w) >= 5 and lev(skeleton(c), skeleton(w)) <= 1:
            return True
    return False


def tokens(phrase):
    return [t for t in re.split(r"[\s\-]+", phrase.strip()) if norm_word(t)]


def find_phrase(words, phrase):
    """words: [(text, start, end, prob)] -> [[start of first word, end of last word, mean prob, matched words]]"""
    toks = tokens(phrase)
    if not toks:
        return []
    out, n = [], len(toks)
    for i in range(len(words) - n + 1):
        if all(same_word(words[i + j][0], toks[j]) for j in range(n)):
            out.append([round(words[i][1], 3), round(words[i + n - 1][2], 3), round(float(np.mean([words[i + j][3] for j in range(n)])), 2), n])
    if not out and n > 1:                                        # a long phrase: accept its most distinctive word alone
        j = max(range(n), key=lambda k: (len(norm_word(toks[k])), k))
        for wd in words:
            if same_word(wd[0], toks[j]):
                out.append([round(wd[1], 3), round(wd[2], 3), round(wd[3] * .8, 2), 1])
    return out[:6]


def link_words(link):
    """'A word → B word' or 'A word = B word' (B may be a concept such as 'הדרופ' = the drop)"""
    w = link.get("word") or ""
    parts = [p.strip() for p in re.split(r"→|->|=|↔", w) if p.strip()]
    a = parts[0] if parts else ""
    b = parts[1] if len(parts) > 1 else a
    drop = bool(re.search(r"דרופ|\bdrop\b", b, re.I))

    def clean(s):
        return s.strip(" ?!.,\"'")
    return clean(a), clean(b), drop


def phrase_langs(phrase):
    if HEB.search(phrase):
        return ["he"]
    if SPANISH.search(phrase):
        return ["es", None]
    return [None, "en", "es"]


# ------------------------------------------------------------------ per-beat features (pure, unit-tested)
def beat_times(g, dur):
    bpm, b0, db = g[0], g[1], g[2]
    p = 60.0 / bpm
    t0 = b0 + db * p                                             # the first bar line found by the tracker
    while t0 - 4 * p >= -1e-6:
        t0 -= 4 * p
    n = int((dur - t0) / p)
    return t0, p, [t0 + i * p for i in range(max(0, n))]


def per_beat_rms(x, sr, t0, p, n):
    out = np.zeros(n)
    for i in range(n):
        a, b = int(max(0, (t0 + i * p) * sr)), int(min(len(x), (t0 + (i + 1) * p) * sr))
        if b > a:
            out[i] = float(np.sqrt(np.mean(x[a:b] ** 2)))
    return out


def digits(v, ref):
    if ref <= 0:
        return "0" * len(v)
    q = np.clip(np.round(9 * np.sqrt(np.clip(np.asarray(v) / ref, 0, 1))), 0, 9).astype(int)   # sqrt: quiet parts stay visible
    return "".join(str(int(x)) for x in q)


def sections(feat, min_gap=4):
    """bar indices where the per-bar feature vector changes most (novelty peaks), first bar = 0"""
    if len(feat) < 6:
        return [0]
    F = np.asarray(feat, float)
    F = (F - F.mean(0)) / (F.std(0) + 1e-9)
    nov = np.zeros(len(F))
    for i in range(2, len(F) - 1):
        nov[i] = np.linalg.norm(F[i:i + 2].mean(0) - F[max(0, i - 2):i].mean(0))
    out = [0]
    for i in np.argsort(-nov):
        if nov[i] < 1.0:
            break
        if all(abs(i - j) >= min_gap for j in out):
            out.append(int(i))
    return sorted(out)[:8]


def envelope(x, sr=SR, hop_s=0.01):
    hop = int(sr * hop_s)
    n = len(x) // hop
    if n <= 0:
        return np.zeros(1)
    return np.sqrt(np.mean(np.asarray(x[: n * hop], np.float64).reshape(n, hop) ** 2, axis=1))


def refine_word(env, s, e, hop=0.01):
    """Trim Whisper's word boundaries (often 0.1-0.3 s off on singing) to the vocal envelope.
    Returns (start, end, level) or None when there is no voice there (a hallucinated word)."""
    n = len(env)
    a, b = int(max(0, s) / hop), int(min(n - 1, max(s + .05, e) / hop))
    if b <= a or a >= n:
        return None
    pk = float(env[a:b + 1].max())
    ref = float(np.percentile(env, 95)) if n > 10 else pk
    if ref <= 0 or pk < .12 * ref:
        return None
    on, off = .25 * pk, .2 * pk
    k = a
    lo = max(0, int((s - .3) / hop))
    if env[k] >= on:
        while k > lo and env[k - 1] >= on:                       # the word began a bit earlier
            k -= 1
    else:
        hi = min(n - 1, int((s + .25) / hop))
        while k < hi and env[k] < on:                            # the voice starts a bit later
            k += 1
        if env[k] < on:
            k = a
    s2 = k * hop
    voiced = np.nonzero(env[k:b + 1] >= off)[0]
    j = k + int(voiced[-1]) if len(voiced) else b                # Whisper's end may be after the voice stopped
    hi = min(n - 1, int((e + .4) / hop))
    if j == b:
        while j < hi and env[j + 1] >= off:                      # sustained last syllable
            j += 1
    e2 = (j + 1) * hop
    return round(s2, 3), round(max(e2, s2 + .06), 3), round(pk / ref, 2)


# ------------------------------------------------------------------ key / pitch classes (numpy; essentia when available)
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CAMELOT = {("C", "major"): "8B", ("G", "major"): "9B", ("D", "major"): "10B", ("A", "major"): "11B", ("E", "major"): "12B", ("B", "major"): "1B",
           ("F#", "major"): "2B", ("Gb", "major"): "2B", ("C#", "major"): "3B", ("Db", "major"): "3B", ("G#", "major"): "4B", ("Ab", "major"): "4B",
           ("D#", "major"): "5B", ("Eb", "major"): "5B", ("A#", "major"): "6B", ("Bb", "major"): "6B", ("F", "major"): "7B",
           ("A", "minor"): "8A", ("E", "minor"): "9A", ("B", "minor"): "10A", ("F#", "minor"): "11A", ("Gb", "minor"): "11A", ("C#", "minor"): "12A",
           ("Db", "minor"): "12A", ("G#", "minor"): "1A", ("Ab", "minor"): "1A", ("D#", "minor"): "2A", ("Eb", "minor"): "2A", ("A#", "minor"): "3A",
           ("Bb", "minor"): "3A", ("F", "minor"): "4A", ("C", "minor"): "5A", ("G", "minor"): "6A", ("D", "minor"): "7A"}
# key profiles tuned for electronic / pop music (Sha'ath, KeyFinder)
P_MAJ = np.array([6.6, 2.0, 3.5, 2.3, 4.6, 4.0, 2.5, 5.2, 2.4, 3.7, 2.3, 3.4])
P_MIN = np.array([6.5, 2.7, 3.5, 5.4, 2.6, 3.5, 2.5, 5.2, 4.0, 2.7, 4.3, 3.2])


def chroma(x, sr=SR, n_fft=16384, fmin=80.0, fmax=4000.0):
    """pitch-class energy profile (C..B) from spectral peaks near a semitone, normalised to max 1
    (tuned on DJ Lab's own CC0 tracks with known keys: tools/mashup_lab_analyze.py keytest)"""
    x = np.asarray(x, np.float32)
    if len(x) < n_fft:
        return np.zeros(12)
    hop = n_fft // 2
    win = np.hanning(n_fft).astype(np.float32)
    f = np.fft.rfftfreq(n_fft, 1 / sr)
    sel = (f >= fmin) & (f <= fmax)
    midi = 69 + 12 * np.log2(f[sel] / 440.0)
    pc = np.round(midi).astype(int) % 12
    tuned = np.abs(midi - np.round(midi)) < .4
    C = np.zeros(12)
    for st in range(0, len(x) - n_fft + 1, hop):
        S = np.abs(np.fft.rfft(x[st:st + n_fft] * win))[sel]
        mx = S.max()
        if mx <= 0:
            continue
        S = S / mx
        peak = (S > np.roll(S, 1)) & (S >= np.roll(S, -1)) & (S > .02) & tuned   # partials, not noise
        np.add.at(C, pc[peak], S[peak])
    return C / C.max() if C.max() > 0 else C


def key_from_chroma(C):
    C = np.asarray(C, float)
    if C.max() <= 0:
        return None, 0.0
    best, arg = -2.0, None
    for t in range(12):
        for prof, mode in ((P_MAJ, "major"), (P_MIN, "minor")):
            r = float(np.corrcoef(C, np.roll(prof, t))[0, 1])
            if r > best:
                best, arg = r, (NAMES[t], mode)
    return CAMELOT.get(arg), round(max(0.0, min(1.0, best)), 3)


def key_essentia(x):
    import essentia.standard as es
    k, scale, strength = es.KeyExtractor(profileType="edma", sampleRate=SR)(np.asarray(x, np.float32))
    return CAMELOT.get((k, scale)), round(float(strength), 3)


def key_of(x):
    try:
        k, s = key_essentia(x)
        if k:
            return k, s, "e"
    except Exception:
        pass
    k, s = key_from_chroma(chroma(x))
    return k, s, "n"


def camelot_near(a, b):
    """same key, relative major/minor, or one step on the wheel"""
    try:
        na, nb = int(a[:-1]), int(b[:-1])
    except (TypeError, ValueError):
        return False
    return a == b or na == nb or (a[-1] == b[-1] and (na - nb) % 12 in (1, 11))


def pc_digits(C):
    C = np.asarray(C, float)
    if C.max() <= 0:
        return "0" * 12
    return "".join(str(int(v)) for v in np.clip(np.floor(9 * C / C.max() + .5), 0, 9))


def selftest():
    ok = True

    def chk(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(("OK   " if cond else "FAIL ") + name)
    chk("hebrew prefix: ולרקוד ~ לרקוד", same_word("ולרקוד", "לרקוד"))
    chk("hebrew spelling: לרקד ~ לרקוד", same_word("לרקד", "לרקוד"))
    chk("hebrew final letters: חלומ ~ חלום", same_word("חלומ", "חלום"))
    chk("english case/punct: Dance! ~ dance", same_word("Dance!", "dance"))
    chk("english stem: dancing ~ dance", same_word("dancing", "dance"))
    chk("accents: llamo ~ Llamó", same_word("llamo", "Llamó"))
    chk("numbers: two ~ 2", same_word("two", "2"))
    chk("different words stay different: love ~ live is False", not same_word("love", "live"))
    chk("different hebrew words stay different", not same_word("שמש", "ירח"))
    ws = [("you", 1.0, 1.2, .9), ("can't", 1.2, 1.5, .9), ("calm", 5.0, 5.3, .8), ("down", 5.3, 5.8, .7), ("calm", 9.0, 9.2, .9), ("down", 9.2, 9.6, .9)]
    occ = find_phrase(ws, "Calm Down")
    chk("phrase found twice with start/end", len(occ) == 2 and occ[0][:2] == [5.0, 5.8] and occ[1][:2] == [9.0, 9.6] and occ[0][3] == 2)
    occ = find_phrase([("missed", 2.0, 2.4, .9), ("calls", 2.4, 2.9, .9)], "10 Missed Calls")
    chk("long phrase falls back to its most distinctive word", len(occ) == 1 and occ[0][3] == 1)
    chk("link words with arrow", link_words({"word": "לרקוד → Dance"})[:2] == ("לרקוד", "Dance"))
    chk("link words with =", link_words({"word": "Temperature = טמפרטורה"})[:2] == ("Temperature", "טמפרטורה"))
    chk("link B concept = the drop", link_words({"word": "הנה זה בא → הדרופ"})[2] is True)
    chk("languages: hebrew word -> he", phrase_langs("לרקוד") == ["he"])
    t0, p, bt = beat_times([120.0, 0.25, 1, .9, "x"], 10.0)
    chk("beat grid starts on the first bar line", abs(t0 - 0.75) < 1e-9 and abs(p - .5) < 1e-9 and len(bt) == 18)
    x = np.zeros(SR * 4)
    x[SR:SR * 2] = .5
    r = per_beat_rms(x, SR, 0.0, 0.5, 8)
    chk("per-beat rms finds the loud second", r[2] > .4 and r[3] > .4 and r[0] == 0 and r[5] == 0)
    chk("digits 0-9", digits(r, r.max()) == "00990000")
    feat = [[0, 0]] * 8 + [[5, 5]] * 8
    chk("section change found at bar 8", 8 in sections(feat))
    env = np.zeros(400)
    env[150:230] = 1.0                                           # a word sung from 1.50 to 2.30 s
    w = refine_word(env, 1.62, 2.05)
    chk(f"word trimmed to the voice: 1.50-2.30 (got {w})", w is not None and abs(w[0] - 1.5) < .011 and abs(w[1] - 2.3) < .011)
    w = refine_word(env, 1.30, 2.60)
    chk(f"late/early Whisper bounds pulled in (got {w})", w is not None and abs(w[0] - 1.5) < .011 and abs(w[1] - 2.3) < .011)
    chk("no voice -> rejected", refine_word(env, 3.0, 3.5) is None)
    t = np.arange(SR * 8) / SR                                   # A minor triad + bass A: 8A
    sig = sum(np.sin(2 * np.pi * f * t) for f in (110.0, 220.0, 261.63, 329.63, 440.0)) + .3 * np.sin(2 * np.pi * 196.0 * t)
    k, s = key_from_chroma(chroma(sig))
    chk(f"numpy key of an A minor chord = 8A (got {k}, {s})", k == "8A")
    chk("pitch-class digits", pc_digits([1, 0, .5] + [0] * 9) == "905000000000")
    print("SELFTEST_OK" if ok else "SELFTEST_FAIL")
    return 0 if ok else 1


# ------------------------------------------------------------------ audio + models (CI only)
def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def fetch(url, path):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
                f.write(r.read())
            return True
        except Exception:
            time.sleep(3 * (attempt + 1))
    return False


def decode_stereo(path, start=None, dur=None):
    cmd = [ffmpeg_exe(), "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", path]
    if dur is not None:
        cmd += ["-t", str(dur)]
    p = subprocess.run(cmd + ["-ac", "2", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, timeout=120)
    if p.returncode != 0:
        return None
    x = np.frombuffer(p.stdout, dtype="<f4").astype(np.float32)
    if len(x) < SR * 2 * 10:
        return None
    return x.reshape(-1, 2).T.copy()                               # (2, n)


def keytest(files):
    """key of local files with known keys (DJ Lab's own CC0 tracks: the sidecar .json has the Camelot key)"""
    hit = near = done = 0
    for f in files:
        side = os.path.splitext(f)[0] + ".json"
        meta = json.load(open(side, encoding="utf-8")) if os.path.exists(side) else {}
        x = decode_stereo(f, start=45, dur=30)
        if x is None:
            continue
        done += 1
        k, s = key_from_chroma(chroma(x.mean(0)))
        want = meta.get("camelot")
        good = want == k
        rel = bool(want and k and (want[:-1] == k[:-1] or (want[-1] == k[-1] and (int(want[:-1]) - int(k[:-1])) % 12 in (1, 11))))
        hit += good
        near += good or rel
        print(f"{'OK ' if good else ('~  ' if rel else 'XX ')} {os.path.basename(f)[:40]:40s} want {want} got {k} ({s})")
    print(f"exact {hit}/{done}, exact or neighbour {near}/{done}")
    return 0


class Models:
    def __init__(self):
        import torch
        from demucs.apply import apply_model
        from demucs.pretrained import get_model
        torch.set_num_threads(max(1, os.cpu_count() or 2))
        self.torch, self.apply = torch, apply_model
        self.demucs = get_model("htdemucs")
        self.demucs.eval()
        self._wh = {}

    def separate(self, wav):
        with self.torch.no_grad():
            out = self.apply(self.demucs, self.torch.tensor(wav)[None], shifts=0, split=True, overlap=0.25, progress=False)[0]
        return {n: out[i].numpy() for i, n in enumerate(self.demucs.sources)}   # drums, bass, other, vocals

    def whisper(self, hebrew):
        name = "ivrit-ai/whisper-large-v3-turbo-ct2" if hebrew else "large-v3-turbo"
        if name not in self._wh:
            from faster_whisper import WhisperModel
            m = None
            for cand in ([name, "large-v3-turbo"] if hebrew else [name, "large-v3"]):
                try:
                    m = WhisperModel(cand, device="cpu", compute_type="int8")
                    print("whisper model:", cand, flush=True)
                    break
                except Exception as e:
                    print("whisper model", cand, "unavailable:", type(e).__name__, str(e)[:120], flush=True)
            self._wh[name] = m
        return self._wh[name]

    def words(self, vocals16k, lang, hot):
        model = self.whisper(lang == "he")
        if model is None:
            return []
        kw = dict(language=lang, word_timestamps=True, vad_filter=False, beam_size=5, condition_on_previous_text=False)
        if hot and "hotwords" in inspect.signature(model.transcribe).parameters:
            kw["hotwords"] = hot
        segs, _info = model.transcribe(vocals16k, **kw)
        out = []
        for s in segs:
            for w in (s.words or []):
                out.append((w.word, float(w.start), float(w.end), float(w.probability)))
        return out


def resample16(x):
    n = int(len(x) * 16000 / SR)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def lufs_of(wav):
    import pyloudnorm as pyln
    return round(float(pyln.Meter(SR).integrated_loudness(wav.T.astype(np.float64))), 2)


def load_inputs():
    tracks = json.load(open(os.path.join(LAB, "tracks.json"), encoding="utf-8"))
    pmap = json.load(open(os.path.join(LAB, "previews.json"), encoding="utf-8"))["map"]
    bmap = json.load(open(os.path.join(LAB, "beats.json"), encoding="utf-8"))["map"]
    return tracks, pmap, bmap


def separate_preview(models, url):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "p.m4a")
        if not fetch(url, path):
            return None, "download"
        wav = decode_stereo(path)
        os.remove(path)                                              # no audio is kept
    if wav is None:
        return None, "decode"
    st = models.separate(wav)
    st["mix"] = wav
    return st, None


def features(st, grid):
    wav = st["mix"]
    voc = st["vocals"].mean(0)
    harm = st["bass"].mean(0) + st["other"].mean(0)
    inst = harm + st["drums"].mean(0)
    mix = wav.mean(0)
    rec = {}
    try:
        rec["key"], rec["ks"], rec["km"] = key_of(harm)                       # harmony without drums or vocals
    except Exception as e:
        rec["key_err"] = type(e).__name__
    hcv = chroma(harm)
    rec["hc"] = pc_digits(hcv)
    rec["kn"] = key_from_chroma(hcv)[0]                                       # numpy estimate, for the report only
    venv = envelope(voc)
    loud = venv > .25 * (np.percentile(venv, 95) + 1e-9)
    vsel = np.repeat(loud, int(SR * .01))
    vv = voc[: len(vsel)][vsel[: len(voc)]]
    rec["vc"] = pc_digits(chroma(vv, fmin=80.0, fmax=2000.0)) if len(vv) > SR else "0" * 12
    try:
        rec["lufs"] = lufs_of(wav)
    except Exception:
        pass
    rec["vdb"] = round(float(20 * np.log10((np.sqrt(np.mean(voc ** 2)) + 1e-9) / (np.sqrt(np.mean(mix ** 2)) + 1e-9))), 1)
    if grid:
        dur = wav.shape[1] / SR
        t0, p, bt = beat_times(grid, dur)
        n = len(bt)
        vr, ir, mr = per_beat_rms(voc, SR, t0, p, n), per_beat_rms(inst, SR, t0, p, n), per_beat_rms(mix, SR, t0, p, n)
        rec["voc"] = digits(vr, max(1e-6, float(np.percentile(vr, 95)) if n else 0))
        rec["nrg"] = digits(ir, max(1e-6, float(np.percentile(ir, 95)) if n else 0))
        clear = (vr / (mr + 1e-9)) > 0.35                            # the vocal clearly present on that beat
        rec["vs"] = round(float(clear.mean()) if n else 0, 3)
        lo, dr = per_beat_rms(st["bass"].mean(0), SR, t0, p, n), per_beat_rms(st["drums"].mean(0), SR, t0, p, n)
        bars = n // 4
        feat = [[np.mean(lo[4 * b:4 * b + 4]), np.mean(dr[4 * b:4 * b + 4]), np.mean(ir[4 * b:4 * b + 4]), np.mean(vr[4 * b:4 * b + 4])] for b in range(bars)]
        rec["sec"] = sections(feat)
        rec["t0"] = round(t0, 4)
    return rec


def cmd_tracks(args):
    tracks, pmap, bmap = load_inputs()
    old = {}
    if os.path.exists(args.existing) and not args.force:
        ex = json.load(open(args.existing, encoding="utf-8"))
        if ex.get("meta", {}).get("v") == AN_VERSION:
            old = ex.get("map", {})
    todo = []
    for t in tracks:
        v = pmap.get(key(t)) or {}
        if not v.get("p"):
            continue
        h = fnv32(v["p"])
        if key(t) in old and old[key(t)].get("h") == h and "err" not in old[key(t)]:
            continue
        todo.append((t, v["p"], h))
    mine = todo[args.shard::args.shards][: args.limit or None]
    print(f"shard {args.shard}: {len(mine)} of {len(todo)} previews", flush=True)
    models = Models()
    out, t_start = {}, time.time()
    for i, (t, url, h) in enumerate(mine, 1):
        g = bmap.get(key(t))
        try:
            st, err = separate_preview(models, url)
            rec = features(st, g if g and g[3] >= .5 else None) if st else {"err": err}
        except Exception as e:
            rec = {"err": "exc:" + type(e).__name__ + ":" + str(e)[:60]}
        rec["h"] = h
        out[key(t)] = rec
        if i % 10 == 0 or i == len(mine):
            json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False)
            print(f"shard {args.shard}: {i}/{len(mine)} ({time.time() - t_start:.0f}s) last: key {rec.get('key')} {rec.get('km')} vocal share {rec.get('vs')}", flush=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False)
    return 0


def cmd_words(args):
    tracks, pmap, bmap = load_inputs()
    links = json.load(open(os.path.join(LAB, "wordplay-links.json"), encoding="utf-8"))
    need = {}                                                        # track key -> [(link id, side, phrase)]
    for l in links:
        a, b, drop = link_words(l)
        lid = l["a"] + " || " + l["b"]
        need.setdefault(l["a"], []).append((lid, "a", a))
        if not drop:
            need.setdefault(l["b"], []).append((lid, "b", b))
    ks = sorted(k for k in need if (pmap.get(k) or {}).get("p"))
    mine = ks[args.shard::args.shards][: args.limit or None]
    print(f"words shard {args.shard}: {len(mine)} tracks", flush=True)
    models = Models()
    out, stats = {}, {"tracks": 0, "phrases": 0, "found": 0}
    for i, k in enumerate(mine, 1):
        url = pmap[k]["p"]
        try:
            st, err = separate_preview(models, url)
            if not st:
                print(f"{i}/{len(mine)} {err}", flush=True)
                continue
            voc = st["vocals"].mean(0)
            env = envelope(voc)
            v16 = resample16(voc)
            heard = {}                                               # lang -> words heard (never stored or printed)
            hot = " ".join(sorted({p for _, _, p in need[k]}))
            stats["tracks"] += 1
            for lid, side, phrase in need[k]:
                stats["phrases"] += 1
                occ = []
                for lang in phrase_langs(phrase):
                    if lang not in heard:
                        heard[lang] = models.words(v16, lang, hot)
                    for s, e, p, nt in find_phrase(heard[lang], phrase):
                        r = refine_word(env, s, e)
                        if r:
                            occ.append([r[0], r[1], p, nt])
                    if occ:
                        break
                rec = out.setdefault(lid, {})
                rec[side] = sorted(occ)[:6]
                rec[side + "_h"] = fnv32(url)
                stats["found"] += bool(occ)
            print(f"{i}/{len(mine)} phrases found {sum(1 for lid, s, _ in need[k] if out.get(lid, {}).get(s))}/{len(need[k])} "
                  f"(whisper runs {len(heard)})", flush=True)
        except Exception as e:
            print(f"{i}/{len(mine)} error {type(e).__name__}: {str(e)[:100]}", flush=True)
        json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False)
    print("words stats:", stats, flush=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False)
    return 0


def cmd_merge(args):
    tracks, pmap, bmap = load_inputs()
    keys = {key(t) for t in tracks}
    an_path, wd_path = os.path.join(LAB, "analysis.json"), os.path.join(LAB, "wordtimes.json")
    old = {}
    if os.path.exists(an_path):
        ex = json.load(open(an_path, encoding="utf-8"))
        if ex.get("meta", {}).get("v") == AN_VERSION:
            old = ex.get("map", {})
    an = dict(old)
    for f in sorted(glob.glob(os.path.join(args.parts, "**", "an-*.json"), recursive=True)):
        try:
            for k, v in json.load(open(f, encoding="utf-8")).items():
                if "err" in v and k in an and "err" not in an[k] and an[k].get("h") == v.get("h"):
                    continue                                         # keep a good old result over a failed retry
                an[k] = v
        except Exception as e:
            print("skip", f, e)
    catalog = {key(t): t.get("k") for t in tracks}
    agree = {}
    for k, v in an.items():                                          # measured key vs the catalog key (web sources)
        want = catalog.get(k)
        for name, got in (("essentia" if v.get("km") == "e" else "numpy", v.get("key")), ("numpy_only", v.get("kn"))):
            if not want or not got:
                continue
            d = agree.setdefault(name, {"n": 0, "exact": 0, "near": 0})
            d["n"] += 1
            d["exact"] += want == got
            d["near"] += want == got or camelot_near(want, got)
    fields = ("h", "key", "ks", "km", "hc", "vc", "lufs", "vdb", "t0", "voc", "nrg", "sec", "vs", "err")
    an = {k: {kk: v[kk] for kk in fields if kk in v} for k, v in an.items() if k in keys}
    ok = sum(1 for v in an.values() if "err" not in v)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    meta = {"generated": now, "v": AN_VERSION, "tracks": len(an), "ok": ok,
            "note": "Measured from the Apple Music previews: numbers only, no audio and no lyrics are stored."}
    if an:
        json.dump({"meta": meta, "map": an}, open(an_path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    wd = {}
    if os.path.exists(wd_path):
        ex = json.load(open(wd_path, encoding="utf-8"))
        if ex.get("meta", {}).get("v") == WD_VERSION:
            wd = ex.get("links", {})
    for f in sorted(glob.glob(os.path.join(args.parts, "**", "wd-*.json"), recursive=True)):
        try:
            for lid, v in json.load(open(f, encoding="utf-8")).items():
                wd.setdefault(lid, {}).update(v)
        except Exception as e:
            print("skip", f, e)
    links = json.load(open(os.path.join(LAB, "wordplay-links.json"), encoding="utf-8"))
    report = {"generated": now, "analysis": meta, "key_vs_catalog": agree, "links": []}
    if wd:
        found = 0
        for l in links:
            lid = l["a"] + " || " + l["b"]
            v = wd.get(lid, {})
            drop = link_words(l)[2]
            fa, fb = bool(v.get("a")), (drop or bool(v.get("b")))
            found += fa and fb
            report["links"].append({"link": lid, "a": len(v.get("a") or []), "b": "drop" if drop else len(v.get("b") or [])})
        wmeta = {"generated": now, "v": WD_VERSION, "links": len(links), "both_found": found,
                 "note": "When each link's word is sung in each preview (seconds). Timestamps only; no lyrics are stored."}
        json.dump({"meta": wmeta, "links": wd}, open(wd_path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        report["words"] = wmeta
    if args.report:
        methods = {}
        for v in an.values():
            methods[v.get("km", "-")] = methods.get(v.get("km", "-"), 0) + 1
        report["key_methods"] = methods
        vs = [v["vs"] for v in an.values() if "vs" in v]
        report["vocal_share_median"] = float(np.median(vs)) if vs else None
        errs = {}
        for v in an.values():
            if "err" in v:
                errs[v["err"][:30]] = errs.get(v["err"][:30], 0) + 1
        report["errors"] = errs
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        json.dump(report, open(args.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("analysis:", meta, "| words:", report.get("words"))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("tracks", "words"):
        a = sub.add_parser(name)
        a.add_argument("--shard", type=int, default=0)
        a.add_argument("--shards", type=int, default=1)
        a.add_argument("--limit", type=int, default=0)
        a.add_argument("--force", action="store_true")
        a.add_argument("--existing", default=os.path.join(LAB, "analysis.json"))
        a.add_argument("--out", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--parts", required=True)
    m.add_argument("--report", default="")
    sub.add_parser("selftest")
    kt = sub.add_parser("keytest")
    kt.add_argument("files", nargs="+")
    x = ap.parse_args()
    if x.cmd == "tracks":
        return cmd_tracks(x)
    if x.cmd == "words":
        return cmd_words(x)
    if x.cmd == "merge":
        return cmd_merge(x)
    if x.cmd == "keytest":
        return keytest(x.files)
    return selftest()


if __name__ == "__main__":
    sys.exit(main())
