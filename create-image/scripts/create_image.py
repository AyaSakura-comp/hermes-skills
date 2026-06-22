#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import torch
from diffusers import Flux2KleinPipeline
from PIL import Image, ImageOps

MODEL_ID_4B = "black-forest-labs/FLUX.2-klein-4B"
MODEL_ID_9B_KV = "black-forest-labs/FLUX.2-klein-9B-kv"
DEFAULT_PROMPT = "a cozy Japanese summer mountain cafe at sunset, warm beige tones, soft watercolor, detailed, peaceful atmosphere"

# ROCm/VAE buckets discovered empirically on this AMD iGPU setup.
# Default quality now uses 9B-KV at 1360x768 then upscales to 1080p.
# Fast preview keeps the old 4B 1024x576 path.
# Native/high-quality generates 1920x1088 because model dimensions must be divisible by 16,
# then center-crops to exact 1920x1080.
FAST_PREVIEW_OUTPUT_SIZE = (1024, 576)
DEFAULT_9B_OUTPUT_SIZE = (1360, 768)
FAST_REFERENCE_SIZE = (768, 432)
NATIVE_OUTPUT_SIZE = (1920, 1088)
FINAL_SIZE = (1920, 1080)
DEFAULT_FLUX_ASPECT_RATIO = "16:9"
FLUX_FINAL_SIZE_BY_ASPECT = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "3:2": (1776, 1184),
    "2:3": (1184, 1776),
    "4:3": (1664, 1248),
    "3:4": (1248, 1664),
    "1:1": (1440, 1440),
}
FLUX_9B_GEN_SIZE_BY_ASPECT = {
    "16:9": DEFAULT_9B_OUTPUT_SIZE,
    "9:16": (768, 1360),
    "3:2": (1248, 832),
    "2:3": (832, 1248),
    "4:3": (1184, 880),
    "3:4": (880, 1184),
    "1:1": (1024, 1024),
}
DEFAULT_DAEMON_URL = "http://127.0.0.1:7862"


def sync():
    if torch.cuda.is_available():
        torch.cuda.synchronize()


def save_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def round_to_multiple(value: float, multiple: int = 16) -> int:
    return max(multiple, int(round(value / multiple)) * multiple)


def parse_size(value: str) -> tuple[int, int]:
    width_str, height_str = value.lower().split("x", 1)
    return int(width_str), int(height_str)


def normalize_aspect_ratio(value: str | None, default: str = DEFAULT_FLUX_ASPECT_RATIO) -> str:
    if not value:
        return default
    v = value.strip().lower().replace("x", ":").replace("/", ":")
    aliases = {
        "portrait": "2:3",
        "vertical": "2:3",
        "tall": "2:3",
        "landscape": "16:9",
        "wide": "16:9",
        "square": "1:1",
    }
    v = aliases.get(v, v)
    if ":" not in v:
        raise ValueError(f"aspect ratio must look like 2:3, 16:9, or square; got {value!r}")
    left, right = v.split(":", 1)
    w, h = int(left), int(right)
    if w <= 0 or h <= 0:
        raise ValueError(f"aspect ratio dimensions must be positive; got {value!r}")
    from math import gcd
    g = gcd(w, h)
    return f"{w // g}:{h // g}"


def size_for_aspect(area_pixels: int, aspect_ratio: str) -> tuple[int, int]:
    w_ratio, h_ratio = (int(part) for part in aspect_ratio.split(":", 1))
    h = (area_pixels * h_ratio / w_ratio) ** 0.5
    w = h * w_ratio / h_ratio
    return round_to_multiple(w), round_to_multiple(h)


def resolve_flux_sizes(model_label: str, aspect_ratio: str | None, native: bool = False) -> tuple[int, int, int, int, str]:
    aspect = normalize_aspect_ratio(aspect_ratio)
    final_w, final_h = FLUX_FINAL_SIZE_BY_ASPECT.get(aspect, size_for_aspect(1920 * 1080, aspect))
    if native:
        gen_w, gen_h = round_to_multiple(final_w), round_to_multiple(final_h)
    elif model_label == "4b":
        gen_w, gen_h = size_for_aspect(FAST_PREVIEW_OUTPUT_SIZE[0] * FAST_PREVIEW_OUTPUT_SIZE[1], aspect)
    else:
        gen_w, gen_h = FLUX_9B_GEN_SIZE_BY_ASPECT.get(
            aspect, size_for_aspect(DEFAULT_9B_OUTPUT_SIZE[0] * DEFAULT_9B_OUTPUT_SIZE[1], aspect))
    return gen_w, gen_h, final_w, final_h, aspect


