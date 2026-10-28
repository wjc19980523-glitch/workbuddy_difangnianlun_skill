"""Procedural score (frozen template; same for every city): pentatonic plucked strings
over a low drone, a woodblock tick for every node, cinematic pads, flight whooshes,
a soft low hit on arrival and a long hall reverb. Timing follows the node timeline.

usage: python3 -I src/audio.py segments.json out.wav
"""
import json, sys, wave
import numpy as np

SR = 48000
rng = np.random.default_rng(20261028)
segs = json.load(open(sys.argv[1]))['segments']
TOTAL = segs[-1]['t1']
N = int(TOTAL * SR) + SR
L = np.zeros(N); R = np.zeros(N)


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def add(sig, t, pan=0.0, gain=1.0):
    i = int(t * SR)
    if i >= N:
        return
    sig = sig[:N - i] * gain
    L[i:i + len(sig)] += sig * np.sqrt(0.5 * (1 - pan))
    R[i:i + len(sig)] += sig * np.sqrt(0.5 * (1 + pan))


def env_adsr(n, a, r, sus=1.0):
    e = np.ones(n) * sus
    na, nr = int(a * SR), int(r * SR)
    e[:na] = np.linspace(0, sus, na) if na else e[:na]
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr) ** 1.5
    return e


def pad_note(f, dur, bright=4.0, a=2.5, r=3.0):
    n = int(dur * SR); t = np.arange(n) / SR
    s = np.zeros(n)
    for det in (-0.0019, 0.0, 0.0023):
        ff = f * (1 + det)
        for k in range(1, 11):
            if ff * k > 6000:
                break
            s += np.sin(2 * np.pi * ff * k * t + rng.uniform(0, 6.28)) * (1 / k) * np.exp(-k / bright)
    lfo = 1 + 0.12 * np.sin(2 * np.pi * rng.uniform(0.05, 0.11) * t + rng.uniform(0, 6))
    return s * lfo * env_adsr(n, a, r) / 6


def pluck(f, dur=3.2, bend=True):
    """guzheng-like pluck: inharmonic decaying partials, small pitch press at the start"""
    n = int(dur * SR); t = np.arange(n) / SR
    pitch = f * (1 + (0.012 * np.exp(-t * 9) if bend else 0))
    ph = 2 * np.pi * np.cumsum(pitch) / SR
    s = np.zeros(n)
    for k in range(1, 9):
        inh = 1 + 0.0007 * k * k
        s += np.sin(ph * k * inh) * (0.9 ** k) / k * np.exp(-t * (1.1 + 0.55 * k))
    att = np.minimum(1, t / 0.004)
    noise = rng.standard_normal(n) * np.exp(-t * 60) * 0.08
    return (s * att + noise) * 0.55


def woodblock(gain=1.0):
    n = int(0.35 * SR); t = np.arange(n) / SR
    s = (np.sin(2 * np.pi * 820 * t) * 0.7 + np.sin(2 * np.pi * 1290 * t) * 0.35) * np.exp(-t * 38)
    return s * gain * 0.5


def whoosh(dur):
    n = int(dur * SR); t = np.arange(n) / SR
    x = rng.standard_normal(n)
    # moving one-pole low-pass: cutoff sweeps up then down
    cut = 300 + 2600 * np.sin(np.pi * t / dur) ** 2
    a = np.exp(-2 * np.pi * cut / SR)
    y = np.zeros(n); acc = 0.0
    for i in range(0, n, 64):          # block-wise coefficient update
        ai = a[i]
        seg = x[i:i + 64]
        out = np.empty_like(seg)
        for j, v in enumerate(seg):
            acc = ai * acc + (1 - ai) * v
            out[j] = acc
        y[i:i + 64] = out
    return y * np.sin(np.pi * t / dur) ** 2 * 0.22


def boom():
    n = int(3.0 * SR); t = np.arange(n) / SR
    f = 52 * (1 + 0.6 * np.exp(-t * 6))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.6)
    s += rng.standard_normal(n) * np.exp(-t * 18) * 0.05
    return s * 0.55


