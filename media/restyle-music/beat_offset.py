#!/usr/bin/env python3
"""Estimate the time offset between a reference track and a generated backing.

Cross-correlates onset-strength envelopes of <ref> (e.g. the original instrumental, which is
aligned to the kept vocal) and <gen> (ACE's new backing). Prints the seconds the generated
backing should be DELAYED (positive) or ADVANCED (negative) so its beats land on the reference's.
Used by restyle_music.sh -k to phase-align the new backing to the original vocal's groove.
Run with the separator venv (has librosa).
"""
import sys
import librosa
import numpy as np

HOP = 512


def offset_seconds(ref_path, gen_path):
    yr, sr = librosa.load(ref_path, mono=True)
    yg, _ = librosa.load(gen_path, sr=sr, mono=True)
    oref = librosa.onset.onset_strength(y=yr, sr=sr, hop_length=HOP)
    ogen = librosa.onset.onset_strength(y=yg, sr=sr, hop_length=HOP)
    oref = (oref - oref.mean()) / (oref.std() + 1e-9)
    ogen = (ogen - ogen.mean()) / (ogen.std() + 1e-9)
    corr = np.correlate(oref, ogen, mode="full")
    lags = np.arange(-(len(ogen) - 1), len(oref))
    # Only the sub-beat phase matters: aligning the beat GRID needs a shift within ±half a beat
    # period. A larger "match" just adds intro silence / truncates the end. Constrain to ±beat/2.
    tempo = float(np.atleast_1d(librosa.beat.beat_track(y=yr, sr=sr)[0])[0]) or 120.0
    max_frames = max(1, int((60.0 / tempo) / 2 * sr / HOP))
    mask = np.abs(lags) <= max_frames
    best_lag = lags[mask][np.argmax(corr[mask])]
    # best_lag > 0 means ogen must be shifted right (delayed) to match oref.
    return best_lag * HOP / sr


if __name__ == "__main__":
    print(f"{offset_seconds(sys.argv[1], sys.argv[2]):.3f}")
