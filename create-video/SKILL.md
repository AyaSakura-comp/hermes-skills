---
name: create-video
description: Generate a short video (with synchronized audio) from a text prompt or source image + prompt using LTX-2.3, Lightricks' 22B audio-video diffusion model, on the local ROCm GPU. Use when the user wants to create/generate a video, make a short clip, animate a scene, or turn a photo/text description into a moving image with sound.
version: 1.0.0
author: Hermes Agent
license: MIT
prerequisites:
  commands: [ffmpeg]
  paths: [~/src/LTX-2]
metadata:
  hermes:
    tags: [video, generation, ai, ltx, ltx-2, text-to-video, image-to-video, t2v, i2v, diffusion, audio, clip]
    related_skills: [create-music, mock-voice, restyle-music]
---

# Create Video — LTX-2.3 text/image-to-video (with synced audio, GPU)

Generate a short video clip with **synchronized audio** from a **text prompt** or
from a **source image + prompt** using **LTX-2.3** (Lightricks' 22B audio-video DiT),
on the local AMD GPU (ROCm gfx1151).
Deployed at `~/src/LTX-2`. Uses the distilled two-stage pipeline + fp8-cast quantization,
with ROCm flash attention (AOTriton) on by default.

## When to use

- "Make a video of X" / "generate a short clip of …" / "animate …"
- User gives a scene description and wants an `.mp4` out.
- User provides a photo/image and asks to animate it with a prompt (image-to-video).

**Audio:** synced audio is **ON by default** and nearly free — the vocoder runs on
CPU (see perf notes). Use `--no-audio` for silent output, e.g. when the user wants
to score the clip with the **create-music** skill instead.

## Quick start (one-shot wrapper)

```bash
~/.hermes/skills/create-video/create_video.sh -p "A corgi running across a sunny beach, waves splashing, slow motion" -o corgi.mp4

# Animate an existing photo while following the prompt
~/.hermes/skills/create-video/create_video.sh --image ./portrait.jpg -p "The person smiles and waves gently, subtle camera push-in" -o portrait_wave.mp4
```

Defaults: **320p 16:9 (576×320), 3 s @ 24 fps**, fp8, flash attention on.

## Options

| Flag | Meaning | Default |
|------|---------|---------|
| `-p, --prompt` | What to generate/animate (required) | — |
| `-i, --image` | Optional source image/photo to animate from frame 0 | — |
| `--image-frame` | Target frame index for image conditioning | `0` |
| `--image-strength` | Image adherence strength | `0.9` |
| `--image-crf` | Optional conditioning image CRF (`0` = lossless) | LTX default |
| `-d, --duration` | Clip length (seconds) | `3` |
| `--fps` | Frames per second | `24` |
| `-a, --aspect` | Aspect ratio when no `-r` (e.g. `9:16`, `1:1`, `4:3`) | `16:9` |
| `-r, --resolution` | Explicit `WxH` (multiples of 64); overrides `-a` | — |
| `--hq` | High quality: short side → 576 (e.g. `1024×576` for 16:9) | off |
| `-o, --output` | Output `.mp4` | `./video_<ts>.mp4` |
| `--seed` | Random seed | random |
| `--steps` | Override stage-1 denoise steps | model default |
| `--quantization` | `fp8-cast\|fp8-scaled-mm\|bf16\|none` | `fp8-cast` |
| `--bf16` | Disable quantization; same as `--quantization none` | off |
| `--offload` | `none\|cpu\|disk` — lower GPU memory | `none` |
| `--audio` | Synced audio (default; vocoder on CPU, nearly free) | on |
| `--no-audio` | Silent video (skip the vocoder) | — |
| `--no-flash` | Disable flash attention (plain SDPA) | flash on |

> **Audio on by default, vocoder runs on CPU.** LTX's BigVGAN-style vocoder is fp32;
> on gfx1151 its 1D convs hit MIOpen's naive (fp64-accumulate) path and are crippled
> (~700 s of a 10 s clip on GPU). Running the *same fp32* vocoder on the CPU is ~14×
> faster per call (head-to-head, identical mel input: GPU-synced 18.1 s vs CPU 1.2 s;
> outputs differ 0.2%, just fp32 rounding) — so audio costs only a few seconds total
> (10 s clip: ~148 s with audio vs ~144 s silent). The launcher (`ltx_run.py`) does
> this automatically. Use `--no-audio` to skip it entirely.

## Examples

```bash
# Vertical short (TikTok/Reels), 5 seconds
create_video.sh -p "Neon city street at night, rain, reflections on the pavement, cinematic" -a 9:16 -d 5 -o street.mp4

# High quality 16:9
create_video.sh -p "A hot air balloon rising over misty mountains at dawn" --hq -o balloon.mp4

# Explicit resolution + square
create_video.sh -p "A spinning ceramic bowl on a potter's wheel" -r 384x384 -o bowl.mp4

# Image-to-video: preserve the source photo, animate according to the prompt
create_video.sh --image ./cat.jpg -p "The cat blinks, looks toward the camera, soft morning light" -d 3 -o cat_blink.mp4

# Stronger/weaker image adherence
create_video.sh --image ./landscape.png --image-strength 0.75 -p "Clouds drift slowly over the mountains" -o landscape_motion.mp4

# Higher-memory bf16/no-quant mode instead of default fp8-cast
create_video.sh --image ./cat.jpg -p "The cat slowly blinks" --bf16 --offload cpu -o cat_bf16.mp4
```

## Prompting tips (LTX-2)

Single flowing paragraph, cinematic and literal. Start with the main action, then add
movement details, appearance, background, camera angle/movement, lighting. Keep < 200 words.

For `--image`, describe the **motion/change** you want while referencing the existing subject
(`"the person smiles…"`, `"the camera slowly pushes in…"`). Keep identity/composition changes
small when you want the output to stay close to the original photo.

## Resolution & frame rules

- Two-stage pipeline requires width/height to be **multiples of 64** — the wrapper snaps to /64.
- Frame count must be **8k+1** — the wrapper snaps `duration × fps` to the nearest valid count.
- 320p 16:9 ≈ `576×320`. `--hq` 16:9 = `1024×576`.

## Performance & memory (gfx1151)

The launcher (`ltx_run.py`) applies three gfx1151 fixes automatically:

1. **`MIOPEN_FIND_MODE=FAST`** — the big one for high res. MIOpen's default FIND
   benchmarks candidate conv kernels at runtime on each new shape; a single 1080p
   frame's VAE decode was **92 s of pure search** (rocprof's "naive_conv 86%" was the
   search, not compute — actual conv is ~1.6 s). FAST uses the heuristic path → **2 s**
   decode even cold. NEVER set `MIOPEN_FIND_ENFORCE=3` / `cudnn.benchmark` (the opposite —
   force exhaustive search, 18× slower). `torch.compile`/triton can't help (triton conv
   OOMs gfx1151's 64 KB LDS).
