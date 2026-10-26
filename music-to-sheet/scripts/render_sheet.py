#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import math
from collections import Counter
from pathlib import Path

ROWS = [
    ("crash", "CY", "Cymbal"),
    ("closed_hihat", "HH", "Hi-hat"),
    ("open_hihat", "OH", "Open hi-hat"),
    ("tom", "T", "Tom"),
    ("snare", "S", "Snare"),
    ("kick", "K", "Kick"),
]
COLORS = ["#ff6b9d", "#8b7cff", "#4fd1c5", "#ffb454", "#67b7ff", "#ec6a5f"]


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render chord and drum transcription as HTML")
    parser.add_argument("--chords", type=Path, required=True)
    parser.add_argument("--drums", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="Music transcription")
    parser.add_argument("--bpm", type=float, default=95.0)
    parser.add_argument("--audio-relative")
    return parser.parse_args()


def stamp(seconds: float) -> str:
    minutes, remainder = divmod(max(0.0, seconds), 60)
    return f"{int(minutes):02d}:{remainder:05.2f}"


def chord_timeline(chords: list[dict], duration: float) -> str:
    blocks = []
    for index, item in enumerate(chords):
        width = max(0.5, (item["end"] - item["start"]) / duration * 100)
        blocks.append(
            f'<div class="chord-block" style="--w:{width:.3f};--c:{COLORS[index % len(COLORS)]}" '
            f'title="{html.escape(item["chord"])} · {stamp(item["start"])}–{stamp(item["end"])}">'
            f'<strong>{html.escape(item["chord"])}</strong><small>{stamp(item["start"])}</small></div>'
        )
    return "".join(blocks)


def drum_measures(events: list[dict], bpm: float, duration: float) -> str:
    beat = 60.0 / bpm
    measure_length = beat * 4
    measure_count = max(1, math.ceil(duration / measure_length))
    slots: dict[tuple[int, str, int], int] = Counter()
    for event in events:
        absolute_slot = max(0, round(float(event["time"]) / (beat / 4)))
        measure, slot = divmod(absolute_slot, 16)
        if measure < measure_count:
            slots[(measure, event["instrument"], slot)] += 1

    measures = []
    for measure in range(measure_count):
        rows = []
        for instrument, short, label in ROWS:
            cells = []
            for slot in range(16):
                count = slots[(measure, instrument, slot)]
                beat_class = " beat" if slot % 4 == 0 else ""
                mark = "●" if count else "·"
                cells.append(f'<span class="note{beat_class}{" hit" if count else ""}">{mark}</span>')
            rows.append(
                f'<div class="drum-label" aria-label="{label}"><abbr title="{label}">{short}</abbr></div>'
                f'<div class="notes">{"".join(cells)}</div>'
            )
        start = measure * measure_length
        measures.append(
            f'<article class="measure"><header><b>第 {measure + 1} 小節</b><time>{stamp(start)}</time></header>'
            f'<div class="staff">{"".join(rows)}</div></article>'
        )
    return "".join(measures)


def score_gallery(output_dir: Path) -> str:
    pages = sorted((output_dir / "drum-score").glob("page-*.svg"))
    if not pages:
        return '<p class="score-pending">尚未產生 SVG 預覽；可下載 MusicXML 以 MuseScore 開啟。</p>'
    return "".join(
        f'<figure class="score-page"><img src="drum-score/{page.name}" alt="五線鼓譜第 {index} 頁" loading="lazy"></figure>'
        for index, page in enumerate(pages, 1)
    )


