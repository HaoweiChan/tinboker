# Original 15s music bed + SFX, pure stdlib (no numpy on this box). 120 BPM, beat = 0.5s.
# usage: python3 synth.py <out_dir>
import math, random, struct, sys, wave

SR = 44100
OUT = sys.argv[1]
random.seed(7)


def buf(sec):
    return [0.0] * int(sec * SR)


def add(dst, src, t, gain=1.0):
    o = int(t * SR)
    for i, v in enumerate(src):
        if 0 <= o + i < len(dst):
            dst[o + i] += v * gain


def svf(x, cutoff, q=0.7, mode="lp"):
    """Chamberlin state-variable filter; cutoff may be a function of sample index."""
    lp = bp = 0.0
    out = []
    for i, s in enumerate(x):
        fc = cutoff(i) if callable(cutoff) else cutoff
        f = 2 * math.sin(math.pi * min(fc, SR / 6) / SR)
        hp = s - lp - q * bp
        bp += f * hp
        lp += f * bp
        out.append(lp if mode == "lp" else bp if mode == "bp" else hp)
    return out


def noise(sec):
    return [random.uniform(-1, 1) for _ in range(int(sec * SR))]


def midi(n):
    return 440 * 2 ** ((n - 69) / 12)


def kick(dec=0.32, f0=150, f1=45):
    out, ph = [], 0.0
    for i in range(int(0.5 * SR)):
        t = i / SR
        ph += 2 * math.pi * (f1 + (f0 - f1) * math.exp(-t / 0.03)) / SR
        out.append(math.sin(ph) * math.exp(-t / dec) + (0.4 * math.exp(-t / 0.003) if i < 200 else 0))
    return out










def save(name, left, right=None, peak=0.89):
    right = right or left
    m = max(max(abs(v) for v in left), max(abs(v) for v in right)) or 1
    with wave.open(f"{OUT}/{name}.wav", "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<hh", int(a / m * peak * 32767), int(b / m * peak * 32767)) for a, b in zip(left, right)))


# ---------------- music: cinematic ----------------
# D minor, i–VI–III–VII. Strings pad + 16th ostinato + taiko on every scene cut,
# toms build 10–12.2s, 0.3s of silence, then a braam + D-major shimmer for the logo.
DUR = 15.0
strings, low, osti, drums, braam, shimmer = (buf(DUR) for _ in range(6))


def saw_n(freq, sec, detune=(0,)):
    """Naive detuned saw stack — aliasing is fine, everything gets low-passed."""
    n = int(sec * SR)
    out = [0.0] * n
    for d in detune:
        inc, ph = freq * 2 ** (d / 1200) / SR, random.random()
        for i in range(n):
            ph += inc
            if ph >= 1:
                ph -= 1
            out[i] += 2 * ph - 1
    return [v / len(detune) for v in out]


def boom(dec=0.7, f0=95, f1=38, thump=0.6):
    n, ph, out = int((dec * 5) * SR), 0.0, []
    th = svf(noise(0.2), 300)
    for i in range(n):
        t = i / SR
        ph += 2 * math.pi * (f1 + (f0 - f1) * math.exp(-t / 0.05)) / SR
        out.append(math.sin(ph) * math.exp(-t / dec) + (th[i] * thump * math.exp(-t / 0.05) if i < len(th) else 0))
    return out


# (start, end, chord tones for strings, low root, ostinato tones)
PROG = [(0, 4, [50, 53, 57], 38, [50, 57, 62, 57]),       # Dm
        (4, 5.5, [50, 53, 58], 34, [46, 53, 58, 53]),     # Bb
        (5.5, 7, [53, 57, 60], 41, [53, 60, 65, 60]),     # F
        (7, 8.5, [50, 53, 57], 38, [50, 57, 62, 57]),     # Dm
        (8.5, 10, [52, 55, 60], 36, [48, 55, 60, 55]),    # C
        (10, 11, [50, 53, 58], 34, [58, 65, 70, 65]),     # Bb (ostinato up an octave)
        (11, 12.2, [52, 55, 60], 36, [60, 67, 72, 67])]   # C
DET = (-14, -6, 0, 7, 15)
for a, b, tones, root, ost in PROG:
    rel = 0.6
    seg = b - a + rel
    att = 1.6 if a == 0 else 0.35
    env = lambda i: min(1, i / SR / att) * min(1, (seg - i / SR) / rel)
    for nt in tones + [tones[0] + 12]:
        add(strings, [v * env(i) for i, v in enumerate(saw_n(midi(nt), seg, DET))], a, 0.28)
    add(low, [v * env(i) for i, v in enumerate(saw_n(midi(root), seg, (-5, 5)))], a, 0.8)
    if a >= 2:  # ostinato: 8ths until 4s, then 16ths
        step = 0.25 if a < 4 else 0.125
        k, t = 0, max(a, 2.0)
        while t < b - 1e-6:
            note = saw_n(midi(ost[k % 4]), 0.16, (-6, 6))
            acc = 1.0 if k % 4 == 0 else 0.65
            add(osti, [v * math.exp(-i / SR / 0.06) * min(1, i / 100) * acc for i, v in enumerate(note)], t, 0.5)
            k, t = k + 1, t + step

BIG, TOM = boom(), boom(dec=0.22, f0=150, f1=85, thump=0.4)
for t, g in [(0, 1.0), (2.0, 0.6), (4.0, 0.9), (7.0, 0.9), (10.0, 1.0)]:
    add(drums, BIG, t, g)
