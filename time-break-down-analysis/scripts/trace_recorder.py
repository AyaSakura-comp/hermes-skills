#!/usr/bin/env python3
"""
Lightweight Universal Telemetry & Timeline Recorder for Time Breakdown Analysis.
Zero external dependencies; exports microsecond-accurate event traces to JSONL.
"""

import time
import json
from contextlib import contextmanager
from typing import Dict, List, Optional, Any


class TraceRecorder:
    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or f"run_{int(time.time() * 1000)}"
        self.events: List[Dict[str, Any]] = []
        self._t0 = time.perf_counter()
        self._wall_t0 = time.time()

    @contextmanager
    def span(self, phase: str, category: str = "default", **metadata):
        """Context manager to measure and record a discrete execution phase."""
        t_start = time.perf_counter()
        wall_start = time.time()
        record: Dict[str, Any] = {
            "run_id": self.run_id,
            "phase": phase,
            "category": category,
            "rel_start": round(t_start - self._t0, 6),
            "wall_start": wall_start,
            "metadata": metadata,
        }
        try:
            yield record
        finally:
            t_end = time.perf_counter()
            wall_end = time.time()
            record["rel_end"] = round(t_end - self._t0, 6)
            record["duration_ms"] = round((t_end - t_start) * 1000, 3)
            record["duration_sec"] = round(t_end - t_start, 4)
            record["wall_end"] = wall_end
            self.events.append(record)

    def mark(self, event_name: str, category: str = "marker", **metadata):
        """Record an instantaneous milestone marker (point-in-time)."""
        t = time.perf_counter()
        self.events.append({
            "run_id": self.run_id,
            "phase": event_name,
            "category": category,
            "rel_start": round(t - self._t0, 6),
            "rel_end": round(t - self._t0, 6),
            "duration_ms": 0.0,
            "duration_sec": 0.0,
            "is_marker": True,
            "wall_start": time.time(),
            "metadata": metadata,
        })

    def export_jsonl(self, filepath: str):
        """Export all recorded spans to a JSONL file."""
        with open(filepath, "w", encoding="utf-8") as f:
            for ev in self.events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    def print_summary(self):
        """Print a human-readable text table breakdown."""
        print(f"\n{'='*75}")
        print(f"⏱️ TIME BREAKDOWN ANALYSIS: {self.run_id}")
        print(f"{'='*75}")
        print(f"{'Phase / Action':<35} | {'Category':<15} | {'Duration':>15}")
        print(f"{'-'*75}")
        total_ms = 0.0
        for ev in self.events:
            dur = f"{ev['duration_ms']:.2f} ms" if ev['duration_ms'] < 1000 else f"{ev['duration_sec']:.3f} s"
            print(f"{ev['phase']:<35} | {ev['category']:<15} | {dur:>15}")
            total_ms += ev["duration_ms"]
        print(f"{'-'*75}")
        tot_str = f"{total_ms:.2f} ms" if total_ms < 1000 else f"{total_ms/1000:.3f} s"
        print(f"{'TOTAL CUMULATIVE TIME':<35} | {'ALL':<15} | {tot_str:>15}")
        print(f"{'='*75}\n")


if __name__ == "__main__":
    recorder = TraceRecorder("sample_pipeline")
    with recorder.span("1. Network Fetch", category="I/O"):
        time.sleep(0.05)
    with recorder.span("2. Local Processing", category="Compute"):
        time.sleep(0.02)
    recorder.mark("Milestone 1 Reached")
    with recorder.span("3. UI Render & Paint", category="Render"):
        time.sleep(0.01)
    recorder.print_summary()
