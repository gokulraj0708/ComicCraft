"""Convert the narration of the ComicCraft videos into the reference voice.

Reads a source narration WAV, converts it to the speaker of a reference
recording (voice conversion: the content, wording and timing are preserved,
only the voice changes) and writes the result back to WAV.

Usage:
    python convert_video_audio.py SOURCE.wav REFERENCE.wav OUT.wav
"""
import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analysis import read_wav, write_wav, f0_track  # noqa: E402
import vc                                          # noqa: E402

CHUNK_S = 25.0
XFADE_S = 0.5


def f0_stats_long(x, sr, chunk_s=30.0):
    """Log-F0 mean/sd of the whole utterance, measured chunk-wise (memory)."""
    vals = []
    chunk = int(chunk_s * sr)
    for st in range(0, len(x), chunk):
        f0, v, _, _ = f0_track(x[st:st + chunk], sr, win_ms=40.0, hop_ms=10.0,
                               fmin=vc.FMIN, fmax=vc.FMAX)
        vals.append(np.log(f0[(f0 > 0) & v]))
    lf = np.concatenate([v for v in vals if len(v)]) if vals else np.array([0.0])
    return float(lf.mean()), float(lf.std())


def convert_long(x, tgt, sr, chunk_s=CHUNK_S, xfade_s=XFADE_S, log=print):
    n = len(x)
    stats = f0_stats_long(x, sr)
    log("  source log-F0: mean %.1f Hz, spread %.2f semitones"
        % (np.exp(stats[0]), stats[1] * 12 / np.log(2)))
    chunk = int(chunk_s * sr)
    xf = int(xfade_s * sr)
    out = np.zeros(n)
    wsum = np.zeros(n)
    starts = list(range(0, max(1, n - chunk + 1), chunk - xf))
    if starts[-1] + chunk < n:
        starts.append(n - chunk)
    for i, st in enumerate(starts):
        seg = x[st:st + chunk]
        t0 = time.time()
        y, info = vc.convert(seg, tgt, sr=sr, f0_stats=stats)
        w = np.ones(len(y))
        if i > 0:
            w[:xf] = np.linspace(0.0, 1.0, xf)
        if st + chunk < n:
            w[-xf:] = np.linspace(1.0, 0.0, xf)
        out[st:st + len(y)] += y * w
        wsum[st:st + len(y)] += w
        log("  chunk %2d/%d  %6.2f-%6.2fs  beta=%.3f  (%.1fs)"
            % (i + 1, len(starts), st / sr, (st + len(seg)) / sr,
               info["beta"], time.time() - t0))
    wsum[wsum < 1e-6] = 1.0
    out = out / wsum
    # keep the original overall loudness
    out *= np.sqrt(np.mean(x ** 2) + 1e-12) / (np.sqrt(np.mean(out ** 2) + 1e-12))
    return vc.soft_limit(out[:n])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("reference")
    ap.add_argument("out")
    ap.add_argument("--knn", type=float, default=vc.KNN_BLEND)
    ap.add_argument("--dyn", type=float, default=0.8)
    args = ap.parse_args()

    ref, sr_ref = read_wav(args.reference)
    src, sr = read_wav(args.source)
    if sr_ref != sr:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(sr_ref, sr)
        ref = resample_poly(ref, sr // g, sr_ref // g)
    print("source    : %.1fs @ %d Hz" % (len(src) / sr, sr))
    print("reference : %.1fs" % (len(ref) / sr))

    tgt, _ = vc.build_target(ref, sr)
    print("target F0 : median %.1f Hz, mean %.1f Hz, spread %.2f semitones"
          % (tgt["f0_med"], np.exp(tgt["f0_mean"]),
             tgt["f0_sd"] * 12 / np.log(2)))

    y = convert_long(src, tgt, sr, log=print)
    assert len(y) == len(src), (len(y), len(src))
    write_wav(args.out, y, sr)
    print("wrote %s (%.1fs)" % (args.out, len(y) / sr))


if __name__ == "__main__":
    main()
