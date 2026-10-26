import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


def test_musicxml_uses_five_line_percussion_notation(tmp_path: Path):
    drums = {
        "counts": {"kick": 1, "snare": 1, "closed_hihat": 1, "crash": 1},
        "events": [
            {"time": 0.0, "instrument": "kick", "midi_pitch": 35},
            {"time": 0.0, "instrument": "closed_hihat", "midi_pitch": 42},
            {"time": 0.5, "instrument": "snare", "midi_pitch": 38},
            {"time": 1.0, "instrument": "crash", "midi_pitch": 49},
        ],
    }
    source = tmp_path / "drums.json"
    target = tmp_path / "drum-score.musicxml"
    source.write_text(json.dumps(drums), encoding="utf-8")

    subprocess.run(
        [
            "python3",
            str(Path(__file__).parents[1] / "scripts" / "generate_drum_score.py"),
            "--drums",
            str(source),
            "--output",
            str(target),
            "--title",
            "Test Song",
            "--bpm",
            "120",
            "--duration",
            "2",
        ],
        check=True,
    )

    root = ET.parse(target).getroot()
    assert root.findtext(".//clef/sign") == "percussion"
    assert root.findtext(".//staff-details/staff-lines") == "5"
    assert root.find(".//unpitched") is not None
    assert root.find(".//notehead[.='x']") is not None
    assert root.find(".//note/chord") is not None
    assert root.find(".//sound[@tempo='120']") is not None
    # Sparse events must be rhythmically grouped, not expanded into 16 tiny rests.
    assert len(root.findall(".//measure[1]/note")) < 10
    assert any(int(node.text) > 1 for node in root.findall(".//measure[1]/note/duration"))
