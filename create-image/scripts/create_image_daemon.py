#!/usr/bin/env python3
import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import torch
from diffusers import Flux2KleinPipeline
from PIL import Image, ImageOps

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import create_image as ci  # noqa: E402


class WarmFlux2Service:
    def __init__(self):
        self.lock = threading.Lock()
        self.pipe = None
        self.loaded_at = None
        self.timings = {}
        self.lora_loaded = False
        self.lora_error = None

    def load(self):
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        os.environ.setdefault("TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL", "1")
        t = time.perf_counter()
        self.pipe = Flux2KleinPipeline.from_pretrained(ci.MODEL_ID_9B_KV, torch_dtype=torch.bfloat16)
        ci.sync(); self.timings["load_pipeline_seconds"] = time.perf_counter() - t
        t = time.perf_counter()
        self.pipe = self.pipe.to("cuda")
        ci.sync(); self.timings["move_to_gpu_seconds"] = time.perf_counter() - t
        self.loaded_at = datetime.now().isoformat()

    def maybe_load_lora(self, prompt: str, no_auto_lora: bool, lora_scale: float) -> dict:
        prompt_lower = prompt.lower()
        requested = (not no_auto_lora) and any(k in prompt_lower or k in prompt for k in ci.GHIBLI_KEYWORDS)
        status = {"requested": requested, "loaded": False, "path": None, "error": None}
        if not requested:
            return status
        status["path"] = str(ci.GHIBLI_LORA_PATH)
        if self.lora_loaded:
            self.pipe.set_adapters(["ghibli"], adapter_weights=[lora_scale])
            status["loaded"] = True
            return status
        if not ci.GHIBLI_LORA_PATH.exists():
            status["error"] = "LoRA file not found"
            return status
        try:
            self.pipe.load_lora_weights(str(ci.GHIBLI_LORA_PATH), adapter_name="ghibli")
            self.pipe.set_adapters(["ghibli"], adapter_weights=[lora_scale])
            self.lora_loaded = True
            status["loaded"] = True
        except Exception as exc:  # noqa: BLE001
            message = str(exc).replace("\n", " ")
            if len(message) > 500:
                message = message[:500] + "..."
            self.lora_error = f"{type(exc).__name__}: {message}"
            status["error"] = self.lora_error
        return status

    def generate(self, payload: dict) -> dict:
        with self.lock:
            return self._generate_locked(payload)

    def _generate_locked(self, payload: dict) -> dict:
        prompt = payload.get("prompt") or ci.DEFAULT_PROMPT
        image_path = payload.get("image")
        is_edit = image_path is not None
        native_1080p = bool(payload.get("native_1080p"))
        steps = int(payload.get("steps") or 4)
        guidance_scale = float(payload.get("guidance_scale") or 1.0)
        lora_scale = float(payload.get("lora_scale") or 0.8)
        seed = payload.get("seed")
        seed = int(seed) if seed is not None else int(time.time()) % (2**31)

        if native_1080p:
            gen_w, gen_h = ci.NATIVE_OUTPUT_SIZE
        else:
            gen_w, gen_h = ci.DEFAULT_9B_OUTPUT_SIZE
        final_w, final_h = ci.FINAL_SIZE
        if payload.get("output_size"):
            final_w, final_h = ci.parse_size(payload["output_size"])
        ref_w, ref_h = ci.FAST_REFERENCE_SIZE

        mode = payload.get("mode") or (("edit-" if is_edit else "") + ("9b-kv-native-1080p" if native_1080p else "9b-default-1360x768-upscale-1080p"))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = payload.get("prefix") or f"flux2_{mode}_{timestamp}"
        out_dir = Path(payload.get("out_dir") or "/home/chihmin/models-work/flux2/output/create-image")
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_path = out_dir / f"{prefix}_raw_{gen_w}x{gen_h}.png"
        final_suffix = f"{final_w}x{final_h}" if is_edit or payload.get("output_size") else "1080p"
        final_path = out_dir / f"{prefix}_{final_suffix}.png"
        meta_path = out_dir / f"{prefix}_timing.json"

        timings = {"daemon_queue_seconds": 0.0}
        lora_status = self.maybe_load_lora(prompt, bool(payload.get("no_auto_lora")), lora_scale)

        reference_image = None
        if is_edit:
            src = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
            src_fit = ImageOps.contain(src, (ref_w, ref_h), Image.Resampling.LANCZOS)
            reference_image = Image.new("RGB", (ref_w, ref_h), (245, 240, 232))
            reference_image.paste(src_fit, ((ref_w - src_fit.width) // 2, (ref_h - src_fit.height) // 2))

        generator = torch.Generator(device="cuda").manual_seed(seed)
        t = time.perf_counter()
        with torch.inference_mode():
            call_kwargs = {
                "prompt": prompt,
                "width": gen_w,
                "height": gen_h,
                "num_inference_steps": steps,
                "guidance_scale": guidance_scale,
                "generator": generator,
            }
            if reference_image is not None:
                call_kwargs["image"] = reference_image
            image = self.pipe(**call_kwargs).images[0]
        ci.sync(); timings["generate_seconds"] = time.perf_counter() - t

        t = time.perf_counter(); image.save(raw_path); timings["save_raw_seconds"] = time.perf_counter() - t
        t = time.perf_counter()
        if native_1080p and final_w <= gen_w and final_h <= gen_h:
            left = (gen_w - final_w) // 2
            top = (gen_h - final_h) // 2
            final = image.crop((left, top, left + final_w, top + final_h))
        else:
            final = image.resize((final_w, final_h), Image.Resampling.LANCZOS)
        timings["postprocess_seconds"] = time.perf_counter() - t
        t = time.perf_counter(); final.save(final_path); timings["save_final_seconds"] = time.perf_counter() - t
        timings["warm_request_seconds"] = timings["generate_seconds"] + timings["postprocess_seconds"] + timings["save_final_seconds"]

        meta = {
            "served_by": "create-image-daemon",
            "model": ci.MODEL_ID_9B_KV,
            "model_label": "9b-kv",
            "mode": mode,
            "prompt": prompt,
            "seed": seed,
            "steps": steps,
            "guidance_scale": guidance_scale,
            "generated_size": [gen_w, gen_h],
            "reference_size": [ref_w, ref_h] if is_edit else None,
            "final_size": [final_w, final_h],
            "input_image": str(Path(image_path).resolve()) if is_edit else None,
            "torch": torch.__version__,
            "hip": getattr(torch.version, "hip", None),
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "lora": lora_status,
            "daemon_loaded_at": self.loaded_at,
            "daemon_startup_timings": self.timings,
            "timings": timings,
            "raw_path": str(raw_path.resolve()),
            "final_path": str(final_path.resolve()),
        }
        ci.save_json(meta_path, meta)
        return meta


SERVICE = WarmFlux2Service()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"ok": SERVICE.pipe is not None, "model": ci.MODEL_ID_9B_KV, "loaded_at": SERVICE.loaded_at, "timings": SERVICE.timings})
        else:
            self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path != "/generate":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            result = SERVICE.generate(payload)
            self._send_json(200, result)
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Warm local FLUX.2 9B-KV daemon for /create-image")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7862)
    args = parser.parse_args()
    print("[create-image-daemon] loading 9B-KV pipeline...", flush=True)
    SERVICE.load()
    print(json.dumps({"event": "loaded", "loaded_at": SERVICE.loaded_at, "timings": SERVICE.timings}, ensure_ascii=False), flush=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[create-image-daemon] listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
