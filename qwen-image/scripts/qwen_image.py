#!/usr/bin/env python3
"""
Qwen-Image-2.1 generation CLI for ComfyUI.
Optimized for AMD ROCm / Strix Halo APU with two-stage super-sampling.
Supports native Chinese & English prompt understanding, hands/anatomy control,
and multiple aspect ratios.
"""

import argparse
import io
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

# Auto-reexec with ComfyUI venv if PIL is missing in current Python
try:
    from PIL import Image
except ImportError:
    comfy_py = "/home/chihmin/src/ComfyUI/.venv/bin/python"
    flux_py = "/home/chihmin/models-work/flux2/.venv-rocm72/bin/python"
    if os.path.exists(comfy_py) and sys.executable != comfy_py:
        os.execv(comfy_py, [comfy_py] + sys.argv)
    elif os.path.exists(flux_py) and sys.executable != flux_py:
        os.execv(flux_py, [flux_py] + sys.argv)
    else:
        raise

COMFY_DEFAULT_URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
DEFAULT_OUTPUT_DIR = Path("/home/chihmin/models-work/flux2/output/qwen-image")

UNET_NAME = "qwen_image_2.1_int8_convrot.safetensors"
CLIP_NAME = "qwen3vl_8b_int8_convrot.safetensors"
VAE_NAME = "qwen_image_2.1_vae_bf16.safetensors"

DEFAULT_NEGATIVE_PROMPT = (
    "malformed hands, extra fingers, missing fingers, fused fingers, duplicated fingers, "
    "branching fingers, webbed fingers, broken finger joints, misplaced thumbs, twisted wrists, "
    "bad anatomy, bad hands, mutated hands, poorly drawn hands, disfigured fingers, "
    "irregular finger count, cropped shoes, cropped head, cropped ears"
)

# Base generation sizes optimized for Qwen-Image-2.1's 1024-scale latent patch geometry
# and target resolutions for Lanczos-3 super-sampling.
ASPECT_RATIOS = {
    "16:9": {"base": (1280, 704), "target": (1920, 1080)},
    "9:16": {"base": (704, 1280), "target": (1080, 1920)},
    "1:1": {"base": (1024, 1024), "target": (1440, 1440)},
    "4:3": {"base": (1152, 864), "target": (1600, 1200)},
    "3:4": {"base": (864, 1152), "target": (1200, 1600)},
    "3:2": {"base": (1216, 800), "target": (1800, 1200)},
    "2:3": {"base": (800, 1216), "target": (1200, 1800)},
    "21:9": {"base": (1536, 640), "target": (2560, 1080)},
}

# Direct unscaled generation sizes (for --native-1080p)
NATIVE_RESOLUTIONS = {
    "16:9": {"gen": (1920, 1088), "target": (1920, 1080)},
    "9:16": {"gen": (1088, 1920), "target": (1080, 1920)},
    "1:1": {"gen": (1536, 1536), "target": (1536, 1536)},
    "4:3": {"gen": (1600, 1200), "target": (1600, 1200)},
    "3:4": {"gen": (1200, 1600), "target": (1200, 1600)},
    "3:2": {"gen": (1824, 1216), "target": (1800, 1200)},
    "2:3": {"gen": (1216, 1824), "target": (1200, 1800)},
    "21:9": {"gen": (2560, 1088), "target": (2560, 1080)},
}


def log(msg: str):
    """Log to stderr so stdout remains clean JSON."""
    sys.stderr.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    sys.stderr.flush()


def check_comfy_health(url: str, timeout: float = 5.0) -> bool:
    try:
        req = urllib.request.Request(f"{url}/system_stats")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def api_get(url: str, path: str, timeout: float = 30.0):
    with urllib.request.urlopen(url + path, timeout=timeout) as r:
        return json.load(r)


