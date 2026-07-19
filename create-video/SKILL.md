---
name: create-video
description: Generate a short video (with synchronized audio) from a text prompt or source image + prompt using LTX-2.3, Lightricks' 22B audio-video diffusion model, on the local ROCm GPU. Use for ANY movie/video-making request — create/generate a video, make a film/movie/short clip/trailer/MV/advertisement/animation, 拍片/做影片/做電影/做動畫, animate a scene, or turn a photo/text description into a moving image with sound. Longer pieces = generate multiple clips with this skill and stitch them with ffmpeg.
version: 1.1.0
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
| `--offload` | `none\|cpu\|disk` — ⚠️ do NOT use `cpu` on this box (UMA: GPU memory IS system RAM, offload frees nothing and only adds copies; see perf notes) | `none` |
| `--chunk-seconds` | Auto-split clips longer than this into segments (0 = never split) | `5` |
| `--smooth-chunks` | Use multi-keyframe overlap continuation for long clips | on |
| `--fast-chunks` | Use old faster last-frame chunking instead of smooth continuation | off |
| `--overlap-seconds` | Smooth chunk overlap/keyframe span | `1` |
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
# (no --offload: this UMA box gains nothing from CPU offload — free memory instead)
create_video.sh --image ./cat.jpg -p "The cat slowly blinks" --bf16 -o cat_bf16.mp4
```

## Prompting tips (LTX-2.3 — official Lightricks guidance)

Write **one flowing paragraph, present tense**, like a cinematographer's shot description.
Be literal and specific — LTX-2.3 rewards detail. Follow this **official ordering**:

1. **Establish the shot** — cinematography terms for the genre (e.g. *cinematic sci-fi
   establishing shot, anamorphic wide lens, shallow depth of field, macro lens, low angle*).
2. **Set the scene** — lighting, color palette, textures, atmosphere (*golden hour,
   rim light, neon glow, teal-and-amber palette, volumetric haze, drifting particles, fog*).
3. **Describe the action** — the core motion, flowing naturally, one main action.
4. **Define the character/subject** — age, clothing, distinguishing features.
5. **Camera movement** — explicit motion verbs: *slow dolly-in, pan, track, tilt up,
   push in / pull back, orbit/circle around, handheld tracking, crane/overhead*. A concrete
   move ("slow dolly-in") is far more stable than vague language.
6. **Audio** — describe ambient sound, music, and any dialogue **in quotation marks**
   (specify language/accent). 2.3's audio is strong, so it's worth a clause.

**Length:** match prompt length to clip duration; keep **under ~200 words**. One main
action per **2–3 s** of video — a short prompt on a long clip makes the model rush.

**Audio prompting guideline:** LTX-2.3 generates synchronized ambience, SFX, music,
speech, or singing when audio is enabled. Prompt audio as explicitly as visuals:

- Put audio near the end in an `Audio:` clause.
- Describe **ambience / room tone** so the model has a background bed: *quiet steakhouse
  ambience, soft kitchen room tone, distant street traffic, wind through trees*.
- Describe **sound effects tied to visible actions**: *knife softly scrapes ceramic as it
  cuts, wet yolk rupture as the egg opens, thick yolk dripping sounds, fabric rustle,
  footsteps on gravel*. Specific action-linked SFX work better than generic "good sound".
- Describe **music as genre + instruments + intensity**: *warm low-volume jazz piano and
  upright bass*, *minimal cinematic strings and soft piano*, *upbeat acoustic guitar and
  light percussion*. If music is unwanted, still provide ambience/SFX and write *no music,
  no singing*.
- Put **spoken dialogue in quotation marks**, and specify speaker/language/delivery:
  *A woman softly says in Mandarin: "好香。"* Keep dialogue short for clearer speech and
  lip sync.
- Say what you do **not** want when important: *no singing, no voiceover, no readable text,
  no crowd chatter*.

Example food audio clause:

```text
Audio: intimate steakhouse ambience, soft plate clinks, close-up knife scraping ceramic,
wet yolk rupture as the egg opens, thick yolk dripping sounds, tender steak fibers tearing
softly, subtle sizzling butter, warm low-volume jazz piano and upright bass, no singing,
no voiceover.
```

**Avoid:** internal emotional states (use visible physical cues instead), readable
text/logos, complex/chaotic physics, too many characters, conflicting lighting, and vague
prompts like "a nice video of nature". For dialogue, use short phrases with physical acting
directions between them, not emotion labels.

For `--image` (image-to-video), describe the **motion/change and new atmosphere** while
referencing the existing subject (*"the man stands still as the camera slowly pushes in…"*).
`--image-strength` (default `0.9`) keeps identity/composition close to the photo; **lower it
(≈0.6–0.8)** when you want a stronger stylistic transformation (e.g. turning a snapshot into
a sci-fi scene) rather than a near-static animation.

See: Lightricks LTX-2.3 prompt guide — https://ltx.io/model/model-blog/ltx-2-3-prompt-guide

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
  memory pressure.
- **⚠️ Never use `--offload cpu` on this machine.** Strix Halo is UMA: "GPU memory" is
  the same physical RAM as CPU memory (GTT). Offloading to CPU frees no memory at all —
  it just adds host↔device copies and slows the run down. When memory is tight, actually
  FREE memory instead: stop/shrink the big `llama-server` (qwen-mtp ctx/slots), stop
  other GPU services, or lower resolution/frames.
- fp8 peak ~50–55 GB; resident transformer raises peak. The box shares RAM as GTT — if a
  large `llama-server` is running, free memory (shrink its ctx/slots) before generating.

### Long clips: auto-chunking (avoids OOM / earlyoom kills)

Attention is **quadratic in frame count**, memory is unified GTT, and **earlyoom** kills
processes at a 3 GB-free floor — so a single-shot long clip will OOM or get SIGTERM'd.
The wrapper therefore **auto-splits any clip longer than `--chunk-seconds` (default 5 s)**.
As of the continuity update, long clips default to **smooth multi-keyframe continuation**
(`--smooth-chunks`): each continuation chunk is conditioned on multiple keyframes extracted
from the previous chunk's final `--overlap-seconds` (default 1 s), then the duplicated
overlap is trimmed during assembly. This is slower than simple concat but gives smoother
seams because the next segment sees a short motion/pose sequence, not just one final frame.
Per-segment memory stays at the ~5 s footprint. A 20 s target with 5 s chunks and 1 s overlap
requires 5 generated chunks internally, then trims to the requested duration.

Use `--fast-chunks` to force the old quicker behavior: each next chunk is conditioned only
on the previous segment's last frame and then concatenated. Use `--chunk-seconds 0` to force
single-shot behaviour (only safe for short clips). Trade-off: audio is generated per-segment
so seams may still not be perfectly continuous, and subjects can drift after the anchored
overlap region.

### When the user asks for a multi-second / multi-segment story

If the user asks for a longer video, a film broken into several seconds, or asks how to
"stitch", "continue", "extend", "接起來", "拼接", or "用上一段最後一幀繼續", prefer a
continuity-first plan instead of blindly generating one very long clip.

Practical default workflow tested on this host, and now the wrapper's default for long clips:

1. **Write the script as segments** (usually 5–10 s each). Each segment should contain only
   one main action. Avoid cramming many actions into one segment; LTX will deform subjects.
2. **Generate with overlap**, not hard cuts:
   - Example target ≈ 9–10 s: generate `seg1` for 5 s, extract frame at `4.0s`, generate
     `seg2` for 5 s from that frame, then crossfade overlap from `4–5s`.
   - For longer stories, repeat: each new segment starts from a frame about 1 s before the
     previous segment ends.
3. **Second/later segment prompt must start with continuity constraints**, e.g.:
   - `Continue seamlessly from the provided starting frame.`
   - `For the first one second, keep the subject and camera almost still.`
   - `Preserve exact pose, lighting, fur pattern/clothing, background, lens, color grading,
      and composition.`
   - Then describe the next action.
4. **Choose low-motion cut points**. Do not cut while the subject jumps, turns quickly, or
   the camera is panning fast. Prefer a blink, breath, pause, settled pose, or almost-static
   frame.
5. **Better than a single last frame: use multiple keyframe images if possible.** The
   underlying LTX CLI supports repeated `--image PATH FRAME_IDX STRENGTH [CRF]`, even though
   the simple wrapper exposes only one image. For a continuation segment, extract the last
   second of the previous segment at several keyframes (e.g. previous `4.0s`, `4.33s`,
   `4.67s`, `4.96s`) and condition the next segment at frames `0`, `8`, `16`, `24`. This
   gives the model motion/pose anchors over the first second, not just a single start pose.
6. **Stitch with video + audio crossfade** when needed. Hard concat usually exposes motion
   reset and audio seams. Use `xfade` for video and `acrossfade` for audio. If multi-keyframe
   conditioning aligns well, a hard join at the overlap boundary or a very short
   `0.2–0.3s` micro-xfade can look cleaner than a long 1s xfade, which may ghost.
7. **Be honest with the user**: overlap/crossfade/multi-keyframe conditioning improves
   continuity but does not guarantee perfect identity or anatomy. LTX is still likely to
   drift on animals, hands, faces, and complex motion. If quality matters, show a short test
   first.

The wrapper now automates this default for long clips. Use manual commands only when you need
custom segment prompts, custom cut points, or to inspect/control every seam.

Example commands for a manual external-overlap test:

```bash
BASE=/home/chihmin/generated/ltx/my_overlap_test
mkdir -p "$BASE/seg1" "$BASE/seg2"