for k in range(6):  # heartbeat toms under the stock scene
    add(drums, TOM, 7.5 + k * 0.5, 0.35)
t = 10.25
while t < 12.2 - 1e-6:  # build: 8ths then 16ths, crescendo
    add(drums, TOM, t, 0.3 + 0.6 * (t - 10) / 2.2)
    t += 0.25 if t < 11 else 0.125

# braam: detuned D power chord, filter blooms open then closes
bn = int(2.5 * SR)
br = [0.0] * bn
for nt in (38, 45, 50, 57):
    for i, v in enumerate(saw_n(midi(nt), 2.5, (-18, -9, -3, 0, 4, 10, 19))):
        br[i] += v
br = svf(br, lambda i: 180 + 2600 * min(1, i / (0.12 * SR)) * math.exp(-max(0, i / SR - 0.12) / 0.7), q=0.9)
braam_env = [math.tanh(1.8 * v) * min(1, i / (0.03 * SR)) * math.exp(-i / SR / 1.4) for i, v in enumerate(br)]
add(braam, braam_env, 12.5, 0.9)
add(drums, boom(dec=1.0, f0=80, f1=32, thump=0.9), 12.5, 1.1)
# shimmer: D major, high and soft, blooms under the logo text
sh = [0.0] * int(2.3 * SR)
for nt in (74, 78, 81, 86):
    f = midi(nt)
    for i in range(len(sh)):
        tt = i / SR
        sh[i] += (math.sin(2 * math.pi * f * tt) + 0.3 * math.sin(2 * math.pi * f * 2.003 * tt)) * min(1, tt / 0.9)
add(shimmer, sh, 12.7, 0.12)

strings = svf(strings, lambda i: 700 + 1500 * min(1, i / SR / 12), q=0.6)  # brightens as the piece builds
low = svf(low, 280, q=0.7)
osti = svf(osti, 2400, q=0.8)


def comb_reverb(x, off):
    """Schroeder: 4 damped combs + 2 allpasses."""
    out = [0.0] * len(x)
    for d in (1557, 1617, 1491, 1422):
        d += off
        cb, lp = [0.0] * len(x), 0.0
        for i in range(len(x)):
            y = cb[i - d] if i >= d else 0.0
            lp = y * 0.75 + lp * 0.25
            cb[i] = x[i] + lp * 0.84
            out[i] += y
    for d in (556 + off, 225):
        buf_ = [0.0] * len(x)
        for i in range(len(x)):
            prev = buf_[i - d] if i >= d else 0.0
            buf_[i] = out[i] + prev * 0.5
            out[i] = prev - out[i] * 0.5
    return [v * 0.25 for v in out]


dry = [strings[i] * 0.55 + low[i] * 0.5 + osti[i] * 0.45 + drums[i] + braam[i] + shimmer[i] for i in range(len(strings))]
send = [strings[i] * 0.5 + osti[i] * 0.6 + drums[i] * 0.25 + braam[i] * 0.5 + shimmer[i] for i in range(len(strings))]
wetL, wetR = comb_reverb(send, 0), comb_reverb(send, 23)


def gate(t):  # suck-back: everything drops out 12.2–12.5 before the braam
    if 12.05 <= t < 12.2:
        return (12.2 - t) / 0.15
    if 12.2 <= t < 12.5:
        return 0.0
    return min(1, max(0, (DUR - t) / 1.1))  # tail fade


L = [(dry[i] + wetL[i] * 0.9) * gate(i / SR) for i in range(len(dry))]
R = [(dry[i] + wetR[i] * 0.9) * gate(i / SR) for i in range(len(dry))]
save("music", L, R, peak=0.8)

# ---------------- sfx ----------------
def env_list(x, f):
    return [v * f(i / SR) for i, v in enumerate(x)]

w = svf(noise(0.5), lambda i: 400 + 5000 * math.sin(math.pi * i / (0.5 * SR)), q=0.35, mode="bp")
save("whoosh", env_list(w, lambda t: math.sin(math.pi * t / 0.5) ** 2))

pop = []
ph = 0.0
for i in range(int(0.12 * SR)):
    t = i / SR
    ph += 2 * math.pi * (380 + 700 * math.exp(-t / 0.015)) / SR
    pop.append(math.sin(ph) * math.exp(-t / 0.035))
save("pop", pop)

save("tick", [math.sin(2 * math.pi * 2600 * i / SR) * math.exp(-i / SR / 0.008) for i in range(int(0.04 * SR))])

imp = kick(dec=0.9, f0=110, f1=32) + [0.0] * int(1.0 * SR)
tail = svf(noise(1.5), 1800, mode="lp")
imp = [a + tail[i] * 0.5 * math.exp(-i / SR / 0.35) for i, a in enumerate(imp)]
save("impact", imp)

rs = svf(noise(2.0), lambda i: 200 + 7800 * (i / (2.0 * SR)) ** 2, q=0.4, mode="bp")
ph, tone = 0.0, []
for i in range(int(2.0 * SR)):
    ph += 2 * math.pi * (220 + 900 * (i / (2.0 * SR)) ** 2) / SR
    tone.append(math.sin(ph) * 0.25)
save("riser", [(a + b) * (i / (2.0 * SR)) ** 2 for i, (a, b) in enumerate(zip(rs, tone))])
print("ok")
