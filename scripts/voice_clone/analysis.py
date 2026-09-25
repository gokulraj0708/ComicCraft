"""Shared analysis helpers: wav IO, STFT, F0 tracking, spectral envelopes."""
import numpy as np
import wave


def read_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        raw = w.readframes(n)
    dt = {1: np.int8, 2: np.int16, 4: np.int32}[sw]
    x = np.frombuffer(raw, dtype=dt).astype(np.float64)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x / float(2 ** (8 * sw - 1)), sr


def write_wav(path, x, sr, subtype_bits=16):
    x = np.clip(x, -1.0, 1.0)
    xi = (x * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(xi.tobytes())


def hann(n):
    return 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)


def stft(x, sr, win_ms=32.0, hop_ms=8.0, n_fft=1024, center=True):
    win = int(round(win_ms * sr / 1000.0))
    hop = int(round(hop_ms * sr / 1000.0))
    w = hann(win)
    if center:
        x = np.pad(x, (win // 2, win // 2))
    n_fr = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n_fr)[:, None]
    frames = (x[idx] * w[None, :]).astype(np.float32)
    X = np.fft.rfft(frames, n=n_fft, axis=1)
    return X, hop, win


def istft(X, hop, win, sr, length=None, center=True):
    n_fft = (X.shape[1] - 1) * 2
    w = hann(win)
    frames = (np.fft.irfft(X, n=n_fft, axis=1)[:, :win] * w[None, :]).astype(np.float32)
    if length is None:
        length = hop * (X.shape[0] - 1) + win - 2 * (win // 2)
    off = win // 2 if center else 0
    total = off + length + win
    needed = (X.shape[0] - 1) * hop + win + 1
    total = max(total, needed)
    y = np.zeros(total, dtype=np.float64)
    nrm = np.zeros(total, dtype=np.float64)
    for i in range(X.shape[0]):
        st = i * hop
        y[st:st + win] += frames[i]
        nrm[st:st + win] += w ** 2
    nrm[nrm < 1e-8] = 1.0
    y = (y / nrm)[off:off + length]
    return y


def f0_track(x, sr, win_ms=40.0, hop_ms=10.0, fmin=60.0, fmax=400.0,
             voicing_thresh=0.35, smooth_ms=40.0):
    """Autocorrelation F0 tracker with parabolic interpolation + median smoothing."""
    win = int(round(win_ms * sr / 1000.0))
    hop = int(round(hop_ms * sr / 1000.0))
    n_fr = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n_fr)[:, None]
    frames = x[idx] * hann(win)[None, :]
    # remove DC and pre-emphasise
    frames = frames - frames.mean(axis=1, keepdims=True)
    n_fft = 1 << int(np.ceil(np.log2(2 * win)))
    spec = np.fft.rfft(frames, n=n_fft * 2, axis=1)
    acf = np.fft.irfft(np.abs(spec) ** 2, axis=1)[:, :int(n_fft)]
    acf0 = acf[:, 0].copy()
    acf0[acf0 <= 0] = 1e-12
    nacf = acf / acf0[:, None]
    lo = int(np.ceil(sr / fmax))
    hi = int(np.floor(sr / fmin))
    hi = min(hi, nacf.shape[1] - 2)
    seg = nacf[:, lo:hi + 1]
    peak_i = np.argmax(seg, axis=1) + lo
    peak_v = nacf[np.arange(n_fr), peak_i]
    # parabolic interpolation
    ip = peak_i
    ym1 = nacf[np.arange(n_fr), np.clip(ip - 1, 0, nacf.shape[1] - 1)]
    yp1 = nacf[np.arange(n_fr), np.clip(ip + 1, 0, nacf.shape[1] - 1)]
    denom = (ym1 - 2 * peak_v + yp1)
    denom[np.abs(denom) < 1e-12] = 1e-12
    delta = 0.5 * (ym1 - yp1) / denom
    delta = np.clip(delta, -1, 1)
    period = (peak_i + delta) / float(sr)
    f0 = np.where(period > 0, 1.0 / np.maximum(period, 1e-9), 0.0)
    voiced = (peak_v > voicing_thresh) & (f0 >= fmin) & (f0 <= fmax)
    f0[~voiced] = 0.0
    # median smooth
    k = max(1, int(round(smooth_ms / hop_ms)) // 2 * 2 + 1)
    if k > 1:
        pad = k // 2
        fp = np.pad(f0, pad, mode="edge")
        stacked = np.stack([fp[i:i + n_fr] for i in range(k)], axis=0)
        f0 = np.median(stacked, axis=0)
        vp = np.pad(voiced.astype(np.float64), pad, mode="edge")
        stacked_v = np.stack([vp[i:i + n_fr] for i in range(k)], axis=0)
        voiced = np.median(stacked_v, axis=0) > 0.5
    f0[~voiced] = 0.0
    return f0, voiced, hop, win


def cepstral_envelope(X, n_ceps=40, floor_db=-90.0):
    """Smooth log-magnitude envelope of an STFT via cepstral liftering.

    Returns log-envelope (natural log of magnitude) with n_fft/2+1 bins.
    """
    mag = np.maximum(np.abs(X), 1e-10)
    logmag = np.log(mag)
    n_fft = (X.shape[1] - 1) * 2
    cep = np.fft.irfft(logmag, n=n_fft, axis=1)
    cep[:, 1:n_ceps] *= 2.0
    cep[:, n_ceps:] = 0.0
    env = np.fft.rfft(cep, n=n_fft, axis=1).real
    return env  # log magnitude envelope


def mcep(X, n_ceps=40, n_mels=40, sr=16000, n_fft=1024):
    """Mel-cepstral coefficients from an STFT (log-mel -> DCT)."""
    from scipy.fftpack import dct
    power = np.maximum(np.abs(X) ** 2, 1e-12)
    n_mels_n = n_mels
    mel_fb = mel_filterbank(sr, n_fft, n_mels_n)
    mel = np.log(np.maximum(power @ mel_fb.T, 1e-10))
    c = dct(mel, type=2, axis=1, norm="ortho")[:, :n_ceps]
    return c


_FB_CACHE = {}


def mel_filterbank(sr, n_fft, n_mels, fmin=40.0, fmax=None):
    key = (sr, n_fft, n_mels, fmin, fmax)
    if key in _FB_CACHE:
        return _FB_CACHE[key]
    if fmax is None:
        fmax = sr / 2.0
    def hz2mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)
    def mel2hz(m):
        return 700.0 * (10 ** (m / 2595.0) - 1.0)
    pts = mel2hz(np.linspace(hz2mel(fmin), hz2mel(fmax), n_mels + 2))
    bins = np.floor((n_fft + 1) * pts / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for i in range(n_mels):
        l, c, r = bins[i], bins[i + 1], bins[i + 2]
        if c == l:
            c = l + 1
        if r == c:
            r = c + 1
        r = min(r, n_fft // 2 + 1)
        fb[i, l:c] = (np.arange(l, c) - l) / float(c - l)
        fb[i, c:r] = (r - np.arange(c, r)) / float(r - c)
    # rows sum to one: a mel value is then the mean power *per bin* of the
    # band, so expanding back to the linear grid carries no band-width bias
    fb = fb / np.maximum(fb.sum(axis=1, keepdims=True), 1e-12)
    _FB_CACHE[key] = fb
    return fb


def f0_yin(x, sr, win_ms=50.0, hop_ms=10.0, fmin=60.0, fmax=400.0,
           threshold=0.12, voiced_thresh=0.35):
    """YIN pitch estimator (vectorised over frames).

    Returns (f0, voiced, hop, win); f0 is 0 in unvoiced frames.
    """
    win = int(round(win_ms * sr / 1000.0))
    hop = int(round(hop_ms * sr / 1000.0))
    n_fr = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n_fr)[:, None]
    frames = x[idx].astype(np.float64)
    frames -= frames.mean(axis=1, keepdims=True)

    tmax = min(int(np.ceil(sr / fmin)) + 2, win // 2)
    tmin = max(2, int(np.floor(sr / fmax)))

    n_fft = 1 << int(np.ceil(np.log2(win + tmax + 1)))
    F = np.fft.rfft(frames, n=n_fft, axis=1)
    acf = np.fft.irfft(np.abs(F) ** 2, n=n_fft, axis=1)[:, :tmax + 1]

    x2 = np.concatenate([np.zeros((n_fr, 1)), np.cumsum(frames ** 2, axis=1)], axis=1)
    tau = np.arange(tmax + 1)
    p1 = x2[:, win - tau]                      # sum x[j]^2, j < win-tau
    p2 = x2[:, win][:, None] - x2[:, tau]      # sum x[j+tau]^2
    d = p1 + p2 - 2.0 * acf
    d[:, 0] = 0.0

    # cumulative mean normalised difference function
    cd = np.concatenate([np.zeros((n_fr, 1)), np.cumsum(d[:, 1:], axis=1)], axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = d * tau[None, :] / np.maximum(cd, 1e-12)
    dd[:, 0] = 1.0
    dd = np.nan_to_num(dd, nan=1.0, posinf=1.0)

    # first dip below the threshold (with a local-minimum check), else global min
    rng = dd[:, tmin:tmax + 1]
    below = rng < threshold
    # local minimum test: dd[t] <= dd[t+1]
    loc = np.zeros_like(below)
    loc[:, :-1] = rng[:, :-1] <= rng[:, 1:]
    loc[:, -1] = True
    ok = below & loc
    any_ok = ok.any(axis=1)
    first = np.argmax(ok, axis=1)
    gmin = np.argmin(rng, axis=1)
    tau_idx = np.where(any_ok, first, gmin) + tmin
    minval = rng[np.arange(n_fr), tau_idx - tmin]

    # parabolic interpolation
    tm = np.clip(tau_idx, 1, tmax - 1)
    y0 = dd[np.arange(n_fr), tm - 1]
    y1 = dd[np.arange(n_fr), tm]
    y2 = dd[np.arange(n_fr), tm + 1]
    denom = (y0 - 2 * y1 + y2)
    denom[np.abs(denom) < 1e-12] = 1e-12
    shift = 0.5 * (y0 - y2) / denom
    period = (tm + np.clip(shift, -1, 1)) / float(sr)
    f0 = np.where(period > 0, 1.0 / np.maximum(period, 1e-9), 0.0)
    voiced = (minval < voiced_thresh) & (f0 >= fmin) & (f0 <= fmax)
    f0[~voiced] = 0.0
    return f0, voiced, hop, win
