#!/usr/bin/env python3
"""Direct Wan2.1 T2V 1.3B runner using Comfy's PyTorch backend without ComfyUI server.

Defaults are memory-optimized for UMA/APU machines:
- UMT5 text encoder on CPU (saves ~6 GiB GTT/UMA vs GPU text encoder)
- free/unload the text encoder immediately after prompt encoding
- tiled VAE decode to reduce decode peak
"""
import argparse, gc, glob, os, shutil, sys, time
from pathlib import Path

COMFY = Path(os.environ.get('COMFY_DIR', '/home/chihmin/src/ComfyUI'))
os.chdir(COMFY)
sys.path.insert(0, str(COMFY))
os.environ.setdefault('TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL', '1')

import torch
import nodes
from comfy_extras.nodes_model_advanced import ModelSamplingSD3
from comfy_extras.nodes_hunyuan import EmptyHunyuanLatentVideo
from comfy_extras.nodes_video import CreateVideo, SaveVideo
from types import SimpleNamespace

SaveVideo.hidden = SimpleNamespace(prompt=None, extra_pnginfo=None)

DEFAULT_PROMPT = (
    'A cute cat is eating food from a small bowl on a cozy kitchen floor, close-up, '
    'realistic soft fur, gentle chewing motion, warm natural light, cinematic, stable camera, high quality video'
)
DEFAULT_NEG = (
    '色调艳丽，过曝，静态，细节模糊不清，字幕，文字，水印，最差质量，低质量，'
    'JPEG压缩残留，畸形，画得不好的脸部，多余的肢体，杂乱背景'
)

def mark(tag: str, enabled: bool = True):
    if not enabled:
        return
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        alloc = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        print(f'{time.time():.3f} {tag} torch_alloc={alloc:.3f}GiB torch_reserved={reserved:.3f}GiB', flush=True)
    else:
        print(f'{time.time():.3f} {tag}', flush=True)

def newest_output(prefix_token: str):
    files = sorted(glob.glob(str(COMFY / 'output' / 'wan21_direct_optimized' / f'*{prefix_token}*.mp4')), key=os.path.getmtime)
    return files[-1] if files else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prompt', default=DEFAULT_PROMPT)
    ap.add_argument('--negative', default=DEFAULT_NEG)
    ap.add_argument('--output', required=True)
    ap.add_argument('--width', type=int, default=832)
    ap.add_argument('--height', type=int, default=480)
    ap.add_argument('--frames', type=int, default=17, help='Wan video length; use 4n+1, e.g. 17/49/73')
    ap.add_argument('--fps', type=float, default=16)
    ap.add_argument('--steps', type=int, default=12)
    ap.add_argument('--cfg', type=float, default=6.0)
    ap.add_argument('--seed', type=int, default=2026070118)
    ap.add_argument('--clip-device', choices=['cpu', 'default'], default='cpu', help='cpu is lowest-memory; default loads the text encoder on Comfy/PyTorch default device')
    ap.add_argument('--free-clip-after-encode', action=argparse.BooleanOptionalAction, default=True, help='delete CLIP/UMT5 and empty the GPU cache immediately after pos/neg encoding')
    ap.add_argument('--vae-mode', choices=['regular', 'tiled'], default='tiled')
    ap.add_argument('--tile-size', type=int, default=256)
    ap.add_argument('--overlap', type=int, default=64)
    ap.add_argument('--temporal-size', type=int, default=16)
    ap.add_argument('--temporal-overlap', type=int, default=4)
    ap.add_argument('--warmup-steps', type=int, default=0, help='run an unsaved same-shape warmup sample before the real sample to populate ROCm/Triton/MIOpen caches')
    ap.add_argument('--warmup-decode', action=argparse.BooleanOptionalAction, default=True, help='also run VAE decode during warmup to compile/warm decode kernels')
    ap.add_argument('--quiet-mem', action='store_true')
    args = ap.parse_args()

    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    token = f'wan21_{args.width}x{args.height}_{args.frames}f_{args.steps}step_{args.clip_device}_{args.vae_mode}_{int(time.time())}'

    t0 = time.time()
    do_mark = not args.quiet_mem
    mark(f'start clip={args.clip_device} vae={args.vae_mode} steps={args.steps} size={args.width}x{args.height} frames={args.frames}', do_mark)

    with torch.inference_mode():
        model = nodes.UNETLoader().load_unet('wan2.1_t2v_1.3B_fp16.safetensors', 'default')[0]
        mark('after_unet_loaded', do_mark)
        model = ModelSamplingSD3().patch(model, 8.0)[0]
        mark('after_sampling_patched', do_mark)

        clip = nodes.CLIPLoader().load_clip('umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'wan', args.clip_device)[0]
        mark('after_clip_loaded', do_mark)
        pos = nodes.CLIPTextEncode().encode(clip, args.prompt)[0]
        mark('after_pos_encoded', do_mark)
        neg = nodes.CLIPTextEncode().encode(clip, args.negative)[0]
        mark('after_neg_encoded', do_mark)

        if args.free_clip_after_encode:
            del clip
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            mark(f'after_del_clip_{args.clip_device}', do_mark)

        vae = nodes.VAELoader().load_vae('wan_2.1_vae.safetensors')[0]
        mark('after_vae_loaded', do_mark)

        if args.warmup_steps > 0:
            warm_latent = EmptyHunyuanLatentVideo.execute(args.width, args.height, args.frames, 1).result[0]
            mark(f'before_warmup_sample steps={args.warmup_steps}', do_mark)
            warm_sampled = nodes.KSampler().sample(model, args.seed + 9973, args.warmup_steps, args.cfg, 'uni_pc', 'simple', pos, neg, warm_latent, 1.0)[0]
            mark('after_warmup_sampled', do_mark)
            if args.warmup_decode:
                if args.vae_mode == 'tiled':
                    warm_images = nodes.VAEDecodeTiled().decode(vae, warm_sampled, args.tile_size, args.overlap, args.temporal_size, args.temporal_overlap)[0]
                else:
                    warm_images = nodes.VAEDecode().decode(vae, warm_sampled)[0]
                mark('after_warmup_vae_decoded', do_mark)
                del warm_images
            del warm_sampled, warm_latent
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            mark('after_warmup_cleanup', do_mark)

        latent = EmptyHunyuanLatentVideo.execute(args.width, args.height, args.frames, 1).result[0]
        mark('after_latent_created', do_mark)
        sampled = nodes.KSampler().sample(model, args.seed, args.steps, args.cfg, 'uni_pc', 'simple', pos, neg, latent, 1.0)[0]
        mark('after_sampled', do_mark)

        if args.vae_mode == 'tiled':
            images = nodes.VAEDecodeTiled().decode(vae, sampled, args.tile_size, args.overlap, args.temporal_size, args.temporal_overlap)[0]
        else:
            images = nodes.VAEDecode().decode(vae, sampled)[0]
        mark('after_vae_decoded', do_mark)
        video = CreateVideo.execute(images, args.fps).result[0]
        mark('after_video_created', do_mark)
        SaveVideo.execute(video, f'wan21_direct_optimized/{token}', 'mp4', 'h264')
        mark('after_saved', do_mark)

    src = newest_output(token)
    if not src:
        raise RuntimeError('SaveVideo finished but output file was not found')
    shutil.copy2(src, out)
    print(f'OUTPUT {out}', flush=True)
    print(f'ELAPSED {time.time() - t0:.3f}', flush=True)

if __name__ == '__main__':
    main()