# ---------------------------------------------------------------- harmony
# D minor pentatonic world: D F G A C. One chord per section, slowly cycling.
CHORDS = [
    [38, 50, 57, 62, 65],   # Dm(add) — D2 D3 A3 D4 F4
    [34, 46, 53, 58, 62],   # Bb
    [41, 53, 57, 60, 65],   # F
    [36, 48, 55, 60, 64],   # C (E as colour)
    [43, 50, 55, 58, 62],   # Gm
]
PENTA = [62, 65, 67, 69, 72, 74, 77, 79, 81]

drone_t = np.arange(N) / SR
drone = (np.sin(2 * np.pi * midi(26) * drone_t) * 0.5 + np.sin(2 * np.pi * midi(33) * drone_t) * 0.25)
drone *= (0.55 + 0.45 * np.sin(2 * np.pi * drone_t / 23.0) ** 2)
fade_in = np.minimum(1, drone_t / 4.0)
fade_out = np.clip((TOTAL - drone_t) / 3.0, 0, 1)
drone *= fade_in * fade_out * 0.16
L += drone; R += drone

for si, s in enumerate(segs):
    t0, t1 = s['t0'], s['t1']
    dur = t1 - t0
    if s['kind'] == 'outro':
        ch = CHORDS[0]
    else:
        ch = CHORDS[si % len(CHORDS)]
    # pad: overlap into the next section for smooth changes
    for k, m in enumerate(ch):
        add(pad_note(midi(m), dur + 2.5, bright=3.0 + k * 0.6, a=1.8, r=2.6), max(0, t0 - 0.6),
            pan=(-0.5 + k * 0.25), gain=0.20 if k else 0.26)
    if s['kind'] == 'node':
        add(whoosh(3.0), t0 - 0.2, pan=0.0, gain=0.9)
        add(boom(), t0 + 2.6, gain=0.75)
        add(woodblock(), t0 + 1.0, pan=0.15, gain=0.55)
        # sparse melody phrase over the hold
        tt = t0 + 3.2
        last = rng.integers(2, 6)
        while tt < t1 - 1.2:
            last = int(np.clip(last + rng.choice([-2, -1, -1, 1, 1, 2]), 0, len(PENTA) - 1))
            add(pluck(midi(PENTA[last])), tt, pan=rng.uniform(-0.4, 0.4), gain=0.42)
            if rng.random() < 0.3:   # octave grace note
                add(pluck(midi(PENTA[last] - 12), 2.4, bend=False), tt + 0.12, pan=-0.2, gain=0.22)
            tt += rng.choice([1.1, 1.5, 1.9, 2.3])
    elif s['kind'] == 'intro':
        for k, (dt, m) in enumerate([(1.6, 62), (3.4, 69), (5.0, 67), (6.6, 74)]):
            add(pluck(midi(m), 4.0), t0 + dt, pan=(-0.3 + 0.2 * k), gain=0.45)
    else:
        add(whoosh(4.2), t0 - 0.2, gain=0.8)
        for k, (dt, m) in enumerate([(3.0, 74), (4.6, 69), (6.0, 65), (7.0, 62)]):
            add(pluck(midi(m), 4.5), t0 + dt, pan=(0.3 - 0.2 * k), gain=0.45)
        add(boom(), t0 + 3.0, gain=0.5)

# ---------------------------------------------------------------- hall reverb (FFT convolution)
irn = int(3.8 * SR); it = np.arange(irn) / SR
def ir():
    x = rng.standard_normal(irn) * np.exp(-it * 1.9)
    # darken the tail
    X = np.fft.rfft(x); fr = np.fft.rfftfreq(irn, 1 / SR)
    X *= 1 / (1 + (fr / 3500) ** 2)
    y = np.fft.irfft(X, irn); y[:int(0.012 * SR)] = 0
    return y / np.sqrt((y ** 2).sum())
def conv(x, h):
    n = 1 << int(np.ceil(np.log2(len(x) + len(h))))
    return np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(h, n), n)[:len(x)]
wetL, wetR = conv(L, ir()), conv(R, ir())
outL = L * 0.78 + wetL * 0.42
outR = R * 0.78 + wetR * 0.42
ln = int(TOTAL * SR)
out = np.stack([outL[:ln], outR[:ln]], 1)
out *= np.clip((TOTAL - np.arange(ln) / SR) / 1.5, 0, 1)[:, None]
out /= np.abs(out).max() * 1.12
with wave.open(sys.argv[2], 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((out * 32767).astype('<i2').tobytes())
print('wrote', sys.argv[2], TOTAL, 's')
