"""Procedural cover art (800×800 JPEG ≤ 200 KB) per track.

Palette per family (house warm orange/pink, techno dark cyan/violet, mainstream gold/magenta,
breadth green/teal), a radial waveform drawn from the track's real loudness envelope, geometric
motifs varied by seed, English + Hebrew title (raqm shaping), BPM/Camelot badge and DJ LAB mark.
"""
from __future__ import annotations

import colorsys
import io
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"
FONT_REG = FONT_DIR / "DejaVuSans.ttf"

PALETTES = {
    "house": [("#FF7A3D", "#B3125E", "#FFD166"), ("#FF5E62", "#7A1E5C", "#FFC371"), ("#F97316", "#9D174D", "#FDE68A")],
    "techno": [("#05060F", "#2B0B57", "#00E5FF"), ("#070B1A", "#3B0A5E", "#7DF9FF"), ("#02040A", "#16213E", "#B388FF")],
    "mainstream": [("#2D0B4E", "#E0218A", "#FFC300"), ("#3A0CA3", "#F72585", "#FFD60A"), ("#4A044E", "#D9006C", "#FFB703")],
    "breadth": [("#00332E", "#00897B", "#B9F6CA"), ("#012A36", "#0E9594", "#C6FF00"), ("#06281F", "#2A9D8F", "#E9FFDB")],
    "practice": [("#111827", "#374151", "#FACC15")],
}


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _font(path, size):
    try:
        return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:  # pragma: no cover - raqm missing
        return ImageFont.truetype(str(path), size)


