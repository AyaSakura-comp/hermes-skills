#!/usr/bin/env python3
"""Anime (二次元) image path for create-image, via the local ComfyUI + Anima.

Separate from the FLUX.2 path: anime requests use the Anima checkpoint
(Cosmos-Predict2-2B finetune) + the @gpt-image-2 style LoRA, driven through
ComfyUI's HTTP API (so this needs only urllib + PIL, not torch/diffusers).

Modes:
  - default      : generate 1280x720 (in-distribution) then Lanczos -> 1920x1080.
                   No hi-res fix (a 2nd diffusion pass barely saves time on this
                   GPU and isn't worth it — see HANDOFF benchmarks).
  - native 1080p : generate 1920x1088 directly then center-crop to 1920x1080
                   (high quality, ~4x slower; use only when explicitly asked).

ComfyUI is started on demand if not already running.
"""
import io
import json
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image

COMFY_URL = "http://127.0.0.1:8188"
COMFY_DIR = "/home/chihmin/src/ComfyUI"

ANIMA_UNET = "anima_baseV10.safetensors"
ANIMA_CLIP = "anima_baseV10_txt.safetensors"
ANIMA_VAE = "qwen_image_vae.safetensors"
ANIMA_LORA = "gpt-image-2_anima-base1_v1-1.safetensors"
ANIMA_TRIGGER = "@gpt-image-2, "

# PVC figure style: this Anima version (Civitai 338712 / v2998722) is a full fine-tuned
# CHECKPOINT (~4 GB DiT), not a LoRA — so for PVC we SWAP the base diffusion model to it and
# keep the @gpt-image-2 LoRA on top.
PVC_UNET = "PVCStyleModelMovable_anima10.safetensors"
PVC_TRIGGER = "pvc figure, pvc style, "
PVC_KEYWORDS = ("pvc", "figurine", "手辦", "手办", "フィギュア", "figma")

# Lighting / volumetric glow: Anima-base LoRA (Civitai 2633578 / v2976629, "Volumetric Glow").
# Chained after @gpt-image-2 when the prompt emphasizes lighting; its recommended prompt words
# (trigger kinrolstyle + the creator's atmospheric keywords) are prepended for best results.
LIGHTING_LORA = "Volumetric_glow_v2.0.safetensors"
LIGHTING_TRIGGER = "kinrolstyle, volumetric glow, soft cinematic lighting, dreamlike atmosphere, luminous materials, "
LIGHTING_STRENGTH = 0.8
LIGHTING_KEYWORDS = ("光影", "光線", "打光", "光照", "戲劇光", "戏剧光", "發光", "glow", "volumetric",
                     "dramatic lighting", "dramatic light", "cinematic lighting", "chiaroscuro",
                     "rim light", "volumetric light", "lighting")

DEFAULT_GEN_SIZE = (1280, 720)     # 720p, inside Anima's 512-1536 trained range
NATIVE_GEN_SIZE = (1920, 1088)     # /16-aligned; crop to 1080p
FINAL_SIZE = (1920, 1080)

ANIME_STEPS = 30
ANIME_CFG = 5.0
ANIME_SAMPLER = "er_sde"
ANIME_SCHEDULER = "simple"
ANIME_LORA_STRENGTH = 1.0
ANIME_IMG2IMG_DENOISE = 0.65       # photo->anime: keep structure, restyle

# Aspect-aware /16-aligned buckets for img2img (avoid arbitrary slow ROCm VAE shapes).
# (gen_size, final_size) chosen so the photo's orientation is preserved.
IMG2IMG_BUCKETS = {
    "landscape": ((1280, 720), (1920, 1080)),
    "portrait": ((720, 1280), (1080, 1920)),
    "square": ((1024, 1024), (1536, 1536)),
}


def _get(path: str, timeout: float = 30.0):
    with urllib.request.urlopen(COMFY_URL + path, timeout=timeout) as r:
        return json.load(r)