def render(chords: list[dict], drums: dict, title: str, bpm: float, audio_relative: str | None, output_dir: Path) -> str:
    events = drums.get("events", [])
    duration = max(
        max((float(item["end"]) for item in chords), default=0.0),
        max((float(item["time"]) for item in events), default=0.0),
        0.001,
    )
    chord_counts = Counter(item["chord"] for item in chords)
    common = " · ".join(chord for chord, _ in chord_counts.most_common(6))
    audio = (
        f'<audio controls preload="metadata"><source src="{html.escape(audio_relative)}"></audio>'
        if audio_relative else ""
    )
    counts = drums.get("counts", {})
    count_cards = "".join(
        f'<div class="metric"><strong>{count}</strong><span>{html.escape(name.replace("_", " ").title())}</span></div>'
        for name, count in sorted(counts.items(), key=lambda item: -item[1])
    )
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}｜和弦與鼓譜</title>
<style>
:root{{--bg:#090b13;--panel:#121624;--line:#2b3248;--text:#f6f1ff;--muted:#a8afc3;--pink:#ff6b9d;--cyan:#4fd1c5}}
*{{box-sizing:border-box}} body{{margin:0;color:var(--text);background:radial-gradient(circle at 15% 0,#251738 0,transparent 32rem),var(--bg);font-family:Inter,"Noto Sans TC",system-ui,sans-serif}}
main{{max-width:1200px;margin:auto;padding:48px 24px 72px}} .eyebrow{{color:var(--cyan);font:700 12px/1.3 ui-monospace,monospace;letter-spacing:.16em;text-transform:uppercase}}
h1{{max-width:900px;margin:12px 0 10px;font-size:clamp(34px,6vw,72px);line-height:1.02;letter-spacing:-.04em}} .subtitle{{color:var(--muted);font-size:17px}} audio{{width:min(640px,100%);margin-top:20px}}
.badges{{display:flex;gap:8px;flex-wrap:wrap;margin:22px 0 34px}} .badge{{border:1px solid var(--line);background:#ffffff08;padding:8px 12px;border-radius:999px;color:#dfe5f8;font:600 12px ui-monospace,monospace}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:20px 0 42px}} .metric{{padding:18px;border:1px solid var(--line);background:linear-gradient(145deg,#171b2c,#10131f);border-radius:16px}} .metric strong{{display:block;font-size:28px}} .metric span{{color:var(--muted);font-size:12px}}
section{{margin-top:52px}} h2{{font-size:28px;margin:0 0 8px}} .section-note{{color:var(--muted);margin:0 0 20px}} .timeline{{display:flex;min-height:104px;overflow-x:auto;border:1px solid var(--line);border-radius:18px;background:var(--panel);padding:8px}}
.chord-block{{flex:var(--w) 0 0;min-width:42px;display:flex;flex-direction:column;justify-content:center;align-items:center;border-left:3px solid var(--c);background:color-mix(in srgb,var(--c) 13%,transparent);padding:8px 5px}} .chord-block:first-child{{border-radius:10px 0 0 10px}} .chord-block strong{{font-size:18px}} .chord-block small{{color:var(--muted);font:10px ui-monospace,monospace}}
.measures{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr));gap:14px}} .measure{{background:var(--panel);border:1px solid var(--line);border-radius:16px;overflow:hidden}} .measure header{{display:flex;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--line);font-size:13px}} .measure time{{color:var(--muted);font:12px ui-monospace,monospace}}
.score-toolbar{{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}} .download{{color:var(--text);text-decoration:none;border:1px solid var(--line);background:#171b2c;padding:10px 14px;border-radius:10px;font:700 12px ui-monospace,monospace}} .download:hover{{border-color:var(--cyan);color:var(--cyan)}}
.score-pages{{display:grid;gap:20px}} .score-page{{margin:0;background:white;border-radius:14px;overflow:hidden;box-shadow:0 20px 55px #0008}} .score-page img{{display:block;width:100%;height:auto}} .score-pending{{padding:24px;border:1px dashed var(--line);border-radius:14px;color:var(--muted)}}
.notice{{margin-top:42px;padding:18px 20px;border:1px solid #72536b;background:#ff6b9d0c;border-radius:14px;color:#d8c5d3}} footer{{margin-top:50px;color:#727b96;font-size:12px}}
@media(max-width:600px){{main{{padding:32px 14px 56px}} .score-pages{{gap:12px}}}}
</style></head><body><main>
<div class="eyebrow">Music-to-sheet · Model transcription</div><h1>{html.escape(title)}</h1>
<p class="subtitle">和弦時間軸 × 五線打擊樂譜</p>{audio}
<div class="badges"><span class="badge">Tempo ≈ {bpm:g} BPM</span><span class="badge">4 / 4</span><span class="badge">Duration {stamp(duration)}</span><span class="badge">Omnizart + ADTOF</span></div>
<div class="metrics">{count_cards}</div>
<section><h2>和弦譜</h2><p class="section-note">主要和弦：{html.escape(common)}。將游標移到色塊可查看精確時間。</p><div class="timeline">{chord_timeline(chords, duration)}</div></section>
<section><h2>五線鼓譜</h2><p class="section-note">五線打擊樂譜；事件依 {bpm:g} BPM 對齊至最近十六分音符。× 符頭表示 hi-hat／cymbal。</p>
<div class="score-toolbar"><a class="download" href="drum-score.musicxml" download>MusicXML</a><a class="download" href="drum-score.pdf" download>PDF</a><a class="download" href="drums.mid" download>MIDI</a></div>
<div class="score-pages">{score_gallery(output_dir)}</div></section>
<div class="notice"><strong>注意：</strong>AI 轉錄結果僅供編曲參考。合成鼓、延伸和弦、轉位與密集混音可能需要人工校正。</div>
<footer>Generated locally by music-to-sheet · Chord model: Omnizart chord_v1 · Drum model: ADTOF-PyTorch</footer>
</main></body></html>"""


def main() -> None:
    options = args()
    chords = json.loads(options.chords.read_text(encoding="utf-8"))
    drums = json.loads(options.drums.read_text(encoding="utf-8"))
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(
        render(chords, drums, options.title, options.bpm, options.audio_relative, options.output.parent), encoding="utf-8"
    )
    print(options.output.resolve())


if __name__ == "__main__":
    main()