def should_try_daemon(args, model_label: str) -> bool:
    # Warm daemon is DISABLED by default: keeping FLUX.2 9B resident alongside
    # other local models (qwen-mtp, ComfyUI/Anima) OOMs the box. Opt back in with
    # env CREATE_IMAGE_USE_DAEMON=1 only if you've freed enough memory.
    return (
        model_label == "9b-kv"
        and not getattr(args, "no_daemon", False)
        and os.environ.get("CREATE_IMAGE_USE_DAEMON") == "1"
    )


def build_daemon_payload(args, mode: str) -> dict:
    return {
        "prompt": args.prompt,
        "image": args.image,
        "seed": args.seed,
        "steps": args.steps,
        "guidance_scale": args.guidance_scale,
        "native_1080p": args.native_1080p,
        "no_auto_lora": args.no_auto_lora,
        "lora_scale": args.lora_scale,
        "out_dir": args.out_dir,
        "prefix": args.prefix,
        "output_size": args.output_size,
        "aspect_ratio": getattr(args, "aspect_ratio", None),
        "mode": mode,
    }


def call_daemon(url: str, payload: dict, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url.rstrip("/") + "/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def main():
    parser = argparse.ArgumentParser(description="Generate or edit images with local FLUX.2 on ROCm 7.2")
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT)
    parser.add_argument("--image", default=None, help="Optional reference image for FLUX.2 image editing")
    parser.add_argument("--fast-preview", "--preview", action="store_true", help="Use the faster 4B model at 1024x576 before 1080p upscale")
    parser.add_argument("--model", choices=("auto", "4b", "9b"), default="auto", help="Override model selection; auto uses 9B by default or 4B for --fast-preview")
    parser.add_argument("--no-daemon", action="store_true", help="Disable the local warm 9B daemon and run in-process")
    parser.add_argument("--daemon-url", default=DEFAULT_DAEMON_URL, help="Local warm daemon URL")
    parser.add_argument("--daemon-timeout", type=float, default=3600.0, help="Seconds to wait for daemon generation")
    parser.add_argument("--native-1080p", "--native", "--high-res", "--high-quality", action="store_true", dest="native_1080p")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--guidance-scale", type=float, default=1.0)
    parser.add_argument("--no-auto-lora", action="store_true", help="Disable automatic style LoRA loading")
    parser.add_argument("--lora-scale", type=float, default=0.8, help="Adapter weight for auto-loaded LoRAs")
    parser.add_argument("--out-dir", default="/home/chihmin/models-work/flux2/output/create-image")
    parser.add_argument("--prefix", default=None)
    parser.add_argument("--output-size", default=None, help="Output size as WxH (e.g. 1080x1440 for 3:4). Overrides native/upscale sizing.")
    parser.add_argument("--aspect-ratio", "--ar", default=None,
                        help="Output aspect ratio such as 2:3, 3:2, 16:9, 1:1, portrait, landscape. Anime defaults to 2:3; FLUX defaults to 16:9.")
    parser.add_argument("--anime", "--anime-mode", "--二次元", action="store_true", dest="anime",
                        help="Anime/二次元 path: ComfyUI + Anima + @gpt-image-2 LoRA. Default 720p->Lanczos 1080p; --native-1080p for native.")
    parser.add_argument("--strength", type=float, default=None,
                        help="Anime img2img denoise strength (with --anime --image): higher = more anime/less faithful to the photo. Default 0.65.")
    parser.add_argument("--flux", action="store_true", dest="force_flux",
                        help="Force the FLUX.2 backend even when --anime is given.")
    parser.add_argument("--loras", default=None,
                        help="Anime: explicit LoRA chain 'name:strength,name2:strength2' (Anima-base LoRAs only). Overrides the auto chain.")
    args = parser.parse_args()

    # Anime/二次元 requests go to the ComfyUI + Anima backend, not FLUX.2.
    if args.anime and not args.force_flux:
        from anima import run_anime
        sys.exit(run_anime(args))

    is_edit = args.image is not None
    if args.model == "4b" or (args.model == "auto" and args.fast_preview):
        model_id = MODEL_ID_4B
        model_label = "4b"
    else:
        model_id = MODEL_ID_9B_KV
        model_label = "9b-kv"

    gen_w, gen_h, final_w, final_h, aspect_ratio = resolve_flux_sizes(
        model_label, args.aspect_ratio, native=args.native_1080p)
    if args.output_size:
        final_w, final_h = parse_size(args.output_size)

    if args.output_size:
        mode = ("edit-" if is_edit else "") + f"{model_label}-custom-{args.output_size}"
    elif args.native_1080p:
        mode = ("edit-" if is_edit else "") + f"{model_label}-native-{aspect_ratio.replace(':', 'x')}"
    elif model_label == "4b":
        mode = ("edit-" if is_edit else "") + f"4b-fast-preview-{aspect_ratio.replace(':', 'x')}"
    else:
        mode = ("edit-" if is_edit else "") + f"9b-default-{aspect_ratio.replace(':', 'x')}-upscale"

    ref_w, ref_h = FAST_REFERENCE_SIZE
    seed = args.seed if args.seed is not None else int(time.time()) % (2**31)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = args.prefix or f"flux2_{mode}_{timestamp}"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"{prefix}_raw_{gen_w}x{gen_h}.png"
    if args.output_size or is_edit:
        final_path = out_dir / f"{prefix}_{final_w}x{final_h}.png"
    else:
        final_path = out_dir / f"{prefix}_1080p.png"
    meta_path = out_dir / f"{prefix}_timing.json"

    if should_try_daemon(args, model_label):
        try:
            daemon_result = call_daemon(args.daemon_url, build_daemon_payload(args, mode), args.daemon_timeout)
            print(json.dumps(daemon_result, ensure_ascii=False, indent=2))
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, OSError) as exc:
            print(f"[create-image] warm daemon unavailable, falling back to in-process generation: {type(exc).__name__}: {exc}", file=sys.stderr)

    os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
    os.environ.setdefault("TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL", "1")

    timings = {}
    t0 = time.perf_counter()
    pipe = Flux2KleinPipeline.from_pretrained(model_id, torch_dtype=torch.bfloat16)
    sync(); timings["load_pipeline_seconds"] = time.perf_counter() - t0

    t = time.perf_counter()
    pipe = pipe.to("cuda")
    sync(); timings["move_to_gpu_seconds"] = time.perf_counter() - t

    reference_image = None
    if is_edit:
        src = ImageOps.exif_transpose(Image.open(args.image)).convert("RGB")
        src_fit = ImageOps.contain(src, (ref_w, ref_h), Image.Resampling.LANCZOS)
        reference_image = Image.new("RGB", (ref_w, ref_h), (245, 240, 232))
        reference_image.paste(src_fit, ((ref_w - src_fit.width) // 2, (ref_h - src_fit.height) // 2))

    generator = torch.Generator(device="cuda").manual_seed(seed)
    t = time.perf_counter()
    with torch.inference_mode():
        call_kwargs = {
            "prompt": args.prompt,
            "width": gen_w,
            "height": gen_h,
            "num_inference_steps": args.steps,
            "guidance_scale": args.guidance_scale,
            "generator": generator,
        }
        if reference_image is not None:
            call_kwargs["image"] = reference_image
        image = pipe(**call_kwargs).images[0]
    sync(); timings["generate_seconds"] = time.perf_counter() - t

    t = time.perf_counter()
    image.save(raw_path)
    timings["save_raw_seconds"] = time.perf_counter() - t

    t = time.perf_counter()
    if args.native_1080p and final_w <= gen_w and final_h <= gen_h:
        # Model dimensions must be divisible by 16. Generate 1920x1088, crop center to exact 1080p.
        # This intentionally leaves the upscaled output buckets and is expected to be much slower.
        left = (gen_w - final_w) // 2
        top = (gen_h - final_h) // 2
        final = image.crop((left, top, left + final_w, top + final_h))
    else:
        final = image.resize((final_w, final_h), Image.Resampling.LANCZOS)
    timings["postprocess_seconds"] = time.perf_counter() - t

    t = time.perf_counter()
    final.save(final_path)
    timings["save_final_seconds"] = time.perf_counter() - t
    timings["end_to_end_seconds"] = sum(timings.values())
    timings["warm_request_seconds"] = timings["generate_seconds"] + timings["postprocess_seconds"] + timings["save_final_seconds"]

    meta = {
        "model": model_id,
        "model_label": model_label,
        "fast_preview": args.fast_preview,
        "native_1080p": args.native_1080p,
        "mode": mode,
        "prompt": args.prompt,
        "seed": seed,
        "steps": args.steps,
        "guidance_scale": args.guidance_scale,
        "generated_size": [gen_w, gen_h],
        "aspect_ratio": aspect_ratio,
        "reference_size": [ref_w, ref_h] if is_edit else None,
        "final_size": [final_w, final_h],
        "input_image": str(Path(args.image).resolve()) if is_edit else None,
        "torch": torch.__version__,
        "hip": getattr(torch.version, "hip", None),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "timings": timings,
        "raw_path": str(raw_path.resolve()),
        "final_path": str(final_path.resolve()),
    }
    save_json(meta_path, meta)

    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
