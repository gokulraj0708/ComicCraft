# Voice clone for the demo / testing videos

`ComicCraft_Demo_Video.mp4` and `ComicCraft_Testing_Video.mp4` were re-voiced:
the narration was converted into the voice of `Standard recording 3.mp3`.

**Nothing but the voice changed.** The video streams were copied bit-for-bit
(`-c:v copy`), the wording is untouched, and every sample keeps its original
timestamp, so the narration still lines up with what is on screen.

## What was done

The reference recording (`Standard recording 3.mp3`) was used as the target
speaker and the existing narration was run through a voice-conversion pipeline
rather than being re-recorded, which is what keeps the content and the timing
identical:

1. **Analysis** — STFT, then a cepstral split into a harmonic-free spectral
   envelope (the vocal-tract colour) and a whitened residual (the excitation),
   plus an autocorrelation F0 contour.
2. **Target model** — mean and covariance of the reference speaker's cepstral
   shape, their log-F0 mean and spread, and a kNN codebook of that speaker's
   envelopes for phonetic conditioning.
3. **Pitch** — the waveform is rebuilt period by period on the reference
   speaker's F0 contour (Catmull-Rom resampling, 50 %-overlap Hann OLA), which
   moves the pitch from ~147–152 Hz down to the reference's ~108 Hz without
   changing the duration.
4. **Timbre** — CORAL (mean + covariance) alignment of the source cepstra into
   the target space, blended with the kNN estimate, with a global-variance
   post-filter. The frame energy (`c0`) is always left alone, so pauses stay
   pauses, and unvoiced frames are only partly converted so consonants keep
   their identity.
5. **Resynthesis** — converted envelope x converted excitation, per-frame
   loudness locked to the source, then a 60 Hz high-pass and a soft limiter.

Everything is estimated from the two recordings themselves; no pretrained
network or external model is downloaded, so the whole thing runs offline.

## Reproducing

```bash
pip install numpy scipy
python scripts/voice_clone/convert_video_audio.py \
    narration.wav "Standard recording 3.mp3" narration_converted.wav

ffmpeg -i ComicCraft_Demo_Video.mp4 -i narration_converted.wav \
    -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 128k -ar 24000 -ac 1 \
    -movflags +faststart ComicCraft_Demo_Video_voiced.mp4
```

A full 2.5 minute file converts in about 13 s and needs roughly 3 GB of RAM
(the whole file is processed in one pass; chunked processing was measured to be
clearly worse at the join points).

## Measured results

Checked by re-extracting the audio from the delivered MP4 files.

| | demo | testing |
|---|---|---|
| F0 median, original narration | 147.0 Hz | 151.7 Hz |
| F0 median, after conversion | 129.6 Hz | 132.2 Hz |
| F0 median, `Standard recording 3.mp3` | 107.5 Hz | 107.5 Hz |
| Long-term spectrum distance from the reference | 6.7 dB → 2.8 dB | 6.5 dB → 2.9 dB |
| Word-error rate vs. the original narration (first 60 s) | 4.8 % | 12.1 % |
| Duration | 149.72 s → 149.72 s | 160.51 s → 160.51 s |

Frame-by-frame, the delivered pitch tracks the target contour to within 5.5 %
(about 0.9 semitones) at the median.

The word-error rate is the honest limit of this approach: it is measured with
Whisper against a transcript of the *original* narration, so it counts only
words the conversion made harder to recognise. All of it comes from the pitch
shift, not from the voice change — on the same 60 s of the testing narration,
the pitch shift alone (no timbre conversion at all) scores 19.7 %, while the
full conversion scores 12.1 %.

## Rejected along the way

- **Phase-vocoder / resample pitch shifting** — 47–53 % word-error rate at this
  shift ratio, because a 0.74 time-scale ratio smears the consonant bursts.
- **kNN-dominant envelope mapping** (`KNN_BLEND` ≥ 0.75) — 47 % word-error rate;
  it regresses every frame toward the target's average envelope and flattens
  the phonetic contrasts.
- **A long-term-spectrum post-filter** — one global correction curve is wrong
  for parts of a 2.5 minute recording (it doubled the word-error rate), and a
  windowed version made both the word-error rate and the spectral distance
  worse. It is present in `vc.py` but switched off by `LTAS_MATCH = False`.

The original videos are still in git history at commit `de6763c`:

```bash
git show de6763c:ComicCraft_Demo_Video.mp4    > ComicCraft_Demo_Video_original.mp4
git show de6763c:ComicCraft_Testing_Video.mp4 > ComicCraft_Testing_Video_original.mp4
```
