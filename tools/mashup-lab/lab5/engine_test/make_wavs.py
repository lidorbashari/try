"""Generate small test previews (16-bit mono WAV) for the engine tests."""
import os, sys, wave
import numpy as np

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wav")
SR = 44100


def tone(path, f0, secs, beat=True):
    t = np.arange(int(secs * SR)) / SR
    x = 0 * t if f0 == 0 else 0.18 * np.sin(2 * np.pi * f0 * t) + 0.1 * np.sin(2 * np.pi * f0 * 1.5 * t)
    if beat and f0:  # 120 BPM pulse so levels move
        env = np.exp(-((t * 2) % 1) * 6)
        x += 0.25 * np.sin(2 * np.pi * 60 * t) * env
    fade = np.minimum(1, np.minimum(t / 0.01, (secs - t) / 0.01))
    x = (x * fade).clip(-1, 1)
    tmp = path + ".tmp"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    os.replace(tmp, path)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    tone(os.path.join(OUT, "a.wav"), 330, 8)
    tone(os.path.join(OUT, "b.wav"), 220, 8)
    tone(os.path.join(OUT, "c.wav"), 262, 8)
    tone(os.path.join(OUT, "sa.wav"), 440, 1.6)
    tone(os.path.join(OUT, "sb.wav"), 294, 1.6)
    tone(os.path.join(OUT, "silent.wav"), 0, 8)  # digital silence: drives the CORS silence watchdog
    art = os.path.join(os.path.dirname(OUT), "art")
    os.makedirs(art, exist_ok=True)
    png = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c4944415408d763f8cfc0f01f0005000201e2a6c4d40000000049454e44ae426082")
    for n in ("100x100bb.png", "600x600bb.png"):
        open(os.path.join(art, n), "wb").write(png)
    print("ok", sorted(os.listdir(OUT)))