def api_post(url: str, path: str, payload: dict, timeout: float = 30.0):
    req = urllib.request.Request(
        url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def build_workflow(
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    seed: int,
    steps: int = 25,
    cfg: float = 1.0,
    prefix: str = "qwen21",
) -> dict:
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": UNET_NAME,
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": CLIP_NAME,
                "type": "qwen_image",
                "device": "default",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": VAE_NAME,
            },
        },
        "4": {
            "class_type": "TextEncodeQwenImage21",
            "inputs": {
                "clip": ["2", 0],
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "resolution": 1024,
            },
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1,
            },
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["4", 1],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "7": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["6", 0],
                "vae": ["3", 0],
            },
        },
        "8": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": prefix,
                "images": ["7", 0],
            },
        },
    }


def wait_for_prompt(url: str, prompt_id: str, timeout: float = 600.0):
    start = time.time()
    while time.time() - start < timeout:
        try:
            hist = api_get(url, f"/history/{prompt_id}")
            if prompt_id in hist:
                entry = hist[prompt_id]
                outputs = entry.get("outputs", {})
                files = []
                for _, node_out in outputs.items():
                    if "images" in node_out:
                        for img_meta in node_out["images"]:
                            fn = img_meta["filename"]
                            sub = img_meta.get("subfolder", "")
                            typ = img_meta.get("type", "output")
                            files.append((fn, sub, typ))
                if files:
                    return files
        except Exception:
            pass
        time.sleep(1.5)
    raise TimeoutError(f"Prompt {prompt_id} timed out after {timeout:.0f}s")


