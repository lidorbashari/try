import numpy as np, wave, json, sys
SR = 44100
def track(bpm, b0, d, dur, kick_every=1, seed=0, name="x"):
    rng = np.random.default_rng(seed); n = int(dur * SR); L = np.zeros(n); R = np.zeros(n); p = 60.0 / bpm
    t = np.arange(n) / SR
    # sustained chord pad (stereo-ish) + bass line on beats
    prog = [(110.0, (220.0, 277.2, 329.6)), (87.3, (174.6, 220.0, 261.6)), (130.8, (261.6, 329.6, 392.0)), (98.0, (196.0, 246.9, 293.7))]
    first_down = b0 + d * p
    bar = 4 * p
    for bi in range(-1, int(dur / bar) + 2):
        t0 = first_down + bi * bar; i0 = max(0, int(t0 * SR)); i1 = min(n, int((t0 + bar) * SR))
        if i1 <= i0: continue
        root, ch = prog[bi % 4]; tt = np.arange(i1 - i0) / SR
        env = np.minimum(1, tt * 40) * np.exp(-tt * 0.6)
        bass = 0.22 * np.sin(2*np.pi*root*tt) * env
        pad = 0.04 * sum(np.sin(2*np.pi*f*tt) for f in ch) * np.minimum(1, tt * 8)
        L[i0:i1] += bass + pad * 0.8; R[i0:i1] += bass + pad * 1.2
    k = 0
    while True:
        tb = b0 + k * p
        if tb >= dur - 0.3: break
        i0 = int(tb * SR); m = int(0.18 * SR); tt = np.arange(m) / SR
        if (k % kick_every) == 0 or ((k - d) % 4 == 0):
            f = 50 + 90 * np.exp(-tt * 30); kick = 0.8 * np.sin(2*np.pi*np.cumsum(f)/SR) * np.exp(-tt * 18)
            L[i0:i0+m] += kick[:len(L[i0:i0+m])]; R[i0:i0+m] += kick[:len(R[i0:i0+m])]
        if (k - d) % 4 in (1, 3):   # clap / snare on 2 and 4
            mm = int(0.12 * SR); nz = rng.standard_normal(mm) * np.exp(-np.arange(mm)/SR*30) * 0.35
            sp = np.fft.rfft(nz); fr = np.fft.rfftfreq(mm, 1/SR); sp[(fr < 900) | (fr > 4000)] = 0; nz = np.fft.irfft(sp, mm) * 3
            L[i0:i0+mm] += nz[:len(L[i0:i0+mm])]; R[i0:i0+mm] += nz[:len(R[i0:i0+mm])]
        # offbeat hats
        ih = int((tb + p/2) * SR); hm = int(0.04 * SR)
        if ih + hm < n:
            hz = rng.standard_normal(hm) * np.exp(-np.arange(hm)/SR*90) * 0.12
            hz = np.diff(np.concatenate([[0], hz]))
            L[ih:ih+hm] += hz * 0.7; R[ih:ih+hm] += hz * 1.3
        k += 1
    st = np.stack([L, R], 1); st /= max(1.0, np.abs(st).max() / 0.9)
    with wave.open(f"media/{name}.wav", "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((st * 32767).astype("<i2").tobytes())
    return {"bpm": bpm, "b0": b0, "d": d, "down": (b0 + d * p) % (4 * p), "p": p}
truth = {"x": track(124.0, 0.410, 0, 24, seed=1, name="x"),
         "y": track(126.0, 0.150, 2, 24, seed=2, name="y"),
         "z": track(92.0, 0.620, 1, 24, kick_every=2, seed=3, name="z"),
         "w": track(125.0, 0.300, 1, 30, seed=4, name="w"),
         "h": track(62.0, 0.500, 0, 30, seed=5, name="h")}
json.dump(truth, open("truth.json", "w"))
print(truth)
