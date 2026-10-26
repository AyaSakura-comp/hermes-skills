import json
import subprocess
from pathlib import Path


def test_renderer_creates_chord_timeline_and_drum_grid(tmp_path: Path):
    chords = [
        {"chord": "Am", "start": 0.0, "end": 2.0},
        {"chord": "F", "start": 2.0, "end": 4.0},
    ]
    drums = {
        "counts": {"kick": 1, "snare": 1, "closed_hihat": 2},
        "events": [
            {"time": 0.0, "instrument": "kick", "midi_pitch": 35},
            {"time": 0.5, "instrument": "closed_hihat", "midi_pitch": 42},
            {"time": 1.0, "instrument": "snare", "midi_pitch": 38},
            {"time": 1.5, "instrument": "closed_hihat", "midi_pitch": 42},
        ],
    }
    (tmp_path / "chords.json").write_text(json.dumps(chords), encoding="utf-8")
    (tmp_path / "drums.json").write_text(json.dumps(drums), encoding="utf-8")
    output = tmp_path / "index.html"

    subprocess.run(
        [
            "python3",
            str(Path(__file__).parents[1] / "scripts" / "render_sheet.py"),
            "--chords",
            str(tmp_path / "chords.json"),
            "--drums",
            str(tmp_path / "drums.json"),
            "--output",
            str(output),
            "--title",
            "Test Song",
            "--bpm",
            "120",
        ],
        check=True,
    )

    html = output.read_text(encoding="utf-8")
    assert "Test Song" in html
    assert "Am" in html and "F" in html
    assert "五線鼓譜" in html
    assert "drum-score.musicxml" in html
    assert "AI 轉錄結果僅供編曲參考" in html
