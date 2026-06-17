#!/usr/bin/env python3
"""Detect tempo (BPM) and musical key of an audio file for ACE-Step conditioning.

Used by restyle_music.sh -k to lock the regenerated backing's tempo + key to the original
song, so the new backing stays on-beat and in-key with the kept original vocal.
Prints one line: "<bpm>\t<key>", e.g. "152\tF# major". Run with the separator venv (has librosa).
"""
import sys
import librosa
import numpy as np

# Krumhansl-Schmuckler key profiles
_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def detect(path):
    y, sr = librosa.load(path, mono=True)
    bpm = int(round(float(np.atleast_1d(librosa.beat.beat_track(y=y, sr=sr)[0])[0])))
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    best = None
    for i in range(12):
        for mode, prof in (("major", _MAJ), ("minor", _MIN)):
            score = np.corrcoef(np.roll(prof, i), chroma)[0, 1]
            if best is None or score > best[2]:
                best = (_NOTES[i], mode, score)
    return bpm, f"{best[0]} {best[1]}"


if __name__ == "__main__":
    bpm, key = detect(sys.argv[1])
    print(f"{bpm}|{key}")