# Segment 1: 5 seconds, no internal chunking.
~/.hermes/skills/create-video/create_video.sh \
  -p "SEGMENT 1 PROMPT" \
  -d 5 -r 1280x704 --chunk-seconds 0 --seed 13001 \
  -o "$BASE/seg1/seg1.mp4"

# Use a frame 1 second before the end as the next segment's start image.
ffmpeg -y -v error -ss 4.0 -i "$BASE/seg1/seg1.mp4" -frames:v 1 "$BASE/seg1_frame_4s.png"

# Segment 2: first second should be nearly still to stabilize continuity.
~/.hermes/skills/create-video/create_video.sh \
  --image "$BASE/seg1_frame_4s.png" --image-strength 0.92 \
  -p "Continue seamlessly from the provided starting frame. For the first one second, keep the subject and camera almost still, preserving exact pose, lighting, background, lens, and color grading. Then continue the next action..." \
  -d 5 -r 1280x704 --chunk-seconds 0 --seed 13002 \
  -o "$BASE/seg2/seg2.mp4"

# Crossfade the 1-second overlap: seg1 0–5s + seg2 0–5s => final ~9s.
ffmpeg -y -i "$BASE/seg1/seg1.mp4" -i "$BASE/seg2/seg2.mp4" \
  -filter_complex "[0:v][1:v]xfade=transition=fade:duration=1:offset=4,format=yuv420p[v];[0:a][1:a]acrossfade=d=1:c1=tri:c2=tri[a]" \
  -map '[v]' -map '[a]' \
  -c:v libx264 -pix_fmt yuv420p -movflags +faststart -crf 20 -preset veryfast \
  -c:a aac -b:a 128k "$BASE/final_overlap_xfade.mp4"
