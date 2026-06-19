---
name: create-video
description: Generate a short video (with synchronized audio) from a text prompt using LTX-2.3, Lightricks' 22B audio-video diffusion model, on the local ROCm GPU. Use when the user wants to create/generate a video, make a short clip, animate a scene, or turn a text description into a moving image with sound.
version: 1.0.0
author: Hermes Agent
license: MIT
prerequisites:
  commands: [ffmpeg]
  paths: [~/src/LTX-2]
metadata:
  hermes:
    tags: [video, generation, ai, ltx, ltx-2, text-to-video, t2v, diffusion, audio, clip]
    related_skills: [create-music, mock-voice, restyle-music]
---

# Create Video — LTX-2.3 text-to-video (with synced audio, GPU)

Generate a short video clip with **synchronized audio** from a **text prompt** using
**LTX-2.3** (Lightricks' 22B audio-video DiT), on the local AMD GPU (ROCm gfx1151).
Deployed at `~/src/LTX-2`. Uses the distilled two-stage pipeline + fp8-cast quantization,
with ROCm flash attention (AOTriton) on by default.

## When to use

- "Make a video of X" / "generate a short clip of …" / "animate …"
- User gives a scene description and wants an `.mp4` out.

**Audio:** synced audio is **ON by default** and nearly free — the vocoder runs on
CPU (see perf notes). Use `--no-audio` for silent output, e.g. when the user wants
to score the clip with the **create-music** skill instead.

## Quick start (one-shot wrapper)

```bash
~/.hermes/skills/create-video/create_video.sh -p "A corgi running across a sunny beach, waves splashing, slow motion" -o corgi.mp4
```

Defaults: **320p 16:9 (576×320), 3 s @ 24 fps**, fp8, flash attention on.

## Options

| Flag | Meaning | Default |
|------|---------|---------|
| `-p, --prompt` | What to generate (required) | — |
| `-d, --duration` | Clip length (seconds) | `3` |
| `--fps` | Frames per second | `24` |
| `-a, --aspect` | Aspect ratio when no `-r` (e.g. `9:16`, `1:1`, `4:3`) | `16:9` |
| `-r, --resolution` | Explicit `WxH` (multiples of 64); overrides `-a` | — |
| `--hq` | High quality: short side → 576 (e.g. `1024×576` for 16:9) | off |
| `-o, --output` | Output `.mp4` | `./video_<ts>.mp4` |
| `--seed` | Random seed | random |
| `--steps` | Override stage-1 denoise steps | model default |
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
```

## Prompting tips (LTX-2)

Single flowing paragraph, cinematic and literal. Start with the main action, then add
movement details, appearance, background, camera angle/movement, lighting. Keep < 200 words.

## Resolution & frame rules

- Two-stage pipeline requires width/height to be **multiples of 64** — the wrapper snaps to /64.
- Frame count must be **8k+1** — the wrapper snaps `duration × fps` to the nearest valid count.
- 320p 16:9 ≈ `576×320`. `--hq` 16:9 = `1024×576`.

## Performance & memory (gfx1151)

- **With audio (default): 10s @ 320p ≈ 2.5 min; 1s ≈ 67 s.** Budget (10s): Gemma 17s,
  denoise ~90s, video VAE decode ~23s, CPU vocoder ~8s. Model load is a fixed ~45s/run.
- **The vocoder MUST run on CPU** (the launcher does this). On GPU its fp32 conv1d hits
  MIOpen's `naive_conv ... float_double_float` (fp64 accumulate, ~1/16 rate on gfx1151) =
  33% of GPU time and ~700 s for a 10 s clip; CPU oneDNN does the same fp32 math ~14× faster.
  Video convs (conv2d/conv3d) are bf16 and fine on GPU.
- Flash attention (AOTriton) on by default — same quality as SDPA, ~10–20% faster;
  `attn_fwd` is only ~3% of GPU time, so attention is not the bottleneck.
- **Do NOT** set `MIOPEN_FIND_ENFORCE` / `torch.backends.cudnn.benchmark` — exhaustive
  MIOpen search made decode 18× slower and still lands on naive conv. Triton conv3d
  fails on gfx1151 (LDS 64 KB < 64–128 KB needed), so `torch.compile` can't help convs.
- fp8 peak ~50–55 GB. The box shares RAM as GTT; if a large `llama-server` is resident
  you may need to free memory (e.g. shrink its context/slots) or pass `--offload cpu`.

## Notes

- Text encoder is Gemma-3-12b (ungated `unsloth/gemma-3-12b-it` mirror) under `~/src/LTX-2/models/`.
- Distilled checkpoint only. The full `dev` two-stage checkpoint (best quality, +44 GB) is
  not downloaded; add it and switch to `ltx_pipelines.ti2vid_two_stages` if needed.
- See deploy notes / gotchas: `~/src/LTX-2` and the project memory.
```
