#!/usr/bin/env python3
"""Run See-Through Marigold depth and PSD composition after LayerDiff has exited."""
from __future__ import annotations

import argparse

from utils.inference_utils import apply_marigold, further_extr


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output_dir")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resolution", type=int, default=512)
    args = parser.parse_args()

    apply_marigold(
        args.input,
        "24yearsold/seethroughv0.0.1_marigold",
        save_dir=args.output_dir,
        seed=args.seed,
        resolution=args.resolution,
        num_inference_steps=-1,
        disable_progressbar=True,
        group_offload=True,
    )
    from pathlib import Path

    saved = Path(args.output_dir) / Path(args.input).stem
    further_extr(str(saved), rotate=False, save_to_psd=True, tblr_split=False)


if __name__ == "__main__":
    main()
