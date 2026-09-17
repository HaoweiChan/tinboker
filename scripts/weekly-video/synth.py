"""Synthesise the weekly-video BGM. stdlib only — no numpy, no samples, no licence.

120 BPM, 4/4, one bar = 2.0s. The video's scene lengths are whole bars (LEN in
weekly.html), so every crash lands exactly on a cut:

  bar 0        0- 2s   s1 title      pad + riser
  bars 1-3     2- 8s   s2 bars       kick/clap/hats enter
  bars 4-6     8-14s   s3 flips      chord turn + lead motif
  bars 7-8    14-18s   s4 sectors    four-on-the-floor peak
  bars 9-10   18-22s   s5 logo       one hit, then the tail
"""
import math, pathlib, random, struct, wave

SR, BAR, BEAT = 44100, 2.0, 0.5
DUR = 22.0
buf = [0.0] * int(SR * (DUR + 1.0))
random.seed(7)                      # same track every run

def add(t, samples, gain=1.0):
    i = int(t * SR)
    for k, v in enumerate(samples):
        if 0 <= i + k < len(buf):
            buf[i + k] += v * gain

def env(n, a, d, s=0.0, r=0.0):
    """attack/decay/sustain/release envelope over n samples, all in samples."""
    out = []
    for i in range(n):
        if i < a:            out.append(i / max(1, a))
        elif i < a + d:      out.append(1 - (1 - s) * (i - a) / max(1, d))
        elif i < n - r:      out.append(s)
        else:                out.append(s * max(0.0, (n - i) / max(1, r)))
    return out

def tone(f, dur, harm=(1.0, 0.5, 0.25), a=.01, d=.2, s=.7, r=.4):
    n = int(dur * SR)
    e = env(n, int(a * SR), int(d * SR), s, int(r * SR))
    out = [0.0] * n
    for h, amp in enumerate(harm, start=1):
        w = 2 * math.pi * f * h / SR
        for i in range(n):
            out[i] += amp * math.sin(w * i)
    m = sum(abs(x) for x in harm) or 1
    return [out[i] / m * e[i] for i in range(n)]

def kick(dur=.42):
    n = int(dur * SR); out = []
    ph = 0.0
    for i in range(n):
        k = i / n
        f = 45 + 95 * math.exp(-9 * k)              # pitch drop = the thump
        ph += 2 * math.pi * f / SR
        out.append(math.sin(ph) * math.exp(-7 * k))
    return out

def noise(dur, decay, tilt=0.0):
    """White noise with an exponential decay; tilt>0 leans bright (one-pole HP)."""
    n = int(dur * SR); out = []; prev = 0.0
    for i in range(n):
        x = random.uniform(-1, 1)
        if tilt:
            hp = x - prev; prev = x; x = hp * tilt + x * (1 - tilt)
        out.append(x * math.exp(-decay * i / n))
    return out

# ── arrangement ────────────────────────────────────────────────────────────
CH = {'Am': (220.00, 261.63, 329.63, 55.00),
      'F':  (174.61, 220.00, 261.63, 43.65),
      'C':  (261.63, 329.63, 392.00, 65.41),
      'G':  (196.00, 246.94, 293.66, 49.00)}
PROG = [('Am', 0, 2), ('Am', 2, 4), ('F', 4, 6), ('C', 6, 8),
        ('G', 8, 10), ('Am', 10, 12), ('F', 12, 14),
        ('C', 14, 16), ('G', 16, 18), ('Am', 18, 22)]

for name, t0, t1 in PROG:
    a, b, c, sub = CH[name]
    swell = 0.9 if t0 >= 14 else (0.75 if t0 >= 8 else 0.55)
    for f in (a, b, c):
        add(t0, tone(f, t1 - t0, (1.0, .45, .22, .10), a=.06, d=.35, s=.62, r=.55), .13 * swell)
    add(t0, tone(sub, t1 - t0, (1.0, .30), a=.02, d=.30, s=.75, r=.45), .30 * swell)