def download_image(url: str, fn: str, sub: str, typ: str) -> Image.Image:
    params = urllib.parse.urlencode({"filename": fn, "subfolder": sub, "type": typ})
    with urllib.request.urlopen(f"{url}/view?{params}", timeout=30.0) as r:
        return Image.open(io.BytesIO(r.read())).convert("RGBA")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate images with Qwen-Image-2.1 via ComfyUI (ROCm APU optimized)."
    )
    parser.add_argument("prompt", type=str, help="Text prompt (Chinese, English, or mixed)")
    parser.add_argument(
        "--negative-prompt", "-n", type=str, default=DEFAULT_NEGATIVE_PROMPT,
        help="Negative prompt for filtering unwanted elements"
    )
    parser.add_argument(
        "--aspect-ratio", "-a", type=str, default="16:9",
        choices=list(ASPECT_RATIOS.keys()),
        help="Image aspect ratio (default: 16:9)"
    )
    parser.add_argument(
        "--native-1080p", action="store_true",
        help="Generate directly at full 1080p latent without Lanczos upscaling (slower, ~350s)"
    )
    parser.add_argument(
        "--base-only", "--fast", action="store_true",
        help="Output raw base latent resolution without upscaling (fastest)"
    )
    parser.add_argument(
        "--seed", "-s", type=int, default=None,
        help="Random seed for deterministic generation (default: random int)"
    )
    parser.add_argument(
        "--steps", type=int, default=None,
        help="Sampling steps (default: 25 for supersample, 30 for native-1080p)"
    )
    parser.add_argument(
        "--cfg", type=float, default=1.0,
        help="Classifier-Free Guidance scale (default: 1.0)"
    )
    parser.add_argument(
        "--width", type=int, default=None,
        help="Custom width in pixels (overrides aspect ratio)"
    )
    parser.add_argument(
        "--height", type=int, default=None,
        help="Custom height in pixels (overrides aspect ratio)"
    )
    parser.add_argument(
        "--output-dir", "-o", type=Path, default=DEFAULT_OUTPUT_DIR,
        help="Directory to save generated image"
    )
    parser.add_argument(
        "--prefix", "-p", type=str, default="qwen21",
        help="Filename prefix for generated image"
    )
    parser.add_argument(
        "--comfy-url", type=str, default=COMFY_DEFAULT_URL,
        help=f"ComfyUI API endpoint (default: {COMFY_DEFAULT_URL})"
    )
    parser.add_argument(
        "--timeout", type=float, default=600.0,
        help="Generation timeout in seconds (default: 600)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Verify ComfyUI health
    if not check_comfy_health(args.comfy_url):
        log(f"ERROR: Cannot connect to ComfyUI at {args.comfy_url}")
        log("Hint: Verify comfyui.service status with `systemctl --user status comfyui` or restart via `/restart-service`.")
        sys.exit(1)

    seed = args.seed if args.seed is not None else random.randint(1, 2147483647)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Resolution determination
    if args.width and args.height:
        # Custom explicit dimensions
        gen_w = (args.width // 16) * 16
        gen_h = (args.height // 16) * 16
        target_w, target_h = args.width, args.height
        mode = "custom"
        steps = args.steps if args.steps is not None else 25
    elif args.native_1080p:
        # Direct native resolution
        nat_cfg = NATIVE_RESOLUTIONS.get(args.aspect_ratio, NATIVE_RESOLUTIONS["16:9"])
        gen_w, gen_h = nat_cfg["gen"]
        target_w, target_h = nat_cfg["target"]
        mode = "native_1080p"
        steps = args.steps if args.steps is not None else 30
    else:
        # Default optimized two-stage super-sampling
        ar_cfg = ASPECT_RATIOS.get(args.aspect_ratio, ASPECT_RATIOS["16:9"])
        gen_w, gen_h = ar_cfg["base"]
        target_w, target_h = ar_cfg["target"] if not args.base_only else ar_cfg["base"]
        mode = "base_only" if args.base_only else "supersample"
        steps = args.steps if args.steps is not None else 25

    log(f"Target Aspect Ratio: {args.aspect_ratio}")
    log(f"Mode: {mode} (Latent: {gen_w}x{gen_h}, Target: {target_w}x{target_h}, Steps: {steps}, Seed: {seed})")
    log(f"Prompt: {args.prompt}")

    wf = build_workflow(
        prompt=args.prompt,
        negative_prompt=args.negative_prompt,
        width=gen_w,
        height=gen_h,
        seed=seed,
        steps=steps,
        cfg=args.cfg,
        prefix=args.prefix,
    )

    client_id = str(uuid.uuid4())
    t0 = time.time()
    try:
        res = api_post(args.comfy_url, "/prompt", {"prompt": wf, "client_id": client_id})
    except urllib.error.URLError as e:
        log(f"Failed to submit prompt to ComfyUI: {e}")
        sys.exit(1)

    prompt_id = res.get("prompt_id")
    log(f"Queued ComfyUI job {prompt_id}, generating...")

    image_metas = wait_for_prompt(args.comfy_url, prompt_id, timeout=args.timeout)
    gen_time = time.time() - t0
    log(f"Inference completed in {gen_time:.2f}s")

    fn, sub, typ = image_metas[0]
    im = download_image(args.comfy_url, fn, sub, typ)

    # Post-processing: cropping / Lanczos upscaling if needed
    if mode == "native_1080p":
        # Center-crop gen size to exact target if needed (e.g. 1920x1088 -> 1920x1080)
        if im.height > target_h:
            top = (im.height - target_h) // 2
            im = im.crop((0, top, im.width, top + target_h))
        if im.width > target_w:
            left = (im.width - target_w) // 2
            im = im.crop((left, 0, left + target_w, im.height))
    elif mode == "supersample" and (im.width != target_w or im.height != target_h):
        im = im.resize((target_w, target_h), Image.Resampling.LANCZOS)

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_name = f"{args.prefix}_{args.aspect_ratio.replace(':', 'x')}_{ts}_{im.width}x{im.height}.png"
    out_path = args.output_dir / out_name
    im.save(out_path)
    log(f"Saved image to: {out_path}")

    # Output JSON summary
    summary = {
        "final_path": str(out_path),
        "size": [im.width, im.height],
        "aspect_ratio": args.aspect_ratio,
        "seed": seed,
        "steps": steps,
        "cfg": args.cfg,
        "mode": mode,
        "gen_time": round(gen_time, 2),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    log(f"Attachment tag: [[image: {out_path}]]")


if __name__ == "__main__":
    main()