def _post(path: str, payload: dict, timeout: float = 30.0):
    req = urllib.request.Request(
        COMFY_URL + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _server_up() -> bool:
    try:
        urllib.request.urlopen(COMFY_URL + "/", timeout=3)
        return True
    except Exception:
        return False


def ensure_comfy(wait_seconds: int = 180) -> bool:
    """Return True if ComfyUI is reachable, starting it detached if needed."""
    if _server_up():
        return True
    subprocess.Popen(
        [f"{COMFY_DIR}/.venv/bin/python", "main.py", "--listen", "127.0.0.1", "--port", "8188"],
        cwd=COMFY_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if _server_up():
            return True
        time.sleep(3)
    return False


def _lora_chain(loras: list) -> tuple:
    """Build a chain of LoraLoader nodes from UNET(1)/CLIP(2). loras = [(name, strength), ...].
    Returns (nodes_dict, model_ref, clip_ref) — the last loader's outputs feed the sampler/encode."""
    nodes = {}
    model_ref, clip_ref = ["1", 0], ["2", 0]
    for i, (name, strength) in enumerate(loras):
        nid = f"L{i}"
        nodes[nid] = {"class_type": "LoraLoader", "inputs": {
            "model": model_ref, "clip": clip_ref, "lora_name": name,
            "strength_model": strength, "strength_clip": strength}}
        model_ref, clip_ref = [nid, 0], [nid, 1]
    return nodes, model_ref, clip_ref


def _build_workflow(prompt: str, gen_w: int, gen_h: int, seed: int, steps: int,
                    cfg: float, loras: list, trigger: str, unet: str = ANIMA_UNET) -> dict:
    text = trigger + prompt
    lnodes, m, c = _lora_chain(loras)
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": ANIMA_CLIP, "type": "qwen_image"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": ANIMA_VAE}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": c, "text": text}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": c, "text": ""}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": gen_w, "height": gen_h, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {
            "model": m, "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0],
            "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": ANIME_SAMPLER, "scheduler": ANIME_SCHEDULER, "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "anima"}},
    }
    wf.update(lnodes)
    return wf


def _upload_image(img: Image.Image, name: str) -> str:
    """Upload a PIL image to ComfyUI's input folder; return the stored filename."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    boundary = "----animaboundary" + uuid.uuid4().hex
    body = b"".join([
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'.encode(),
        b"Content-Type: image/png\r\n\r\n", data, b"\r\n",
        f'--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'.encode(),
        f"--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        COMFY_URL + "/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
    return (res.get("subfolder", "") + "/" + res["name"]) if res.get("subfolder") else res["name"]


def _cover_resize(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale to cover (w,h) then center-crop — fills the frame, preserves no bars."""
    src_ar, dst_ar = img.width / img.height, w / h
    if src_ar > dst_ar:
        nh = h; nw = round(h * src_ar)
    else:
        nw = w; nh = round(w / src_ar)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _img2img_workflow(prompt: str, image_name: str, gen_w: int, gen_h: int, seed: int,
                      steps: int, cfg: float, denoise: float, loras: list, trigger: str,
                      unet: str = ANIMA_UNET) -> dict:
    text = trigger + prompt
    lnodes, m, c = _lora_chain(loras)
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": ANIMA_CLIP, "type": "qwen_image"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": ANIMA_VAE}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": c, "text": text}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": c, "text": ""}},
        "13": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "14": {"class_type": "VAEEncode", "inputs": {"pixels": ["13", 0], "vae": ["3", 0]}},
        "8": {"class_type": "KSampler", "inputs": {
            "model": m, "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["14", 0],
            "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": ANIME_SAMPLER, "scheduler": ANIME_SCHEDULER, "denoise": denoise}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "anima_i2i"}},
    }
    wf.update(lnodes)
    return wf


def _fetch_image(info: dict) -> Image.Image:
    q = urllib.parse.urlencode({
        "filename": info["filename"],
        "subfolder": info.get("subfolder", ""),
        "type": info.get("type", "output"),
    })
    with urllib.request.urlopen(f"{COMFY_URL}/view?{q}", timeout=60) as r:
        return Image.open(io.BytesIO(r.read())).convert("RGB")