def _shift(rgb, dh):
    h, l, s = colorsys.rgb_to_hls(*[v / 255 for v in rgb])
    r, g, b = colorsys.hls_to_rgb((h + dh) % 1.0, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


def _fit_font(draw, text, path, max_w, start, min_size=26, **kw):
    size = start
    while size > min_size:
        f = _font(path, size)
        if draw.textlength(text, font=f, **kw) <= max_w:
            return f
        size -= 2
    return _font(path, min_size)


def make_cover(plan: dict, envelope: np.ndarray | None = None, size: int = 800) -> bytes:
    rng = np.random.default_rng(int(plan.get("seed", 0)) + 77)
    fam = plan.get("family", "house")
    pals = PALETTES.get(fam, PALETTES["house"])
    c1, c2, acc = [_hex(c) for c in pals[int(rng.integers(len(pals)))]]
    dh = rng.uniform(-0.03, 0.03)
    c1, c2, acc = _shift(c1, dh), _shift(c2, dh), _shift(acc, dh * 0.5)
    S = size
    # ---- gradient background (diagonal + radial glow)
    yy, xx = np.mgrid[0:S, 0:S] / S
    ang = rng.uniform(0, 2 * math.pi)
    t = np.clip(0.5 + ((xx - 0.5) * math.cos(ang) + (yy - 0.5) * math.sin(ang)) * 1.1, 0, 1)
    cx, cy = rng.uniform(0.3, 0.7), rng.uniform(0.3, 0.55)
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    glow = np.exp(-(r / 0.38) ** 2)[..., None]
    base = np.array(c1)[None, None, :] * (1 - t[..., None]) + np.array(c2)[None, None, :] * t[..., None]
    img_arr = base * (1 - 0.35 * glow) + np.array(acc)[None, None, :] * 0.35 * glow
    vign = 1 - 0.35 * np.clip((np.sqrt((xx - 0.5) ** 2 + (yy - 0.5) ** 2) - 0.3) / 0.45, 0, 1)
    img_arr = np.clip(img_arr * vign[..., None], 0, 255).astype(np.uint8)
    img = Image.fromarray(img_arr, "RGB").convert("RGBA")

    over = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    ccx, ccy = int(cx * S), int(cy * S)
    motif = int(rng.integers(3))
    # ---- geometric motif
    if motif == 0:  # concentric vinyl rings
        for i in range(14):
            rr = 60 + i * 22
            d.ellipse([ccx - rr, ccy - rr, ccx + rr, ccy + rr], outline=acc + (int(28 + 4 * (i % 3)),), width=2)
    elif motif == 1:  # radial rays
        for i in range(72):
            a = i / 72 * 2 * math.pi
            r0, r1 = 120, 120 + rng.uniform(60, 330)
            d.line([ccx + r0 * math.cos(a), ccy + r0 * math.sin(a), ccx + r1 * math.cos(a), ccy + r1 * math.sin(a)],
                   fill=acc + (40,), width=3)
    else:  # perspective grid
        hor = int(S * 0.62)
        for i in range(-12, 13):
            d.line([S / 2 + i * 18, hor, S / 2 + i * 160, S], fill=acc + (45,), width=2)
        for j in range(10):
            y = hor + (S - hor) * (j / 10) ** 1.8
            d.line([0, y, S, y], fill=acc + (40,), width=2)
    # ---- radial waveform from the track envelope
    env = np.asarray(envelope if envelope is not None and len(envelope) > 8 else rng.random(240) * 0.6 + 0.2)
    env = np.interp(np.linspace(0, len(env) - 1, 360), np.arange(len(env)), env)
    env = env / (env.max() + 1e-9)
    rad0 = 150
    pts_out, pts_in = [], []
    for i, e in enumerate(env):
        a = i / len(env) * 2 * math.pi - math.pi / 2
        ro = rad0 + 10 + 110 * e
        ri = rad0 - 4 - 30 * e
        pts_out.append((ccx + ro * math.cos(a), ccy + ro * math.sin(a)))
        pts_in.append((ccx + ri * math.cos(a), ccy + ri * math.sin(a)))
    glow_l = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_l)
    gd.polygon(pts_out, fill=acc + (90,))
    glow_l = glow_l.filter(ImageFilter.GaussianBlur(18))
    img = Image.alpha_composite(img, glow_l)
    d.polygon(pts_out, fill=acc + (200,))
    d.polygon(pts_in, fill=c1 + (255,))
    d.ellipse([ccx - rad0 + 30, ccy - rad0 + 30, ccx + rad0 - 30, ccy + rad0 - 30], outline=acc + (180,), width=3)
    d.ellipse([ccx - 8, ccy - 8, ccx + 8, ccy + 8], fill=acc + (230,))
    img = Image.alpha_composite(img, over)

    # ---- typography
    d = ImageDraw.Draw(img)
    pad = 48
    white = (255, 255, 255, 255)
    mark = _font(FONT_BOLD, 26)
    d.text((pad, pad), "D J   L A B", font=mark, fill=white)
    d.line([pad, pad + 38, pad + 90, pad + 38], fill=acc + (255,), width=4)
    genre_f = _font(FONT_REG, 24)
    gtxt = plan.get("genre", "").upper()
    d.text((S - pad - d.textlength(gtxt, font=genre_f), pad + 2), gtxt, font=genre_f, fill=(255, 255, 255, 220))

    title = plan.get("title", "")
    tf = _fit_font(d, title, FONT_BOLD, S - 2 * pad, 72)
    title_he = plan.get("title_he", "")
    hf = _fit_font(d, title_he, FONT_BOLD, S - 2 * pad, 50, direction="rtl")
    # dark band behind text for legibility
    band = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    bd.rectangle([0, S - 250, S, S], fill=(0, 0, 0, 120))
    band = band.filter(ImageFilter.GaussianBlur(24))
    img = Image.alpha_composite(img, band)
    d = ImageDraw.Draw(img)
    d.text((pad, S - 220), title, font=tf, fill=white)
    hw = d.textlength(title_he, font=hf, direction="rtl")
    d.text((S - pad - hw, S - 135), title_he, font=hf, fill=acc + (255,), direction="rtl")
    # badge
    badge = f"{int(round(float(plan.get('bpm', 0))))} BPM  ·  {plan.get('camelot', '')}"
    bf = _font(FONT_BOLD, 24)
    bw = d.textlength(badge, font=bf)
    bx, by = pad, S - 70
    d.rounded_rectangle([bx - 2, by - 8, bx + bw + 26, by + 34], radius=20, fill=acc + (255,))
    d.text((bx + 12, by - 1), badge, font=bf, fill=c1 + (255,) if sum(c1) < 300 else (20, 20, 20, 255))
    key = plan.get("key_short", "")
    kf = _font(FONT_REG, 22)
    d.text((bx + bw + 44, by), f"{key}  ·  Energy {plan.get('energy', '')}", font=kf, fill=(255, 255, 255, 230))

    rgb = img.convert("RGB")
    for q in (90, 85, 80, 72, 64, 55):
        buf = io.BytesIO()
        rgb.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() <= 200 * 1024:
            break
    return buf.getvalue()


def envelope_from_audio(audio: np.ndarray, points: int = 360) -> np.ndarray:
    m = np.abs(np.asarray(audio)).mean(axis=1) if np.asarray(audio).ndim == 2 else np.abs(audio)
    k = max(1, m.shape[0] // points)
    e = np.sqrt((m[: k * points].reshape(points, k) ** 2).mean(axis=1))
    return e
