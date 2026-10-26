#!/usr/bin/env python3
"""Unit tests for qwen_image CLI script."""

import sys
from pathlib import Path

# Add scripts directory to sys.path
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from qwen_image import (
    ASPECT_RATIOS,
    DEFAULT_NEGATIVE_PROMPT,
    NATIVE_RESOLUTIONS,
    build_workflow,
)


def test_aspect_ratios_consistency():
    for ar, cfg in ASPECT_RATIOS.items():
        bw, bh = cfg["base"]
        tw, th = cfg["target"]
        assert bw % 16 == 0, f"Base width {bw} for {ar} must be multiple of 16"
        assert bh % 16 == 0, f"Base height {bh} for {ar} must be multiple of 16"
        assert tw > 0 and th > 0


def test_workflow_structure():
    wf = build_workflow(
        prompt="Cyberpunk rabbit girl",
        negative_prompt=DEFAULT_NEGATIVE_PROMPT,
        width=704,
        height=1280,
        seed=12345,
        steps=25,
        cfg=1.0,
        prefix="test_qwen",
    )
    assert "1" in wf and wf["1"]["class_type"] == "UNETLoader"
    assert "2" in wf and wf["2"]["class_type"] == "CLIPLoader"
    assert "3" in wf and wf["3"]["class_type"] == "VAELoader"
    assert "4" in wf and wf["4"]["class_type"] == "TextEncodeQwenImage21"
    assert "5" in wf and wf["5"]["class_type"] == "EmptyLatentImage"
    assert "6" in wf and wf["6"]["class_type"] == "KSampler"
    assert "7" in wf and wf["7"]["class_type"] == "VAEDecode"
    assert "8" in wf and wf["8"]["class_type"] == "SaveImage"

    # Check connection inputs
    assert wf["6"]["inputs"]["model"] == ["1", 0]
    assert wf["6"]["inputs"]["positive"] == ["4", 0]
    assert wf["6"]["inputs"]["negative"] == ["4", 1]
    assert wf["6"]["inputs"]["latent_image"] == ["5", 0]
    assert wf["6"]["inputs"]["steps"] == 25
    assert wf["6"]["inputs"]["seed"] == 12345
    assert wf["7"]["inputs"]["samples"] == ["6", 0]
    assert wf["7"]["inputs"]["vae"] == ["3", 0]
    assert wf["8"]["inputs"]["images"] == ["7", 0]


if __name__ == "__main__":
    test_aspect_ratios_consistency()
    test_workflow_structure()
    print("All unit tests passed successfully!")
