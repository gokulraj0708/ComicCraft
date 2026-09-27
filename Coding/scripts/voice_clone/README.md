# Offline voice-conversion utility

This optional utility converts the narration of a supplied source recording into
a supplied reference voice. It is independent of the ComicCraft application
runtime and does not require any media assets to be checked into the repository.

## What it does

The pipeline estimates a speaker model from the reference recording and applies
it to the source narration without changing its timing:

1. **Analysis** — STFT, a cepstral split into a spectral envelope and residual,
   and an autocorrelation F0 contour.
2. **Target model** — the reference speaker's cepstral statistics, log-F0
   statistics, and a kNN envelope codebook.
3. **Pitch** — period-by-period waveform reconstruction with overlap-add.
4. **Timbre** — CORAL alignment blended with the kNN estimate while preserving
   source energy and unvoiced consonants.
5. **Resynthesis** — converted envelope and excitation with source loudness,
   high-pass filtering, and a soft limiter.

Everything is estimated from the two input recordings; no pretrained network or
external model is downloaded.

## Usage

```bash
pip install numpy scipy
python scripts/voice_clone/convert_video_audio.py \
    source.wav reference.wav converted.wav
```

The command accepts any source and reference audio files supported by the
utility. To place converted narration into a separate video workflow, use the
resulting audio file with your preferred media tool.

A long recording is processed in one pass and can require several gigabytes of
RAM. The implementation and analysis helpers are kept here as optional
repository tooling; they are not imported by the ComicCraft server.
