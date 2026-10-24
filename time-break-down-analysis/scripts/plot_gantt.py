#!/usr/bin/env python3
"""
Universal Multi-Lane Gantt Chart & Time Breakdown Visualizer.
Generates publication-quality single-lane or multi-version comparative Gantt charts.
"""

import sys
import os
import json
import argparse
from typing import List, Dict, Any
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib import font_manager

# Pick a CJK-capable font so Chinese phase labels don't render as boxes.
for _family in ("Noto Sans CJK TC", "Noto Sans CJK JP", "Noto Serif CJK TC", "WenQuanYi Zen Hei"):
    if any(f.name == _family for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [_family, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
        break


# Premium cohesive palette
PALETTE = {
    "open": "#3498db",        # Blue
    "ground": "#9b59b6",      # Purple
    "plan": "#e67e22",        # Orange
    "fill": "#2ecc71",        # Emerald Green
    "settle": "#e74c3c",      # Red / Coral
    "submit": "#1abc9c",      # Teal
    "render": "#f1c40f",      # Gold
    "io": "#34495e",          # Slate
    "default": "#7f8c8d",     # Grey
}


def get_color(name: str) -> str:
    lower = name.lower()
    for key, color in PALETTE.items():
        if key in lower:
            return color
    return PALETTE["default"]


def plot_lane_gantt(spans: List[Dict[str, Any]], title: str, output_path: str, legend: Dict[str, str] = None):
    """Render spans that share rows: every span with the same "lane" sits on one row (e.g. one agent turn = encode+prefill+decode+tool)."""
    lanes = []
    for s in spans:
        if s["lane"] not in lanes:
            lanes.append(s["lane"])
    fig, ax = plt.subplots(figsize=(14, max(4, len(lanes) * 0.42) + 2.0), dpi=200)
    max_x = max(s.get("rel_start", 0.0) + s.get("duration_sec", 0.0) for s in spans)
    for s in spans:
        y = lanes.index(s["lane"])
        start, dur = s.get("rel_start", 0.0), s.get("duration_sec", 0.0)
        color = get_color(s.get("category", s.get("phase", "")))
        ax.barh(y, dur, left=start, height=0.6, color=color, edgecolor="black", linewidth=0.5, alpha=0.92)
        if dur >= max_x * 0.012:
            ax.text(start + dur / 2, y, f"{dur:.1f}", va="center", ha="center", fontsize=7, color="white", fontweight="bold")
    ax.set_yticks(range(len(lanes)))
    ax.set_yticklabels(lanes, fontsize=9, fontweight="semibold")
    ax.invert_yaxis()
    ax.set_xlabel("Elapsed Time (Seconds)", fontsize=11, fontweight="bold")
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    ax.grid(axis="x", linestyle="--", alpha=0.5)
    if legend:
        handles = [patches.Patch(color=get_color(cat), label=label) for cat, label in legend.items()]
        ax.legend(handles=handles, loc="upper right", fontsize=9, framealpha=0.95)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()
    print(f"✅ Lane Gantt chart saved to: {output_path}")


def plot_single_gantt(spans: List[Dict[str, Any]], title: str, output_path: str):
    """Render a single run Gantt chart."""
    fig, ax = plt.subplots(figsize=(12, max(4, len(spans) * 0.45) + 1.5), dpi=200)

    y_labels = [s["phase"] for s in spans]
    y_positions = list(range(len(spans)))

    for i, s in enumerate(spans):
        start = s.get("rel_start", s.get("start", 0.0))
        dur = s.get("duration_sec", s.get("dur", s.get("rel_end", 0.0) - start))
        color = get_color(s.get("category", s.get("cat", s["phase"])))
        
        ax.barh(i, dur, left=start, height=0.55, align='center', color=color,
                edgecolor='black', linewidth=0.8, alpha=0.9)
        
        label_text = f"{dur*1000:.1f}ms" if dur < 1.0 else f"{dur:.2f}s"
        ax.text(start + dur + 0.02, i, label_text, va='center', ha='left',
                fontsize=9, fontweight='bold', color='#2c3e50')

    ax.set_yticks(y_positions)
    ax.set_yticklabels(y_labels, fontsize=10, fontweight='semibold')
    ax.invert_yaxis()
    ax.set_xlabel("Elapsed Time (Seconds)", fontsize=11, fontweight='bold')
    ax.set_title(title, fontsize=13, fontweight='bold', pad=12)
    ax.grid(axis='x', linestyle='--', alpha=0.5)

    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()
    print(f"✅ Single Gantt chart saved to: {output_path}")


def plot_multiversion_comparison(versions: List[Dict[str, Any]], title: str, output_path: str):
    """
    Render stacked multi-panel Gantt charts comparing multiple architectural versions.
    versions format:
    [
        {"name": "V1: Legacy (14.15s)", "spans": [{"phase": "...", "start": 0.0, "dur": 1.5, "cat": "open"}, ...]},
        {"name": "V2: Compact (11.16s)", "spans": [...]},
        ...
    ]
    """
    n_versions = len(versions)
    fig, axes = plt.subplots(n_versions, 1, figsize=(14, 2.8 * n_versions + 1.0), sharex=True, dpi=220)
    if n_versions == 1:
        axes = [axes]

    max_x = max(max(s["start"] + s["dur"] for s in v["spans"]) for v in versions) * 1.08

    for ax, v in zip(axes, versions):
        spans = v["spans"]
        y_labels = [s["phase"] for s in spans]
        y_pos = list(range(len(spans)))

        for i, s in enumerate(spans):
            start = s["start"]
            dur = s["dur"]
            color = get_color(s.get("cat", s["phase"]))
            
            ax.barh(i, dur, left=start, height=0.6, align='center', color=color,
                    edgecolor='#2c3e50', linewidth=0.8, alpha=0.92)
            
            label_text = f"{dur*1000:.0f}ms" if dur < 0.9 else f"{dur:.2f}s"
            ax.text(start + dur + max_x * 0.008, i, label_text, va='center', ha='left',
                    fontsize=8.5, fontweight='bold', color='#1a252f')

        ax.set_yticks(y_pos)
        ax.set_yticklabels(y_labels, fontsize=9, fontweight='semibold')
        ax.invert_yaxis()
        ax.set_title(v["name"], fontsize=11, fontweight='bold', loc='left', color='#2c3e50', pad=6)
        ax.grid(axis='x', linestyle='--', alpha=0.45)
        ax.set_xlim(0, max_x)

    axes[-1].set_xlabel("Elapsed Time (Seconds)", fontsize=11, fontweight='bold')
    fig.suptitle(title, fontsize=14, fontweight='bold', y=0.995)
    plt.tight_layout()
    plt.subplots_adjust(top=0.94)
    plt.savefig(output_path, dpi=220)
    plt.close()
    print(f"✅ Multi-version comparison chart saved to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Gantt Chart Visualizer")
    parser.add_argument("--jsonl", help="Input JSONL file of spans")
    parser.add_argument("--out", default="gantt.png", help="Output PNG path")
    parser.add_argument("--title", default="Time Breakdown Analysis", help="Chart title")
    parser.add_argument("--legend", help='JSON object {category: label} drawn as a legend (lane mode)')
    parser.add_argument("--versions", help="JSON file: [{name, spans:[{phase,start,dur,cat}]}] for a stacked comparison")
    args = parser.parse_args()

    if args.versions and os.path.exists(args.versions):
        with open(args.versions, "r", encoding="utf-8") as f:
            plot_multiversion_comparison(json.load(f), args.title, args.out)
    elif args.jsonl and os.path.exists(args.jsonl):
        spans = []
        with open(args.jsonl, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    spans.append(json.loads(line))
        if any("lane" in s for s in spans):
            plot_lane_gantt(spans, args.title, args.out, json.loads(args.legend) if args.legend else None)
        else:
            plot_single_gantt(spans, args.title, args.out)
    else:
        print("Usage: python3 plot_gantt.py (--jsonl <trace.jsonl> | --versions <versions.json>) --out <output.png> --title '<Title>'")