CUTS = [0.0, 2.0, 8.0, 14.0, 18.0]           # scene changes — the crashes

# The cut times live in weekly.html (LEN) and here. Two files, one timeline: check it,
# because a crash landing half a second off a cut is exactly what nobody notices in a diff.
def _check_against_video():
    import re, pathlib
    html = pathlib.Path(__file__).with_name('weekly.html').read_text()
    lens = [float(x) for x in re.search(r'const LEN=\[([0-9.,\s]+)\]', html).group(1).split(',')]
    starts, acc = [], 0.0
    for l in lens:
        starts.append(round(acc, 3)); acc += l
    assert starts == CUTS, f'video cuts {starts} != drum hits {CUTS}'
    assert round(acc, 3) == DUR, f'video is {acc}s, music is {DUR}s'
_check_against_video()
for t in CUTS:
    add(t, noise(1.8 if t < 18 else 3.2, 5.0, .55), .16)
    add(t, kick(.5), .55)

def drums(t0, t1, four_on_floor=False, hats=True):
    t = t0
    while t < t1 - 1e-6:
        beat = round((t - t0) / BEAT) % 4
        if four_on_floor or beat in (0, 2):
            add(t, kick(), .62)
        if beat in (1, 3):
            add(t, noise(.22, 9.0, .7), .30)      # clap
        if hats:
            add(t, noise(.05, 26.0, .95), .12)
            add(t + BEAT / 2, noise(.05, 26.0, .95), .07)
        t += BEAT

drums(2.0, 8.0)
drums(8.0, 14.0)
drums(14.0, 18.0, four_on_floor=True)

# riser into the first cut, and into the peak
for t0, t1 in ((0.9, 2.0), (12.9, 14.0)):
    n = int((t1 - t0) * SR)
    ph = 0.0; out = []
    for i in range(n):
        k = i / n
        ph += 2 * math.pi * (300 + 900 * k) / SR
        out.append((math.sin(ph) * .35 + random.uniform(-1, 1) * .65) * (k ** 2))
    add(t0, out, .22)

# lead motif — A minor pentatonic, doubled an octave up from bar 7
MOTIF = [(0.0, 659.25, 1.0), (1.0, 587.33, .5), (1.5, 523.25, 1.5),
         (3.0, 587.33, 1.0), (4.0, 440.00, 2.0)]
for base, gain in ((8.0, .10), (14.0, .13)):
    for dt, f, ln in MOTIF:
        if base + dt + ln > 18.0: ln = max(.4, 18.0 - base - dt)
        add(base + dt, tone(f, ln, (1.0, .0, .35, .0, .18), a=.02, d=.25, s=.55, r=.35), gain)
        if base >= 14:
            add(base + dt, tone(f * 2, ln, (1.0, .3), a=.02, d=.2, s=.4, r=.3), gain * .45)

# final hit + tail
add(18.0, tone(110.0, 4.0, (1.0, .5, .25), a=.005, d=.9, s=.35, r=2.0), .34)

# ── fades, soft clip, write ────────────────────────────────────────────────
for i in range(len(buf)):
    t = i / SR
    g = min(1.0, t / 0.35)                                  # fade in
    if t > DUR - 2.2: g *= max(0.0, (DUR - t) / 2.2)        # fade out on the logo card
    buf[i] *= g
peak = max(abs(x) for x in buf) or 1.0
buf = [math.tanh(x / peak * 1.25) * 0.89 for x in buf]      # soft clip, -1 dBFS-ish

import os
OUT_WAV = os.environ.get('BGM_WAV') or str(pathlib.Path(__file__).with_name('bgm.wav'))
with wave.open(OUT_WAV, 'w') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, x)) * 32767)) for x in buf))
print(f'{OUT_WAV}  {DUR}s  peak_before_clip={peak:.2f}')