def run_anime(args) -> int:
    """Generate an anime image via ComfyUI+Anima. Prints the result JSON. Returns exit code."""
    timings = {}
    t_all = time.perf_counter()

    t = time.perf_counter()
    if not ensure_comfy():
        print(json.dumps({"error": "ComfyUI (Anima backend) did not become ready on :8188"}))
        return 1
    timings["comfy_ready_seconds"] = time.perf_counter() - t

    native = bool(args.native_1080p)
    is_edit = bool(getattr(args, "image", None))
    seed = args.seed if args.seed is not None else int(time.time()) % (2**31)
    steps = args.steps if args.steps != 4 else ANIME_STEPS  # FLUX default 4 -> Anima 30
    cfg = args.guidance_scale if args.guidance_scale != 1.0 else ANIME_CFG
    lora_strength = args.lora_scale if args.lora_scale != 0.8 else ANIME_LORA_STRENGTH
    denoise = (args.strength if getattr(args, "strength", None) is not None else ANIME_IMG2IMG_DENOISE)

    # Base model + LoRA chain. Default: anima_baseV10 + @gpt-image-2 LoRA. PVC style SWAPS the base
    # to the PVC checkpoint (it's a full fine-tune, not a LoRA) and keeps @gpt-image-2 on top.
    pl = args.prompt.lower()
    unet = ANIMA_UNET
    loras = [(ANIMA_LORA, lora_strength)]
    trigger = ANIMA_TRIGGER
    if any(k in pl or k in args.prompt for k in PVC_KEYWORDS):
        unet = PVC_UNET
        trigger = ANIMA_TRIGGER + PVC_TRIGGER
    # Dramatic lighting -> chain the S1 lighting LoRA after @gpt-image-2 (only if the file exists,
    # so a missing download degrades gracefully to a normal generation).
    if any(k in pl or k in args.prompt for k in LIGHTING_KEYWORDS) and \
            (Path(COMFY_DIR) / "models" / "loras" / LIGHTING_LORA).exists():
        loras.append((LIGHTING_LORA, LIGHTING_STRENGTH))
        trigger = trigger + LIGHTING_TRIGGER
    # Manual override: --loras "name:strength,name2:strength2" (replaces the auto chain).
    if getattr(args, "loras", None):
        loras = []
        for spec in args.loras.split(","):
            spec = spec.strip()
            if not spec:
                continue
            if ":" in spec:
                nm, st = spec.rsplit(":", 1)
                loras.append((nm.strip(), float(st)))
            else:
                loras.append((spec, 1.0))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    uploaded_name = None

    if is_edit:
        # photo -> anime: pick an aspect-preserving /16 bucket, cover-crop, encode, restyle.
        from PIL import ImageOps  # noqa: PLC0415
        src = ImageOps.exif_transpose(Image.open(args.image)).convert("RGB")
        ar = src.width / src.height
        key = "landscape" if ar > 1.15 else "portrait" if ar < 0.87 else "square"
        (gen_w, gen_h), (final_w, final_h) = IMG2IMG_BUCKETS[key]
        prepped = _cover_resize(src, gen_w, gen_h)
        uploaded_name = _upload_image(prepped, f"anima_src_{timestamp}.png")
        mode = f"anima-img2img-{key}-denoise{denoise}"
    else:
        gen_w, gen_h = NATIVE_GEN_SIZE if native else DEFAULT_GEN_SIZE
        final_w, final_h = FINAL_SIZE
        mode = "anima-native-1080p" if native else "anima-720p-upscale-1080p"

    prefix = args.prefix or f"anima_{mode}_{timestamp}"
    raw_path = out_dir / f"{prefix}_raw_{gen_w}x{gen_h}.png"
    final_path = out_dir / f"{prefix}_{final_w}x{final_h}.png"
    meta_path = out_dir / f"{prefix}_timing.json"

    if is_edit:
        wf = _img2img_workflow(args.prompt, uploaded_name, gen_w, gen_h, seed, steps, cfg,
                               denoise, loras, trigger, unet)
    else:
        wf = _build_workflow(args.prompt, gen_w, gen_h, seed, steps, cfg, loras, trigger, unet)
    t = time.perf_counter()
    pid = _post("/prompt", {"prompt": wf, "client_id": str(uuid.uuid4())})["prompt_id"]
    img_info = None
    while True:
        try:
            hist = _get(f"/history/{pid}")
        except Exception:
            # Transient HTTP timeout while the GPU is busy — keep polling.
            hist = {}
        if pid in hist:
            st = hist[pid]["status"]
            if st.get("completed"):
                for node_out in hist[pid]["outputs"].values():
                    for im in node_out.get("images", []):
                        img_info = im
                break
            if st.get("status_str") == "error":
                print(json.dumps({"error": "ComfyUI generation failed", "status": st}))
                return 1
        if time.perf_counter() - t > 1200:
            print(json.dumps({"error": "ComfyUI generation timed out"}))
            return 1
        time.sleep(3)
    timings["generate_seconds"] = time.perf_counter() - t

    if img_info is None:
        print(json.dumps({"error": "No image returned by ComfyUI"}))
        return 1

    image = _fetch_image(img_info)
    image.save(raw_path)

    t = time.perf_counter()
    if native:
        left = (image.width - final_w) // 2
        top = (image.height - final_h) // 2
        final = image.crop((left, top, left + final_w, top + final_h))
    else:
        final = image.resize((final_w, final_h), Image.Resampling.LANCZOS)
    final.save(final_path)
    timings["postprocess_seconds"] = time.perf_counter() - t
    timings["end_to_end_seconds"] = time.perf_counter() - t_all

    meta = {
        "backend": "comfyui-anima",
        "model": unet,
        "loras": [{"name": n, "strength": s} for n, s in loras],
        "trigger": trigger.strip(),
        "mode": mode,
        "native_1080p": native,
        "img2img": is_edit,
        "input_image": str(Path(args.image).resolve()) if is_edit else None,
        "denoise": denoise if is_edit else None,
        "prompt": args.prompt,
        "seed": seed,
        "steps": steps,
        "guidance_scale": cfg,
        "sampler": ANIME_SAMPLER,
        "scheduler": ANIME_SCHEDULER,
        "generated_size": [gen_w, gen_h],
        "final_size": [final_w, final_h],
        "upscale": "none (crop)" if (native and not is_edit) else f"lanczos {gen_w}x{gen_h}->{final_w}x{final_h}",
        "raw_path": str(raw_path.resolve()),
        "final_path": str(final_path.resolve()),
        "timings": timings,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0