```

For user-facing delivery, also make a small contact sheet around the seam (`3.8s`, `4.2s`,
`4.6s`, `5.0s`) to inspect whether the transition is acceptable before claiming it is good.

Multi-keyframe continuation example using the underlying LTX runner directly:

```bash
# Suppose seg1.mp4 is 5s. Extract the final second as four keyframes.
for spec in 0:4.000 8:4.333 16:4.667 24:4.958; do
  idx=${spec%%:*}; t=${spec#*:}
  ffmpeg -y -v error -ss "$t" -i seg1.mp4 -frames:v 1 "ref_frame_${idx}.png"
done

# Generate seg2 with those keyframes pinned to frames 0/8/16/24. CRF 0 keeps the
# conditioning images lossless.
cd /home/chihmin/src/LTX-2
env PYTHONUTF8=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1 \
  MIOPEN_FIND_MODE=FAST MIOPEN_USER_DB_PATH=/home/chihmin/.cache/miopen-ltx \
  /home/chihmin/src/LTX-2/.venv/bin/python /home/chihmin/.hermes/skills/create-video/ltx_run.py \
    --distilled-checkpoint-path /home/chihmin/src/LTX-2/models/ltx/ltx-2.3-22b-distilled-1.1.safetensors \
    --spatial-upsampler-path /home/chihmin/src/LTX-2/models/ltx/ltx-2.3-spatial-upscaler-x2-1.1.safetensors \
    --gemma-root /home/chihmin/src/LTX-2/models/gemma-3-12b-it \
    --prompt "Continue seamlessly from the provided sequence of starting keyframes. The first second should follow the provided keyframes closely, preserving exact motion, pose, lighting, background, lens, and color grading. Then continue the next action..." \
    --height 704 --width 1280 --num-frames 121 --frame-rate 24 \
    --seed 13012 --output-path seg2.mp4 --quantization fp8-cast \
    --image ref_frame_0.png 0 0.95 0 \
    --image ref_frame_8.png 8 0.95 0 \
    --image ref_frame_16.png 16 0.95 0 \
    --image ref_frame_24.png 24 0.95 0

# If seg2 frame 0 corresponds to seg1 at 4.0s, build final as seg1[0:4] + seg2.
ffmpeg -y -i seg1.mp4 -i seg2.mp4 \
  -filter_complex "[0:v]trim=0:4,setpts=PTS-STARTPTS[v0];[0:a]atrim=0:4,asetpts=PTS-STARTPTS[a0];[1:v]setpts=PTS-STARTPTS[v1];[1:a]asetpts=PTS-STARTPTS[a1];[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]" \
  -map '[v]' -map '[a]' -c:v libx264 -pix_fmt yuv420p -movflags +faststart \
  -crf 20 -preset veryfast -c:a aac -b:a 128k final_hardjoin.mp4
```

Tested result note: on the cat overlap experiment, conditioning frames `0/8/16/24` against
previous segment keyframes gave low frame diffs (`mean_abs_rgb` about `2–4`), proving that
multi-keyframe conditioning does lock the first second much more strongly than a single
start image. The subject can still drift after the anchored region.

## Notes

- Text encoder is Gemma-3-12b (ungated `unsloth/gemma-3-12b-it` mirror) under `~/src/LTX-2/models/`.
- Distilled checkpoint only. The full `dev` two-stage checkpoint (best quality, +44 GB) is
  not downloaded; add it and switch to `ltx_pipelines.ti2vid_two_stages` if needed.
- See deploy notes / gotchas: `~/src/LTX-2` and the project memory.
```
