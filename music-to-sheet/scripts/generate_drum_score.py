#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

DIVISIONS = 4  # one quarter note; one grid slot is a sixteenth
INSTRUMENTS = {
    "kick": {"name": "Bass Drum", "step": "F", "octave": "4", "head": "normal", "midi": 36},
    "snare": {"name": "Snare Drum", "step": "C", "octave": "5", "head": "normal", "midi": 38},
    "tom": {"name": "Tom", "step": "D", "octave": "5", "head": "normal", "midi": 45},
    "open_hihat": {"name": "Open Hi-Hat", "step": "F", "octave": "5", "head": "x", "midi": 46},
    "closed_hihat": {"name": "Closed Hi-Hat", "step": "G", "octave": "5", "head": "x", "midi": 42},
    "crash": {"name": "Crash Cymbal", "step": "A", "octave": "5", "head": "x", "midi": 49},
}
ORDER = {name: index for index, name in enumerate(reversed(tuple(INSTRUMENTS)))}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a five-line percussion MusicXML score")
    parser.add_argument("--drums", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="Drum transcription")
    parser.add_argument("--bpm", type=float, required=True)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--offset", type=float, default=0.0, help="Time in seconds of measure 1 beat 1")
    return parser.parse_args()


def text(parent: ET.Element, tag: str, value: object, **attrs: str) -> ET.Element:
    node = ET.SubElement(parent, tag, attrs)
    node.text = str(value)
    return node


def rhythm_type(duration: int) -> tuple[str, bool]:
    return {1: ("16th", False), 2: ("eighth", False), 3: ("eighth", True), 4: ("quarter", False)}[duration]


def add_note(measure: ET.Element, instrument: str, chord: bool, duration: int) -> None:
    spec = INSTRUMENTS[instrument]
    note = ET.SubElement(measure, "note")
    if chord:
        ET.SubElement(note, "chord")
    unpitched = ET.SubElement(note, "unpitched")
    text(unpitched, "display-step", spec["step"])
    text(unpitched, "display-octave", spec["octave"])
    ET.SubElement(note, "instrument", id=f"P1-{instrument}")
    text(note, "duration", duration)
    text(note, "voice", 1)
    note_type, dotted = rhythm_type(duration)
    text(note, "type", note_type)
    if dotted:
        ET.SubElement(note, "dot")
    text(note, "stem", "up")
    text(note, "notehead", spec["head"])


def add_rest(measure: ET.Element, duration: int) -> None:
    note = ET.SubElement(measure, "note")
    ET.SubElement(note, "rest")
    text(note, "duration", duration)
    text(note, "voice", 1)
    note_type, dotted = rhythm_type(duration)
    text(note, "type", note_type)
    if dotted:
        ET.SubElement(note, "dot")


def build_score(drums: dict, title: str, bpm: float, duration: float | None, offset: float = 0.0) -> ET.ElementTree:
    events = drums.get("events", [])
    last_event = max((float(event["time"]) for event in events), default=0.0)
    duration = max(duration or 0.0, last_event + 60.0 / bpm / 4)
    slot_length = 60.0 / bpm / 4
    measure_count = max(1, math.ceil(max(0.0, duration - offset) / (slot_length * 16)))
    slots: dict[int, set[str]] = defaultdict(set)
    for event in events:
        instrument = event.get("instrument")
        if instrument in INSTRUMENTS:
            slots[max(0, round((float(event["time"]) - offset) / slot_length))].add(instrument)

    root = ET.Element("score-partwise", version="4.0")
    work = ET.SubElement(root, "work")
    text(work, "work-title", title)
    identification = ET.SubElement(root, "identification")
    encoding = ET.SubElement(identification, "encoding")
    text(encoding, "software", "music-to-sheet")

    part_list = ET.SubElement(root, "part-list")
    score_part = ET.SubElement(part_list, "score-part", id="P1")
    text(score_part, "part-name", "Drum Set")
    for instrument, spec in INSTRUMENTS.items():
        score_instrument = ET.SubElement(score_part, "score-instrument", id=f"P1-{instrument}")
        text(score_instrument, "instrument-name", spec["name"])
        midi = ET.SubElement(score_part, "midi-instrument", id=f"P1-{instrument}")
        text(midi, "midi-channel", 10)
        text(midi, "midi-program", 1)
        text(midi, "midi-unpitched", spec["midi"] + 1)

    part = ET.SubElement(root, "part", id="P1")
    for measure_index in range(measure_count):
        measure = ET.SubElement(part, "measure", number=str(measure_index + 1))
        if measure_index == 0:
            attributes = ET.SubElement(measure, "attributes")
            text(attributes, "divisions", DIVISIONS)
            time = ET.SubElement(attributes, "time")
            text(time, "beats", 4)
            text(time, "beat-type", 4)
            clef = ET.SubElement(attributes, "clef")
            text(clef, "sign", "percussion")
            details = ET.SubElement(attributes, "staff-details")
            text(details, "staff-lines", 5)
            direction = ET.SubElement(measure, "direction", placement="above")
            direction_type = ET.SubElement(direction, "direction-type")
            metronome = ET.SubElement(direction_type, "metronome")
            text(metronome, "beat-unit", "quarter")
            text(metronome, "per-minute", f"{bpm:g}")
            ET.SubElement(direction, "sound", tempo=f"{bpm:g}")
        measure_slots = range(measure_index * 16, measure_index * 16 + 16)
        if not any(slot in slots for slot in measure_slots):
            note = ET.SubElement(measure, "note")
            ET.SubElement(note, "rest", measure="yes")
            text(note, "duration", 16)
            text(note, "voice", 1)
            text(note, "type", "whole")
            continue
        occupied = sorted(slot - measure_index * 16 for slot in measure_slots if slot in slots)
        local_slot = 0
        while local_slot < 16:
            later_hits = [slot for slot in occupied if slot > local_slot]
            next_beat = min(16, ((local_slot // 4) + 1) * 4)
            boundary = min([next_beat, *later_hits]) if later_hits else next_beat
            duration = boundary - local_slot
            absolute_slot = measure_index * 16 + local_slot
            hits = sorted(slots.get(absolute_slot, ()), key=lambda item: ORDER[item])
            if not hits:
                add_rest(measure, duration)
            else:
                for index, instrument in enumerate(hits):
                    add_note(measure, instrument, index > 0, duration)
            local_slot = boundary

    ET.indent(root, space="  ")
    return ET.ElementTree(root)


def main() -> None:
    options = parse_args()
    drums = json.loads(options.drums.read_text(encoding="utf-8"))
    score = build_score(drums, options.title, options.bpm, options.duration, options.offset)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    score.write(options.output, encoding="utf-8", xml_declaration=True)
    print(options.output.resolve())


if __name__ == "__main__":
    main()
