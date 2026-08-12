#!/usr/bin/env python3
"""Generate Anima storyboard frames with ControlNet-LLLite structure guidance."""

import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anima  # noqa: E402

DEFAULT_MODEL_PATCH = "anima-lllite-any-test-like-v2.safetensors"
DEFAULT_STRENGTH = 0.4
DEFAULT_END_PERCENT = 0.5


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate consistent anime storyboard frames with Anima ControlNet-LLLite"
    )
    parser.add_argument("prompt", help="Describe character identity, action, camera, and new scene")
    parser.add_argument("--reference", required=True, help="Character reference image")
    parser.add_argument("--aspect-ratio", "--ar", default="16:9")
    parser.add_argument("--output-size", default=None,
                        help="Exact generation and output canvas as WIDTHxHEIGHT, e.g. 864x480")
    parser.add_argument("--strength", type=float, default=DEFAULT_STRENGTH,
                        help="LLLite structure strength; 0.3-0.5 allows scene/camera changes")
    parser.add_argument("--end-percent", type=float, default=DEFAULT_END_PERCENT,
                        help="Stop structural guidance at this fraction of sampling")
    parser.add_argument("--steps", type=int, default=anima.ANIME_STEPS)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--guidance-scale", type=float, default=anima.ANIME_CFG)
    parser.add_argument("--native-1080p", action="store_true")
    parser.add_argument("--model-patch", default=DEFAULT_MODEL_PATCH)
    parser.add_argument("--out-dir", default="/home/chihmin/models-work/flux2/output/create-image")
    parser.add_argument("--prefix", default=None)
    return parser.parse_args(argv)


def resolve_output_sizes(output_size: str | None, aspect_ratio: str,
                         native: bool) -> tuple[int, int, int, int, str]:
    if output_size is None:
        return anima.resolve_anime_sizes(aspect_ratio, native=native)
    try:
        width_text, height_text = output_size.lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (AttributeError, ValueError) as exc:
        raise ValueError("--output-size must use WIDTHxHEIGHT, e.g. 864x480") from exc
    if width <= 0 or height <= 0 or width % 16 or height % 16:
        raise ValueError("--output-size dimensions must be positive multiples of 16")
    return width, height, width, height, f"{width}:{height}"


def prepare_control_image(reference: Path, width: int, height: int) -> Image.Image:
    """Create the verified grayscale structure control used for scene replacement."""
    image = ImageOps.exif_transpose(Image.open(reference)).convert("RGB")
    image = anima._cover_resize(image, width, height).convert("L")
    image = ImageEnhance.Contrast(image).enhance(0.8)
    image = image.filter(ImageFilter.GaussianBlur(0.6))
    return image.convert("RGB")


def build_lllite_workflow(prompt: str, image_name: str, gen_w: int, gen_h: int,
                           seed: int, steps: int, strength: float, end_percent: float,
                           loras: list, trigger: str,
                           model_patch: str = DEFAULT_MODEL_PATCH,
                           cfg: float = anima.ANIME_CFG) -> dict:
    lora_nodes, model_ref, clip_ref = anima._lora_chain(loras)
    workflow = {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": anima.ANIMA_UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": anima.ANIMA_CLIP, "type": "qwen_image"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": anima.ANIMA_VAE}},
        "6": {"class_type": "ModelPatchLoader", "inputs": {"name": model_patch}},
        "7": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "8": {"class_type": "AnimaLLLiteApply", "inputs": {
            "model": model_ref,
            "model_patch": ["6", 0],
            "image": ["7", 0],
            "strength": strength,
            "start_percent": 0.0,
            "end_percent": end_percent,
        }},
        "9": {"class_type": "CLIPTextEncode", "inputs": {
            "clip": clip_ref, "text": trigger + prompt}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {
            "clip": clip_ref,
            "text": "extra arms, extra legs, duplicate person, malformed hands, deformed anatomy",
        }},
        "11": {"class_type": "EmptySD3LatentImage", "inputs": {
            "width": gen_w, "height": gen_h, "batch_size": 1}},
        "12": {"class_type": "KSampler", "inputs": {
            "model": ["8", 0],
            "positive": ["9", 0],
            "negative": ["10", 0],
            "latent_image": ["11", 0],
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": anima.ANIME_SAMPLER,
            "scheduler": anima.ANIME_SCHEDULER,
            "denoise": 1.0,
        }},
        "13": {"class_type": "VAEDecode", "inputs": {
            "samples": ["12", 0], "vae": ["3", 0]}},
        "14": {"class_type": "SaveImage", "inputs": {
            "images": ["13", 0], "filename_prefix": "anima_lllite"}},
    }
    workflow.update(lora_nodes)
    return workflow


