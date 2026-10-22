"""synthetic previews with drums on a known grid + sung 'words' (harmonic tone bursts) at known times"""
import numpy as np, wave, json, os
SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))
def track(bpm, b0, d, dur, words, f0, seed=0, name="x"):
    rng = np.random.default_rng(seed); n = int(dur * SR); L = np.zeros(n); R = np.zeros(n); p = 60.0 / bpm
    prog = [(110.0, (220.0, 277.2, 329.6)), (87.3, (174.6, 220.0, 261.6)), (130.8, (261.6, 329.6, 392.0)), (98.0, (196.0, 246.9, 293.7))]
    first_down = b0 + d * p; bar = 4 * p
    for bi in range(-1, int(dur / bar) + 2):
        t0 = first_down + bi * bar; i0 = max(0, int(t0 * SR)); i1 = min(n, int((t0 + bar) * SR))
        if i1 <= i0: continue
        root, ch = prog[bi % 4]; tt = np.arange(i1 - i0) / SR
        env = np.minimum(1, tt * 40) * np.exp(-tt * 0.6)
        L[i0:i1] += 0.2 * np.sin(2*np.pi*root*tt) * env + 0.03 * sum(np.sin(2*np.pi*f*tt) for f in ch) * np.minimum(1, tt * 8)
        R[i0:i1] += 0.2 * np.sin(2*np.pi*root*tt) * env + 0.036 * sum(np.sin(2*np.pi*f*tt) for f in ch) * np.minimum(1, tt * 8)
    k = 0
    while True:
        tb = b0 + k * p
        if tb >= dur - 0.3: break
        i0 = int(tb * SR); m = int(0.18 * SR); tt = np.arange(m) / SR
        f = 50 + 90 * np.exp(-tt * 30); kick = 0.7 * np.sin(2*np.pi*np.cumsum(f)/SR) * np.exp(-tt * 18)
        L[i0:i0+m] += kick[:len(L[i0:i0+m])]; R[i0:i0+m] += kick[:len(R[i0:i0+m])]
        if (k - d) % 4 in (1, 3):
            mm = int(0.12 * SR); nz = rng.standard_normal(mm) * np.exp(-np.arange(mm)/SR*30) * 0.3
            sp = np.fft.rfft(nz); fr = np.fft.rfftfreq(mm, 1/SR); sp[(fr < 900) | (fr > 4000)] = 0; nz = np.fft.irfft(sp, mm) * 3
            L[i0:i0+mm] += nz[:len(L[i0:i0+mm])]; R[i0:i0+mm] += nz[:len(R[i0:i0+mm])]
        ih = int((tb + p/2) * SR); hm = int(0.04 * SR)
        if ih + hm < n:
            hz = np.diff(np.concatenate([[0], rng.standard_normal(hm) * np.exp(-np.arange(hm)/SR*90) * 0.1]))
            L[ih:ih+hm] += hz * 0.7; R[ih:ih+hm] += hz * 1.3
        k += 1
    for (ws, we) in words:   # a sung word: harmonics of f0 with a soft attack, centred (mono)
        i0, i1 = int(ws * SR), int(we * SR); tt = np.arange(i1 - i0) / SR
        env = np.minimum(1, tt / 0.015) * np.minimum(1, (we - ws - tt) / 0.02)
        v = sum(a * np.sin(2*np.pi*f0*h*tt) for h, a in ((1, .25), (2, .12), (3, .06))) * env
        L[i0:i1] += v; R[i0:i1] += v
    st = np.stack([L, R], 1); st /= max(1.0, np.abs(st).max() / 0.9)
    with wave.open(os.path.join(HERE, "media", name + ".wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((st * 32767).astype("<i2").tobytes())
    return {"bpm": bpm, "b0": b0, "d": d, "p": p, "words": words, "f0": f0}
truth = {"wa": track(124.0, 0.410, 0, 30, [(10.25, 10.82), (20.30, 20.90)], 600.0, seed=1, name="wa"),
         "wb": track(126.0, 0.150, 2, 30, [(8.00, 8.60), (17.10, 17.60)], 900.0, seed=2, name="wb"),
         "wc": track(92.0, 0.620, 1, 30, [(9.60, 10.10)], 750.0, seed=3, name="wc")}
json.dump(truth, open(os.path.join(HERE, "truth.json"), "w"))
print(json.dumps(truth))
