"""Train-free zero-shot voice conversion.

Pipeline
--------
1.  Analysis     : STFT -> harmonic-free cepstral envelope + whitened
                   residual (excitation), autocorrelation F0 contour.
2.  Target model : statistics of the reference speaker (mean / covariance of
                   the cepstral shape, log-F0 mean & sd) plus a kNN codebook
                   of that speaker's envelopes for phonetic conditioning.
3.  Envelope map : CORAL (mean + covariance) alignment of the source cepstra
                   into the target space, refined by kNN, with a
                   global-variance post-filter.  The frame energy (c0) always
                   stays the source's, so pauses stay pauses.
4.  Excitation   : the residual is rebuilt period by period on the target F0
                   contour (pitch-synchronous resynthesis, duration kept).
5.  Resynthesis  : converted envelope x converted excitation -> ISTFT.

Everything is estimated from the two signals themselves, so this runs offline
with no pretrained network.
"""
import numpy as np
from scipy.fftpack import dct, idct
from scipy.spatial import cKDTree
from scipy.signal import resample_poly, butter, sosfilt

from analysis import read_wav, write_wav, hann, stft, istft, f0_track

# ----------------------------------------------------------------------------
# configuration
# ----------------------------------------------------------------------------
SR = 16000
N_FFT = 1024
WIN_MS = 32.0
HOP_MS = 8.0
N_CEPS = 40           # cepstral order of the converted envelope (~200 Hz)
WHITEN_FLOOR = 10 ** (-40.0 / 20.0)   # -40 dB w.r.t. the frame mean magnitude
FMIN, FMAX = 60.0, 340.0
KNN_K = 32
KNN_BLEND = 0.50      # 0 = pure CORAL, 1 = pure kNN
GV_RANGE = (0.5, 2.0)
UNVOICED_MIX = 0.60   # how much of the target shape unvoiced frames receive
LTAS_MATCH = False    # measured to hurt, see the note in convert()


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def cepsmooth(log_env, n_ceps, n_fft=N_FFT):
    """Lifter a linear-frequency log-magnitude envelope to `n_ceps` cepstra.

    Accepts either a single spectrum (1-D) or a stack of frames (2-D).
    """
    flat = log_env.ndim == 1
    if flat:
        log_env = log_env[None, :]
    cep = np.fft.irfft(log_env, n=n_fft, axis=1)
    out = np.zeros_like(cep)
    out[:, 0] = cep[:, 0]
    out[:, 1:n_ceps] = 2.0 * cep[:, 1:n_ceps]
    env = np.fft.rfft(out, n=n_fft, axis=1).real
    return env[0] if flat else env


def cep_to_env(c0, shape, n_fft=N_FFT):
    """Inverse of `cepsmooth`: cepstral coefficients -> log-magnitude envelope."""
    T, n = shape.shape[0], shape.shape[1] + 1
    out = np.zeros((T, n_fft))
    out[:, 0] = c0
    out[:, 1:n] = 2.0 * shape
    return np.fft.rfft(out, n=n_fft, axis=1).real


def highpass(x, sr, fc=65.0, order=4):
    sos = butter(order, fc / (sr / 2.0), btype="highpass", output="sos")
    return sosfilt(sos, x)


