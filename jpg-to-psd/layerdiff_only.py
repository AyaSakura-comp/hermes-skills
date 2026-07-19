#!/usr/bin/env python3
"""Run See-Through LayerDiff only; process exit releases its GPU allocations."""
from __future__ import annotations

import argparse
import os
import os.path as osp

import numpy as np
import torch
from PIL import Image

from modules.layerdiffuse.diffusers_kdiffusion_sdxl import KDiffusionStableDiffusionXLPipeline
from modules.layerdiffuse.layerdiff3d import UNetFrameConditionModel
from modules.layerdiffuse.vae import TransparentVAE
from utils.cv import center_square_pad_resize
from utils.inference_utils import apply_layerdiff
from utils.torch_utils import seed_everything

BODY_TAGS = [
    "front hair", "back hair", "head", "neck", "neckwear", "topwear", "handwear",
    "bottomwear", "legwear", "footwear", "tail", "wings", "objects",
]


def run_body_only(input_path: str, output_dir: str, seed: int, resolution: int, steps: int) -> None:
    """Generate only the 13 body layers; intentionally omits head, depth, and PSD."""
    repo = "layerdifforg/seethroughv0.0.2_layerdiff3d"
    pipeline = KDiffusionStableDiffusionXLPipeline.from_pretrained(
        repo,
        trans_vae=TransparentVAE.from_pretrained(repo, subfolder="trans_vae"),
        unet=UNetFrameConditionModel.from_pretrained(repo, subfolder="unet"),
        scheduler=None,
    )
    for model in (pipeline.vae, pipeline.trans_vae, pipeline.unet, pipeline.text_encoder, pipeline.text_encoder_2):
        model.to(device="cuda", dtype=torch.bfloat16).eval()
    pipeline.cache_tag_embeds()
    pipeline.set_progress_bar_config(disable=True)

    saved = osp.join(output_dir, osp.splitext(osp.basename(input_path))[0])
    os.makedirs(saved, exist_ok=True)
    image = np.array(Image.open(input_path).convert("RGBA"))
    fullpage = center_square_pad_resize(image, resolution)
    Image.fromarray(fullpage).save(osp.join(saved, "src_img.png"))
    result = pipeline(
        strength=1.0,
        num_inference_steps=steps,
        batch_size=1,
        generator=torch.Generator(device="cuda").manual_seed(seed),
        guidance_scale=1.0,
        prompt=BODY_TAGS,
        negative_prompt="",
        fullpage=fullpage,
        group_index=0,
    )
    for layer, tag in zip(result.images, BODY_TAGS):
        Image.fromarray(layer).save(osp.join(saved, f"{tag}.png"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output_dir")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resolution", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=32)
    parser.add_argument("--body-only", action="store_true")
    args = parser.parse_args()

    seed_everything(args.seed)
    if args.body_only:
        run_body_only(args.input, args.output_dir, args.seed, args.resolution, args.steps)
        return
    apply_layerdiff(
        args.input,
        "layerdifforg/seethroughv0.0.2_layerdiff3d",
        save_dir=args.output_dir,
        seed=args.seed,
        resolution=args.resolution,
        num_inference_steps=args.steps,
        disable_progressbar=True,
        group_offload=False,
    )


if __name__ == "__main__":
    main()