2. **Audio vocoder on CPU** — its fp32 1D convs hit MIOpen naive+fp64 on GPU (~700 s for a
   10 s clip); same fp32 math on CPU oneDNN (24 threads) is ~14× faster, quality identical.
3. **Transformer load dedup** — the 22B denoise transformer is built once and kept resident
   across stage1+stage2 (default loads it twice). Saves a fixed ~17 s/run. Auto-skipped under
   `--offload`.

Timings (with audio, all fixes on):
- **320p:** 1 s ≈ 67 s, 10 s ≈ ~2.5 min. Dedup is ~24% of a 2 s clip here.
- **1080p:** 9 frames ≈ 90 s; **2 s (49 f) ≈ 8 min** — denoise-bound (stage2 ~103 s/it).
  Breakdown (1080p 9 f): denoise 59%, model load 31%, VAE decode 10%.
- Stage2 = the 22B joint audio-video DiT (48 blocks, video dim 4096). At few frames it's
  **GEMM-bound** (FFN 4096→16384 + QKV = 64% of GPU); at many frames **attention-bound**
  (quadratic in tokens). Neither is fixable on this GPU (no fp8 matmul) — reduce frames/res.
- Default precision is `--quantization fp8-cast` to keep the 22B model within memory.
  Use `--bf16` / `--quantization none` for bf16/no-quant comparisons; expect much higher
  memory pressure and consider `--offload cpu`.
- fp8 peak ~50–55 GB; resident transformer raises peak. The box shares RAM as GTT — if a
  large `llama-server` is running, free memory (shrink its ctx/slots) or pass `--offload cpu`.

## Notes

- Text encoder is Gemma-3-12b (ungated `unsloth/gemma-3-12b-it` mirror) under `~/src/LTX-2/models/`.
- Distilled checkpoint only. The full `dev` two-stage checkpoint (best quality, +44 GB) is
  not downloaded; add it and switch to `ltx_pipelines.ti2vid_two_stages` if needed.
- See deploy notes / gotchas: `~/src/LTX-2` and the project memory.
```