def _movavg(a, k):
    if k <= 1:
        return a
    ker = np.ones(k) / k
    ap = np.pad(a, ((k // 2, k // 2), (0, 0)), mode="edge")
    return np.apply_along_axis(lambda m: np.convolve(m, ker, "valid"), 0, ap)[:a.shape[0]]


def _median_smooth(a, k):
    if k <= 1:
        return a
    pad = k // 2
    ap = np.pad(a, ((pad, pad), (0, 0)), mode="edge")
    return np.median(np.stack([ap[i:i + a.shape[0]] for i in range(k)], 0), 0)


def spectral_gate(x, sr, win_ms=32.0, hop_ms=8.0, n_fft=1024, percentile=15,
                  over_subtract=1.3, floor=0.05, smooth_ceps=32):
    """Stationary-noise spectral subtraction."""
    X, hop, win = stft(x, sr, win_ms=win_ms, hop_ms=hop_ms, n_fft=n_fft)
    mag = np.abs(X)
    logp = np.log(np.maximum(mag ** 2, 1e-12))
    noise = np.exp(np.percentile(logp, percentile, axis=0)) ** 0.5
    gain = 1.0 - over_subtract * (noise / np.maximum(mag, 1e-12))
    gain = np.clip(gain, floor, 1.0)
    gain_s = np.exp(cepsmooth(np.log(np.maximum(gain, 1e-6)), smooth_ceps, n_fft))
    Y = X * np.clip(gain_s, 0.0, 1.0)
    return istft(Y, hop, win, sr, length=len(x))


def soft_limit(y, thresh=0.5, ceil=0.99):
    """Gentle tanh limiter: tames isolated bursts without pumping."""
    a = np.abs(y)
    m = a > thresh
    if not m.any():
        return y
    out = y.copy()
    k = (ceil - thresh) / np.tanh(3.0)
    out[m] = np.sign(y[m]) * (thresh + k * np.tanh((a[m] - thresh) / k))
    return out


# ----------------------------------------------------------------------------
# analysis
# ----------------------------------------------------------------------------
def analyze(x, sr=SR):
    X, hop, win = stft(x, sr, win_ms=WIN_MS, hop_ms=HOP_MS, n_fft=N_FFT)
    logmag = np.log(np.maximum(np.abs(X).astype(np.float32), 1e-10))
    cep = np.fft.irfft(logmag, n=N_FFT, axis=1).astype(np.float32)
    c0 = cep[:, 0].astype(np.float64)
    shape = cep[:, 1:N_CEPS].astype(np.float64)
    del logmag

    env = cepsmooth(np.log(np.maximum(np.abs(X).astype(np.float32), 1e-10)),
                    N_CEPS).astype(np.float32)
    env_mag = np.exp(env)
    env_mag = np.maximum(env_mag, WHITEN_FLOOR * env_mag.mean(axis=1, keepdims=True))
    R = X / env_mag
    del env, env_mag, cep

    f0, voiced, fhop, fwin = f0_track(x, sr, win_ms=40.0, hop_ms=10.0,
                                      fmin=FMIN, fmax=FMAX)
    t_stft = (np.arange(X.shape[0]) * hop + win / 2.0) / sr
    t_f0 = (np.arange(len(f0)) * fhop + fwin / 2.0) / sr
    f0_s = np.interp(t_stft, t_f0, f0)
    voiced_s = np.interp(t_stft, t_f0, voiced.astype(float)) > 0.5

    return dict(X=X, R=R, hop=hop, win=win, c0=c0, shape=shape,
                f0=f0_s, voiced=voiced_s,
                t=t_stft, f0_t=t_f0, f0_raw=f0, voiced_raw=voiced)


# ----------------------------------------------------------------------------
# reference speaker model
# ----------------------------------------------------------------------------
def make_features(shape, w_delta=0.7):
    d1 = np.vstack([np.zeros((1, shape.shape[1])), np.diff(shape, axis=0)])
    d2 = np.vstack([np.zeros((1, shape.shape[1])), np.diff(d1, axis=0)])
    return np.concatenate([shape, w_delta * d1, 0.4 * w_delta * d2], axis=1)


def build_target(ref_x, sr=SR, denoise=True):
    if denoise:
        ref_x = spectral_gate(ref_x, sr)
        ref_x = highpass(ref_x, sr, 70.0)
    ref_ltas = ltas(ref_x, sr)
    a = analyze(ref_x, sr)
    lvl = a["c0"]
    v = lvl > np.percentile(lvl, 25)          # every audible frame, voiced or not
    c = a["shape"]
    cv = c[v] if v.sum() > 50 else c
    mean = cv.mean(axis=0)
    cov = np.cov(cv.T) + 1e-4 * np.eye(c.shape[1])
    lf = np.log(a["f0"][a["voiced"] & (a["f0"] > 0)])
    feat = make_features(c)
    mu, sd = feat.mean(axis=0), feat.std(axis=0) + 1e-8
    return dict(mean=mean, cov=cov, f0_mean=float(lf.mean()),
                f0_sd=float(lf.std()), f0_med=float(np.exp(np.median(lf))),
                tree=cKDTree((feat - mu) / sd), shape=c, mu=mu, sd=sd,
                voiced=v, n_frames=len(c), ltas=ref_ltas), a


# ----------------------------------------------------------------------------
# envelope conversion
# ----------------------------------------------------------------------------
def _sqrtm(cov):
    w, V = np.linalg.eigh(cov)
    w = np.maximum(w, 1e-8)
    return V @ np.diag(1.0 / np.sqrt(w)) @ V.T, V @ np.diag(np.sqrt(w)) @ V.T


def convert_ceps(c0, shape, audible, tgt, blend=KNN_BLEND, k=KNN_K,
                 max_sd=4.0, voiced=None, unvoiced_mix=UNVOICED_MIX):
    """Map the spectral shape into the target speaker's space (energy kept).

    `audible` marks the frames used to fit the source statistics; it must be
    the same criterion the target model was fitted with, otherwise unvoiced
    frames fall outside the fitted distribution and CORAL extrapolates.
    """
    d = shape.shape[1]
    cv = shape[audible] if audible.sum() > 50 else shape
    s_mean = cv.mean(axis=0)
    s_cov = np.cov(cv.T) + 1e-4 * np.eye(d)
    s_inv_sqrt, s_sqrt = _sqrtm(s_cov)
    _, t_sqrt = _sqrtm(tgt["cov"])
    coral = (shape - s_mean) @ s_inv_sqrt @ t_sqrt + tgt["mean"]

    if blend > 0:
        feat = make_features(shape)
        featn = (feat - feat.mean(axis=0)) / (feat.std(axis=0) + 1e-8)
        dist, idx = tgt["tree"].query(featn, k=k, workers=2)
        w = 1.0 / (dist + 1e-3)
        w **= 2
        w /= w.sum(axis=1, keepdims=True)
        knn = (tgt["shape"][idx] * w[:, :, None]).sum(axis=1)
        knn = _movavg(_median_smooth(knn, 5), 5)
        out = (1 - blend) * coral + blend * knn
    else:
        out = coral

    # global-variance postfilter measured on the audible frames
    if audible.sum() > 50:
        m = out[audible].mean(axis=0)
        oc = out - m
        gv_out = oc[audible].std(axis=0) + 1e-8
    else:
        m = out.mean(axis=0)
        oc = out - m
        gv_out = oc.std(axis=0) + 1e-8
    gv_t = np.sqrt(np.diag(tgt["cov"])) + 1e-8
    # hard guard: never leave the target's own envelope range by more than
    # `max_sd` standard deviations - this bounds any residual extrapolation
    oc = np.clip(oc, -max_sd * gv_t, max_sd * gv_t)
    out = tgt["mean"] + oc * np.clip(gv_t / gv_out, *GV_RANGE)
    # Unvoiced frames carry the consonant identity (plosive bursts, fricative
    # noise) and almost none of the speaker identity, so they are only partly
    # converted - otherwise "TestAPI" turns into "BestAPI".
    if voiced is not None and unvoiced_mix < 1.0:
        uv = ~voiced
        out[uv] = unvoiced_mix * out[uv] + (1.0 - unvoiced_mix) * shape[uv]
    # near-silent frames keep the source's own shape: a pause must stay a pause
    silent = ~audible
    out[silent] = shape[silent]
    return out


# ----------------------------------------------------------------------------
# pitch-synchronous excitation rebuilding
# ----------------------------------------------------------------------------
def pvoc_time_scale(x, sr, alpha, hop_ms=8.0, win_ms=32.0, n_fft=N_FFT):
    """Phase-vocoder time scaling: output is `alpha` times as long, pitch kept.

    Phase is propagated with the standard wrap-and-accumulate rule so the
    resynthesised frames stay phase-coherent.
    """
    if abs(alpha - 1.0) < 1e-3:
        return x.copy()
    win = int(round(win_ms * sr / 1000.0))
    hop_a = int(round(hop_ms * sr / 1000.0))
    hop_s = max(1, int(round(hop_a * alpha)))
    X, hop, w = stft(x, sr, win_ms=win_ms, hop_ms=hop_ms, n_fft=n_fft)
    bins = X.shape[1]
    omega = 2.0 * np.pi * np.arange(bins) / n_fft
    ph = np.angle(X)
    mag = np.abs(X)
    out_ph = np.zeros_like(ph)
    prev = ph[0].copy()
    out_ph[0] = prev
    expect = omega * hop_a
    for i in range(1, X.shape[0]):
        d = ph[i] - ph[i - 1] - expect
        d = (d + np.pi) % (2.0 * np.pi) - np.pi
        prev = prev + omega * hop_s + d
        out_ph[i] = prev
    Y = mag * np.exp(1j * out_ph)
    return istft(Y, hop_s, win, sr, length=int(round(len(x) * alpha)))


def pitch_shift(x, sr, beta):
    """Scale pitch by `beta`, duration preserved (resample + phase vocoder)."""
    if abs(beta - 1.0) < 0.004:
        return x.copy()
    beta = float(np.clip(beta, 0.55, 1.8))
    from fractions import Fraction
    fr = Fraction(beta).limit_denominator(64)
    y1 = resample_poly(x, fr.denominator, fr.numerator)   # pitch x beta
    alpha = len(x) / float(len(y1))                       # restore duration
    y2 = pvoc_time_scale(y1, sr, alpha)
    if len(y2) < len(x):
        y2 = np.pad(y2, (0, len(x) - len(y2)))
    return y2[:len(x)]


def _pitch_marks(r, sr, t_grid, f0, voiced):
    n = len(r)
    marks = []
    t = 0.0
    while t < n / float(sr):
        f = float(np.interp(t, t_grid, f0))
        v = float(np.interp(t, t_grid, voiced.astype(float))) > 0.5
        if v and f > 0:
            p = 1.0 / f
            i0 = int(round(t * sr))
            ps = max(2, int(round(p * sr)))
            lo = max(0, i0 - ps // 4)
            hi = min(n, i0 + ps // 4 + 1)
            if hi - lo >= 4:
                seg = np.abs(r[lo:hi])
                win = max(1, len(seg) // 8)
                sm = np.convolve(seg, np.ones(win) / win, mode="same")
                j = lo + int(np.argmax(sm))
            else:
                j = i0
            marks.append(j)
            t += p
        else:
            marks.append(int(round(t * sr)))
            t += 0.005
    return np.array(marks, dtype=np.int64)


def synth_excitation(r, sr, t_grid, f0_src, voiced, f0_tgt):
    """Rebuild the signal on the target F0 contour; duration is preserved.

    Each glottal period of the source is resampled to the target period length
    and overlap-added through a Hann window twice that long, so consecutive
    periods share half their length and no join discontinuity is left behind.
    Because the target periods are longer (lower pitch) fewer source periods
    are consumed than the output needs, and the surplus ones are skipped.
    """
    n = len(r)
    dur = n / float(sr)
    marks = _pitch_marks(r, sr, t_grid, f0_src, voiced)
    if len(marks) < 2:
        return r.copy()
    pad = int(0.05 * sr)
    out = np.zeros(n + 2 * pad)
    nrm = np.zeros(n + 2 * pad)
    j = 0
    t = marks[0] / float(sr)
    guard = 0
    while t < dur and guard < 500000:
        guard += 1
        ft = float(np.interp(t, t_grid, f0_tgt))
        v = float(np.interp(t, t_grid, voiced.astype(float))) > 0.5
        i_out = int(round(t * sr)) + pad
        if i_out - pad >= n:
            break
        if v and ft > 0:
            n_t = max(6, int(round(sr / ft)))
            while j < len(marks) - 2 and marks[j + 1] < i_out - pad:
                j += 1
            i_a = marks[j]
            i_b = marks[j + 1] if j + 1 < len(marks) else min(n, i_a + n_t)
            seg = r[i_a:i_b]
            if len(seg) < 4:
                break
            # cubic (PCHIP-free) interpolation via cubic convolution
            xs = np.arange(n_t) * (len(seg) - 1) / float(n_t - 1)
            seg2 = _cubic_interp(seg, xs)
            L = 2 * n_t
            half = n_t
            w = hann(L)
            buf = np.zeros(L)
            buf[half - n_t // 2:half - n_t // 2 + n_t] = seg2
            o = i_out - half
            o0, o1 = max(0, o), min(len(out), o + L)
            if o1 > o0:
                out[o0:o1] += (buf * w)[o0 - o:o1 - o]
                nrm[o0:o1] += w[o0 - o:o1 - o]
            t += n_t / float(sr)
        else:
            blk = int(0.005 * sr)
            i1 = min(n, i_out - pad + blk)
            m = i1 - (i_out - pad)
            if m <= 0:
                break
            out[i_out:i_out + m] += r[i_out - pad:i1]
            nrm[i_out:i_out + m] += 1.0
            t += blk / float(sr)
    nrm[nrm < 1e-6] = 1.0
    y = (out / nrm)[pad:pad + n]
    if len(y) < n:
        y = np.pad(y, (0, n - len(y)))
    return y[:n]


def _cubic_interp(y, xs):
    """Cubic convolution (Catmull-Rom) interpolation of `y` at positions `xs`."""
    n = len(y)
    x0 = np.floor(xs).astype(np.int64)
    frac = xs - x0
    yp = np.concatenate([[y[0]], y, [y[-1], y[-1], y[-1]]])

    def at(k):
        return yp[np.clip(k + 1, 0, len(yp) - 1)]

    p0, p1, p2, p3 = at(x0 - 1), at(x0), at(x0 + 1), at(x0 + 2)
    a = -0.5 * p0 + 1.5 * p1 - 1.5 * p2 + 0.5 * p3
    b = p0 - 2.5 * p1 + 2.0 * p2 - 0.5 * p3
    c = -0.5 * p0 + 0.5 * p2
    return ((a * frac + b) * frac + c) * frac + p1


# ----------------------------------------------------------------------------
# long-term spectral matching (timbre post-filter)
# ----------------------------------------------------------------------------
def ltas(x, sr, sr_analysis=SR, n_ceps=20):
    """Smooth log-power long-term average spectrum over voiced frames."""
    if sr != sr_analysis:
        x = resample_poly(x, sr_analysis, sr)
    X, hop, win = stft(x, sr_analysis, win_ms=WIN_MS, hop_ms=HOP_MS, n_fft=N_FFT)
    f0, v, fh, fw = f0_track(x, sr_analysis, win_ms=40.0, hop_ms=10.0,
                             fmin=FMIN, fmax=FMAX)
    t_stft = (np.arange(X.shape[0]) * hop + win / 2.0) / sr_analysis
    t_f0 = (np.arange(len(f0)) * fh + fw / 2.0) / sr_analysis
    vs = np.interp(t_stft, t_f0, v.astype(float)) > 0.5
    P = np.abs(X[vs]) ** 2 if vs.sum() > 30 else np.abs(X) ** 2
    return cepsmooth(np.log(np.maximum(P.mean(axis=0), 1e-12)), n_ceps, N_FFT)


def match_ltas(y, tgt_ltas, sr, max_db=7.0, smooth_ceps=14):
    """Nudge the output's overall tonal balance toward the reference's."""
    cur = ltas(y, sr)
    delta = cepsmooth(tgt_ltas - cur, smooth_ceps, N_FFT)
    lim = max_db * np.log(10.0) / 20.0
    delta = np.clip(delta, -lim, lim)
    Y, hop, win = stft(y, sr, win_ms=WIN_MS, hop_ms=HOP_MS, n_fft=N_FFT)
    out = istft(Y * np.exp(delta), hop, win, sr, length=len(y))
    return soft_limit(out * (np.sqrt(np.mean(y ** 2) + 1e-12) /
                             np.sqrt(np.mean(out ** 2) + 1e-12)))


# ----------------------------------------------------------------------------
# full conversion
# ----------------------------------------------------------------------------
def match_ltas_local(y, tgt_ltas, sr, win_s=12.0, step_s=4.0, max_db=6.0,
                     smooth_ceps=14):
    """Time-varying tonal-balance match.

    A single global correction curve is wrong for parts of a long recording
    (measured: it doubles the word-error rate on a 2.5 minute file), so the
    correction is estimated in overlapping windows and interpolated per frame.
    """
    Y, hop, win = stft(y, sr, win_ms=WIN_MS, hop_ms=HOP_MS, n_fft=N_FFT)
    nf = Y.shape[0]
    t = np.arange(nf) * hop / float(sr)
    f0, v, fh, fw = f0_track(y, sr, win_ms=40.0, hop_ms=10.0,
                             fmin=FMIN, fmax=FMAX)
    tf = (np.arange(len(f0)) * fh + fw / 2.0) / sr
    vs = np.interp(t, tf, v.astype(float)) > 0.5
    P = np.abs(Y) ** 2

    lim = max_db * np.log(10.0) / 20.0
    centres = np.arange(win_s / 2.0, max(t[-1], win_s), step_s)
    curves = []
    for c in centres:
        sel = (t >= c - win_s / 2.0) & (t <= c + win_s / 2.0) & vs
        if sel.sum() < 30:
            sel = (t >= c - win_s / 2.0) & (t <= c + win_s / 2.0)
        if sel.sum() < 10:
            curves.append(np.zeros(Y.shape[1]))
            continue
        m = P[sel].mean(axis=0)
        cur = cepsmooth(np.log(np.maximum(m, 1e-12)), smooth_ceps, N_FFT)
        curves.append(np.clip(tgt_ltas - cur, -lim, lim))
    curves = np.stack(curves, axis=0)
    delta = np.stack([np.interp(t, centres, curves[:, k])
                      for k in range(curves.shape[1])], axis=1)
    out = istft(Y * np.exp(delta), hop, win, sr, length=len(y))
    return soft_limit(out * (np.sqrt(np.mean(y ** 2) + 1e-12) /
                             np.sqrt(np.mean(out ** 2) + 1e-12)))

def convert(src_x, tgt, sr=SR, dyn_blend=0.8, knn_blend=KNN_BLEND,
            f0_blend=1.0, f0_stats=None, unvoiced_mix=UNVOICED_MIX):
    a = analyze(src_x, sr)
    f0, vs = a["f0"], a["voiced"]

    # ---- F0 contour mapping -------------------------------------------------
    lf = np.log(np.maximum(f0, 1e-9))
    m = f0 > 0
    if f0_stats is not None:
        # statistics measured over the whole utterance, so that the mapping is
        # identical in every chunk of a long file
        src_mean, src_sd = f0_stats
    else:
        src_mean, src_sd = float(lf[m].mean()), float(lf[m].std())
    sd_use = (1 - dyn_blend) * src_sd + dyn_blend * tgt["f0_sd"]
    f0_new = np.zeros_like(f0)
    f0_new[m] = np.exp((lf[m] - src_mean) / max(src_sd, 1e-6) * sd_use
                       + tgt["f0_mean"])
    f0_new[m] *= tgt["f0_med"] / max(np.exp(np.median(np.log(f0_new[m]))), 1e-9)
    f0_new = np.clip(f0_new, FMIN, FMAX)
    f0_new = f0_new * f0_blend + f0 * (1 - f0_blend)
    f0_new[~m] = 0.0
    src_med = float(np.exp(np.median(lf[m])))
    beta = tgt["f0_med"] / max(src_med, 1e-6)

    # only the per-frame energy of the source is needed later, so the (large)
    # first analysis can be released before the second one is built
    e_src_frames = (np.abs(a["X"]) ** 2).sum(axis=1).astype(np.float64)
    t_grid = a["t"]
    del a

    # ---- pitch conversion of the waveform itself ----------------------------
    # Done on the speech (not on the whitened residual) so the natural glottal
    # excitation and its tilt survive; the vocal-tract colour is removed later.
    # Period-synchronous resynthesis: the measured intelligibility cost of a
    # -5 semitone shift done this way is ~23% relative WER, versus ~48% for a
    # phase-vocoder/resample shifter at the same ratio, because the phase
    # vocoder smears the consonant bursts at a 0.74 time-scale ratio.
    x_ps = synth_excitation(src_x, sr, t_grid, f0, vs, f0_new)

    # ---- envelope conversion ------------------------------------------------
    a = analyze(x_ps, sr)
    audible = a["c0"] > np.percentile(a["c0"], 25)
    shape_out = convert_ceps(a["c0"], a["shape"], audible, tgt,
                             blend=knn_blend, voiced=a["voiced"],
                             unvoiced_mix=unvoiced_mix)
    env_out = cep_to_env(a["c0"], shape_out)
    R, hop, win = a["R"], a["hop"], a["win"]

    n = min(R.shape[0], env_out.shape[0], len(e_src_frames))
    R = R[:n]
    env_out = env_out[:n]
    # per-frame loudness follows the source
    e_src = e_src_frames[:n]
    e_out = (np.abs(R) ** 2 * np.exp(2.0 * env_out)).sum(axis=1)
    scale = np.sqrt(e_src / np.maximum(e_out, 1e-20))
    scale = np.clip(scale, 0.25, 4.0)
    if len(scale) > 15:
        ker = np.hanning(15)
        ker /= ker.sum()
        scale = np.convolve(scale, ker, mode="same")
    Y = R * np.exp(env_out) * scale[:, None]
    y = istft(Y, hop, win, sr, length=len(src_x))

    # ---- polish -------------------------------------------------------------
    y = highpass(y, sr, 60.0)
    rms_s = np.sqrt(np.mean(src_x ** 2) + 1e-12)
    rms_y = np.sqrt(np.mean(y ** 2) + 1e-12)
    y = y * (rms_s / rms_y)
    y = soft_limit(y)
    # NB: a long-term-spectrum post-filter was tried and rejected.  A single
    # global correction curve is wrong for parts of a long recording (it doubled
    # the word-error rate on the 2.5 minute files), and a windowed version made
    # both the word-error rate and the spectral deviation worse.  The cepstral
    # conversion below already carries the timbre transfer.
    if "ltas" in tgt and LTAS_MATCH:
        y = match_ltas_local(y, tgt["ltas"], sr)
    return y, dict(f0_src=f0, f0_new=f0_new, x_ps=x_ps,
                   res_new=x_ps, a=a, beta=beta)