def _wait_for_image(prompt_id: str, timeout: int = 1200) -> dict:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        try:
            history = anima._get(f"/history/{prompt_id}")
        except Exception:
            history = {}
        if prompt_id in history:
            item = history[prompt_id]
            status = item["status"]
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI generation failed: {status}")
            if status.get("completed"):
                images = [
                    image
                    for output in item.get("outputs", {}).values()
                    for image in output.get("images", [])
                ]
                if not images:
                    raise RuntimeError("ComfyUI completed without an image")
                return images[-1]
        time.sleep(3)
    raise TimeoutError("ComfyUI generation timed out")


def run(args) -> int:
    reference = Path(args.reference).expanduser().resolve()
    patch = Path(anima.COMFY_DIR) / "models" / "model_patches" / args.model_patch
    if not reference.is_file():
        print(json.dumps({"error": f"reference image not found: {reference}"}))
        return 2
    if not patch.is_file():
        print(json.dumps({"error": f"LLLite model patch not found: {patch}"}))
        return 2
    if not 0.0 <= args.end_percent <= 1.0:
        print(json.dumps({"error": "--end-percent must be between 0 and 1"}))
        return 2

    ready, owned_process = anima.ensure_comfy()
    if not ready:
        print(json.dumps({"error": "ComfyUI did not become ready on 127.0.0.1:8188"}))
        return 1

    try:
        gen_w, gen_h, final_w, final_h, aspect = resolve_output_sizes(
            args.output_size, args.aspect_ratio, native=args.native_1080p)
        control = prepare_control_image(reference, gen_w, gen_h)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_name = anima._upload_image(control, f"anima_lllite_control_{stamp}.png")
        seed = args.seed if args.seed is not None else int(time.time()) % (2**31)

        loras = [(anima.ANIMA_LORA, anima.ANIME_LORA_STRENGTH)]
        trigger = anima.ANIMA_TRIGGER
        aniani_path = Path(anima.COMFY_DIR) / "models" / "loras" / anima.ANIANI_LORA
        if aniani_path.is_file():
            loras.append((anima.ANIANI_LORA, anima.ANIANI_STRENGTH))
            trigger += anima.ANIANI_TRIGGER

        workflow = build_lllite_workflow(
            args.prompt, image_name, gen_w, gen_h, seed, args.steps,
            args.strength, args.end_percent, loras, trigger,
            model_patch=args.model_patch, cfg=args.guidance_scale,
        )
        prompt_id = anima._post(
            "/prompt", {"prompt": workflow, "client_id": str(uuid.uuid4())}
        )["prompt_id"]
        image = anima._fetch_image(_wait_for_image(prompt_id))

        output_dir = Path(args.out_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        prefix = args.prefix or f"anima_lllite_storyboard_{stamp}"
        raw_path = output_dir / f"{prefix}_raw_{gen_w}x{gen_h}.png"
        final_path = output_dir / f"{prefix}_{final_w}x{final_h}.png"
        image.save(raw_path)
        if args.native_1080p:
            left = (image.width - final_w) // 2
            top = (image.height - final_h) // 2
            final = image.crop((left, top, left + final_w, top + final_h))
        else:
            final = image.resize((final_w, final_h), Image.Resampling.LANCZOS)
        final.save(final_path)

        result = {
            "backend": "comfyui-anima-lllite",
            "model_patch": args.model_patch,
            "reference": str(reference),
            "prompt": args.prompt,
            "seed": seed,
            "steps": args.steps,
            "strength": args.strength,
            "end_percent": args.end_percent,
            "aspect_ratio": aspect,
            "generated_size": [gen_w, gen_h],
            "final_size": [final_w, final_h],
            "raw_path": str(raw_path.resolve()),
            "final_path": str(final_path.resolve()),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        anima.stop_comfy(owned_process)


def main(argv=None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
