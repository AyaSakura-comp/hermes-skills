---
name: create-image
description: Generate or edit images locally (FLUX.2 + Anima on ROCm 7.2). Use for /create-image or any request to create/generate/edit/convert an image (incl. photo→anime, photo→PVC). IMPORTANT FOR AGENTS - image generation is ALREADY DEPLOYED here; do NOT write your own diffusers/Stable-Diffusion/FLUX script and do NOT download models - RUN THIS SKILL'S SCRIPT. To run, activate the FLUX venv then call the script (works for all modes including anime/PVC, which only need urllib+PIL)- `cd /home/chihmin/models-work/flux2 && source .venv-rocm72/bin/activate && python ~/.hermes/skills/create-image/scripts/create_image.py "PROMPT" [flags]` - it prints JSON; attach its final_path PNG. Flags - (none)=FLUX.2 photoreal 1080p default; --fast-preview=quick draft; --native-1080p=high quality; --anime=anime/二次元/動漫/美少女/插畫/waifu (ComfyUI+Anima); --anime --image PHOTO=photo→anime img2img (--strength tunes how anime); PVC/figure/手辦/フィギュア prompts auto-switch to the Anima PVC checkpoint (use --anime). Read SKILL.md body for env/models/details before improvising.
---

# Create Image

## ⚡ How to run (copy/paste — do NOT roll your own)

**Image generation is ALREADY deployed here (FLUX.2 + Anima on ROCm). Do NOT write your own
diffusers / Stable Diffusion / Flux script and do NOT download models — just run the command below.**

Every request is one command. Always activate the FLUX venv first (it works for all modes, including
`--anime`):

```bash
cd /home/chihmin/models-work/flux2
source .venv-rocm72/bin/activate
python ~/.hermes/skills/create-image/scripts/create_image.py "YOUR PROMPT HERE"
```

That prints a JSON object — take the `final_path` field and **you MUST attach that PNG file in your
reply to the user** (don't just report the path or say "done"; always send the actual image).

Pick the mode by what the user asked for:

| User wants | Command (append to the `python … create_image.py "PROMPT"` line) |
|---|---|
| normal / photo / general (default) | *(nothing — default 9B → 1080p, ~25–60s)* |
| quick draft / 快速預覽 / 草稿 | `--fast-preview` *(4B, ~7s)* |
| high quality / 原生 / 高畫質 / native | `--native-1080p` *(~195s)* |
| **anime / 二次元 / 動漫 / 美少女 / 插畫 / waifu** | `--anime` *(720p→1080p, ~70s)* |
| **PVC figure / 手辦 / フィギュア style** | `--anime` *(prompt with "pvc figure …" → auto base-swap to PVC checkpoint)* |
| anime, high quality | `--anime --native-1080p` *(~320s)* |
| **turn a photo INTO anime** | `--anime --image /path/to/photo.jpg` *(img2img; add `--strength 0.5–0.8` to tune)* |
| edit a photo (non-anime) | `--image /path/to/photo.jpg` |

One-liner form (no separate activate) also works:

```bash
/home/chihmin/models-work/flux2/.venv-rocm72/bin/python \
  ~/.hermes/skills/create-image/scripts/create_image.py "YOUR PROMPT" --anime
```

Everything below is reference detail; the commands above are all you need to run it.

---

Generate or edit images with the local FLUX.2 deployment:

- Repo: `/home/chihmin/models-work/flux2`
- Venv: `/home/chihmin/models-work/flux2/.venv-rocm72`
- Runtime verified: `torch 2.12.1+rocm7.2`, HIP `7.2.53211`
- GPU: AMD Radeon 8060S
- Default model: `black-forest-labs/FLUX.2-klein-9B-kv`
- Fast preview model: `black-forest-labs/FLUX.2-klein-4B`

## Environment & setup (read before running)

Two independent backends, two venvs. ROCm `7.2.2` at `/opt/rocm-7.2.2`, GPU `gfx1151` (AMD Radeon
8060S) — **no `HSA_OVERRIDE_GFX_VERSION`** (gfx1151 is native; setting it breaks things on this box).

**Skill location:** real dir is `~/.hermes/skills/create-image`. The `~/.pi/agent/skills` and
`~/.claude/skills` directories are symlinks to `~/.hermes/skills/`, so the skill also resolves at
`~/.pi/agent/skills/create-image` and `~/.claude/skills/create-image` (any of these paths work in
commands). Scripts: `scripts/create_image.py` (entry), `scripts/anima.py` (anime backend),
`scripts/create_image_daemon.py` (the disabled FLUX daemon).

### FLUX.2 backend (default / photoreal / general)
- Repo `/home/chihmin/models-work/flux2`, venv `.venv-rocm72`. **Everything is already installed and
  every model already downloaded — do NOT `pip install` anything and do NOT download models.**
- Installed in `.venv-rocm72` (verified): `torch 2.12.1+rocm7.2` (HIP 7.2.53211),
  `torchvision 0.27.1+rocm7.2`, `diffusers 0.38.0`, `transformers 4.56.1`, `accelerate 1.12.0`,
  `safetensors 0.8.0`, `pillow 12.2.0`, `huggingface-hub 0.36.2`.
- Loading is done for you inside `create_image.py` via
  `from diffusers import Flux2KleinPipeline` → `Flux2KleinPipeline.from_pretrained(model_id,
  torch_dtype=torch.bfloat16).to("cuda")`. You don't write this — you run the script.
- Models already cached under `~/.cache/huggingface/hub/`: `FLUX.2-klein-9B-kv` (~33 GB, default),
  `FLUX.2-klein-4B` (fast preview), `FLUX.2-klein-9b-kv-fp8`. Loaded by HF id
  `black-forest-labs/FLUX.2-klein-9B-kv` (offline cache hit, no network).
- **Always activate this venv before running `create_image.py`** (it imports torch/diffusers):
  ```bash
  cd /home/chihmin/models-work/flux2
  source .venv-rocm72/bin/activate
  python ~/.hermes/skills/create-image/scripts/create_image.py "PROMPT" [flags]
  ```
- Env the script sets automatically (no need to export): `HF_XET_HIGH_PERFORMANCE=1`,
  `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1`.
- `CREATE_IMAGE_USE_DAEMON` — leave UNSET. Set to `1` only to opt back into the warm daemon (disabled
  by default, OOM risk — see "Warm daemon" below).

### Anime backend (`--anime`: ComfyUI + Anima)
- ComfyUI repo `/home/chihmin/src/ComfyUI`, venv `.venv`, HTTP API on `http://127.0.0.1:8188`.
  **Already installed; do NOT reinstall ComfyUI or its deps, and do NOT download the Anima models.**
- Installed in ComfyUI's `.venv` (verified): `torch 2.11.0+rocm7.2` (HIP 7.2.26015),
  `torchvision 0.26.0+rocm7.2`, `triton-rocm 3.6.0`, `safetensors 0.8.0`, `pillow 12.2.0`, plus the
  full ComfyUI `requirements.txt`. Uses ONLY built-in ComfyUI nodes (no custom nodes needed).
- The anime path in `anima.py` talks to ComfyUI over HTTP (it builds the node graph as JSON and POSTs
  to `/prompt`); it imports only `urllib` + `PIL`, NOT torch — so it runs fine from the FLUX venv.
- **You do NOT start ComfyUI manually** — `anima.py` auto-starts it (detached, from ComfyUI's own
  venv) if `:8188` isn't up, and waits until ready. The anime path itself only needs `urllib`+`PIL`,
  so it runs fine from the FLUX `.venv-rocm72` (i.e. the same activate step above works for `--anime`).
- Manual ComfyUI start, only if ever needed:
  ```bash
  cd /home/chihmin/src/ComfyUI && .venv/bin/python main.py --listen 127.0.0.1 --port 8188
  ```
- Anima model files (already downloaded, fixed locations under `ComfyUI/models/`):
  `diffusion_models/anima_baseV10.safetensors`, `text_encoders/anima_baseV10_txt.safetensors`,
  `vae/qwen_image_vae.safetensors`, `loras/gpt-image-2_anima-base1_v1-1.safetensors`.

### Memory / co-residency (important on this 122 GB UMA box)
- **Do NOT keep the FLUX warm daemon resident** and do NOT keep multiple big models loaded — it OOMs.
- Other always-on services (`qwen-mtp.service` ~43 GB GTT, etc.) coexist with normal image gen, but
  do NOT stop/kill them for image generation.
- ComfyUI/Anima (~6 GB GTT) is light; it can stay running between anime requests.

## Default mode

Default prioritizes quality while staying much faster than native 1080p:

1. Use `FLUX.2-klein-9B-kv`
2. Generate at `1360x768`
3. Lanczos upscale to exact `1920x1080`
4. Return the final `*_1080p.png`

```bash
cd /home/chihmin/models-work/flux2
source .venv-rocm72/bin/activate
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "PROMPT HERE"
```

Expected time: about 46 seconds of compute for 9B-KV `1360x768 → 1920x1080` run in-process, plus
model-load overhead each call (the warm daemon that used to amortize this is disabled — see below).

## Fast preview mode

When the user asks for quick preview / 快速預覽 / 草稿, use 4B:

```bash
cd /home/chihmin/models-work/flux2
source .venv-rocm72/bin/activate
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "PROMPT HERE" \
  --fast-preview
```

Fast preview uses `FLUX.2-klein-4B`, generates at `1024x576`, then upscales to exact `1920x1080`.
Expected warm time: about 6–7 seconds.

## Image editing / reference image

Image editing is supported in all modes. Add `--image /path/to/input.jpg`.

Default 9B edit:

```bash
cd /home/chihmin/models-work/flux2
source .venv-rocm72/bin/activate
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "Transform this image into a warm Japanese-style illustration" \
  --image /path/to/input.jpg
```

Fast preview edit:

```bash
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "Transform this image into a warm Japanese-style illustration" \
  --image /path/to/input.jpg \
  --fast-preview
```

Reference images are resized/padded to `768x432` for conditioning. Edited output uses the selected bucket:

- default: 9B-KV `1360x768 → 1920x1080`
- fast preview: 4B `1024x576 → 1920x1080`
- native/high quality: 9B-KV `1920x1088 → crop 1920x1080`

This is intentional: arbitrary output/reference shapes can trigger very slow ROCm VAE kernels.

## Native/high-quality 1080p mode

Use only when the user explicitly says high quality, high resolution, native, 原生1080p, 高畫質, 高解析度, or similar.

Native/high-quality mode uses the 9B-KV model, generates `1920x1088`, then center-crops to exact `1920x1080`.

```bash
cd /home/chihmin/models-work/flux2
source .venv-rocm72/bin/activate
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "PROMPT HERE" \
  --native-1080p
```

Expected warm time: about 195 seconds. Avoid VAE tiling for native 1080p because it can take 10+ minutes on this ROCm/iGPU setup.

## Anime / 二次元 mode (Anima backend)

For anime / 二次元 / 動漫 / 美少女 / 插畫 / waifu / illustration-style requests, use the
**Anima** backend instead of FLUX.2 by adding `--anime`. This routes to ComfyUI + the Anima
checkpoint (NVIDIA Cosmos-Predict2-2B finetune) + the `@gpt-image-2` style LoRA. The trigger word
`@gpt-image-2` is prepended automatically.

Default anime behaviour (fast, recommended): generate at **720p (1280x720)** — inside Anima's
512–1536 trained range — then **Lanczos upscale to exact 1920x1080**. **No hi-res fix** (a 2nd
diffusion pass at 1080p barely saves time on this GPU and isn't worth it).

```bash
cd /home/chihmin/models-work/flux2
source .venv-rocm72/bin/activate
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "a cute anime girl with twin tails, school uniform, cherry blossoms" \
  --anime
```

Expected warm time: about **70 seconds** for `1280x720 -> 1920x1080` (30 steps, er_sde, cfg 5).

High-quality / native anime 1080p — only when the user explicitly asks for high quality / 原生1080p /
高畫質 / native:

```bash
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "PROMPT" --anime --native-1080p
```

Native anime generates `1920x1088` directly then center-crops to `1920x1080`. Expected warm time:
about **320 seconds** (~4x slower than the 720p upscale path; quality is higher and avoids the slight
over-range artifacts of pushing beyond 1536).

Anima specifics (fixed, no need to change):
- diffusion model `anima_baseV10.safetensors`, text encoder `anima_baseV10_txt.safetensors`
  (CLIPLoader type `qwen_image`), VAE `qwen_image_vae.safetensors`, LoRA
  `gpt-image-2_anima-base1_v1-1.safetensors` at strength 1.0.
- defaults: steps 30, cfg 5.0, sampler `er_sde`, scheduler `simple`. Override with `--steps` /
  `--guidance-scale` / `--lora-scale` if asked.
- ComfyUI (port 8188, repo `/home/chihmin/src/ComfyUI`) is started on demand if not already running.

### Photo → anime (img2img)

**First step whenever an input image is given: open and look at the image** to decide if it's already
anime/二次元 or a real photo — that determines the backend (Anima for anime targets, FLUX for photoreal
edits) and a sensible `--strength`.

Turn a normal photo into anime style: add `--anime --image /path/to/photo.jpg`. The photo is
cover-cropped into an aspect-preserving /16 bucket (landscape `1280x720`, portrait `720x1280`,
square `1024x1024`), VAE-encoded, then partially re-diffused and Lanczos-upscaled (long side 1920).

```bash
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "anime girl, beautiful detailed illustration" \
  --anime --image /path/to/photo.jpg
```

- `--strength` controls the denoise (0.0–1.0, default **0.65**). **Let the user drive it by feedback:**
  - If the user says it looks **too different from the original photo** (lost the face/composition),
    **lower** `--strength` (e.g. 0.55 → 0.45 → 0.35) and regenerate.
  - If the user says it's **not anime enough** (still looks like a photo), **raise** `--strength`
    (e.g. 0.7 → 0.8) and regenerate.
  - Keep the same `--seed` when tuning strength so only the style amount changes.
- A short prompt still helps steer the style (`@gpt-image-2` trigger is auto-added).
- Warm time ≈ **70 s** (same as 720p text2img). Output preserves the photo's orientation.

### PVC figure style (auto)

When the user asks for **PVC / figure / 手辦 / フィギュア / figma** style, the anime path auto-switches
to PVC mode: it **swaps the base diffusion model** to `PVCStyleModelMovable_anima10.safetensors`
(Civitai 338712 v2998722 — a full Anima fine-tune, ~4 GB; it's a checkpoint, NOT a LoRA) and **keeps
the `@gpt-image-2` LoRA on top**, prepending `pvc figure, pvc style,` to the prompt. Triggered by
prompt keywords `pvc / figurine / 手辦 / 手办 / フィギュア / figma`, so usually no flag is needed:

```bash
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "a pvc figure of an anime girl in a dynamic battle pose, glossy finish, figure stand" --anime
```

- Works with text2img and `--image` (photo → PVC figure). ~70 s at 720p→1080p.
- File location: `ComfyUI/models/diffusion_models/PVCStyleModelMovable_anima10.safetensors`.

### Chaining multiple Anima LoRAs

`--loras "name:strength,name2:strength2"` stacks an explicit LoRA chain (e.g.
`--loras "gpt-image-2_anima-base1_v1-1:1.0,some_other_anima_lora:0.7"`). **Anima-base LoRAs only** —
Flux/SDXL/Illustrious LoRAs will NOT load (architecture mismatch). Note many Civitai "Anima" entries
are full checkpoints rather than LoRAs (like PVC above) — those are base swaps, not chain entries.

## Named character requests (search for a reference first)

If the user asks for a specific named character (an anime/game/VTuber/cartoon/celebrity character —
anything you think is a real, identifiable character), **don't rely on the prompt alone**:

1. **Search the web** for the character (e.g. WebSearch / image search) to confirm who they are and
   what they look like.
2. **Prefer full-body (全身) reference images** of the character (search terms like "<name> full body
   / 全身 / full body reference"); a clear full-body shot is best, then half-body, then a clean
   portrait as last resort. **Download a candidate, then OPEN/READ it to verify it's actually a usable
   character picture** — i.e. a clear single depiction of the character or official CG/illustration,
   NOT a logo, banner, text, meme, collage/grid, thumbnail, or an unrelated image. If it's not a good
   (ideally full-body) character reference, **try the next candidate**. Give it **up to 20 attempts**.
3. **If none of the 20 candidates is a usable reference, fall back to generating from the textual
   description** you found on the web (hair/eye color, outfit, distinguishing features) — write those
   details into the prompt and generate without an `--image` reference.
4. When you do have a good reference, judge whether the character is anime/二次元 or a real-life/photoreal
   person, then use it as the input image so the result actually resembles the character:
   - anime/illustrated character → `--anime --image <ref>` (Anima img2img), with a prompt naming the
     character + desired scene; tune `--strength` (lower keeps the character closer to the reference).
   - real/photoreal person → `--image <ref>` on FLUX (or `--anime --image` if they want them in anime
     style).
5. Still attach the final generated image to the user (see guardrails).

Only skip the search if the character is generic/original (e.g. "a cat girl", "a knight") — then just
generate from the prompt.

## Warm daemon (DISABLED by default — OOM risk)

A local daemon (`create-image-daemon.service`, port 7862) *can* keep the FLUX.2 9B-KV pipeline
resident, but **it is disabled by default and should stay that way**: keeping 9B resident alongside
the other local models on this box (qwen-mtp, ComfyUI/Anima) **OOMs the machine**. Every request now
runs **in-process** instead, which is reliable.

- Do NOT `enable`/`start` `create-image-daemon.service` and do NOT keep the FLUX pipeline resident.
- The service is left `disabled`. `create_image.py` no longer contacts the daemon by default
  (`should_try_daemon` is gated behind env `CREATE_IMAGE_USE_DAEMON=1`).
- Only if you have explicitly freed enough memory and want the warm path: set
  `CREATE_IMAGE_USE_DAEMON=1` and start the service manually. Otherwise leave it off.

## Useful flags

```bash
--image /path/to.jpg     # optional reference image for image editing
--fast-preview           # use 4B at 1024x576 then upscale; for quick drafts
--model 4b|9b|auto       # optional explicit model override; auto defaults to 9B unless --fast-preview
--no-daemon              # disable warm daemon routing and run in-process
--daemon-url URL         # default http://127.0.0.1:7862
--lora-scale 0.8         # anime (--anime) LoRA strength; default 1.0 for the @gpt-image-2 LoRA
--loras "a:1.0,b:0.7"    # anime: explicit Anima-base LoRA chain (overrides the auto chain)
--seed 123               # reproducible image
--out-dir /path          # output folder
--prefix name            # output filename prefix
--steps 4                # default / fixed distilled step count
--output-size 1080x1440  # force a custom final size via post-processing
--native-1080p           # force native 1920x1088 then crop to 1080p (FLUX or, with --anime, Anima)
--anime                  # anime/二次元 path: ComfyUI + Anima + @gpt-image-2 LoRA (720p->Lanczos 1080p)
--strength 0.65          # with --anime --image: photo->anime denoise (higher=more anime, default 0.65)
```

The script prints JSON containing final image path and timing fields. Attach the `final_path` image to Discord replies.

## Guardrails

- **ALWAYS deliver the generated image to the user.** After a successful run, you MUST send/attach the
  `final_path` PNG file in your reply (on Discord, attach it via the reply tool's files). Never just
  report the path, describe the image, or say "done" — the actual image file must reach the user every
  time an image is generated.

- For anime / 二次元 / 動漫 / 美少女 / 插畫 / waifu / illustration requests, use `--anime` (Anima
  backend). Default to the 720p→Lanczos 1080p path (no hi-res fix); use `--anime --native-1080p`
  only when high quality / 原生1080p / 高畫質 is explicitly requested. All other rules below are
  FLUX.2-only and unchanged.
- **Named character requests:** if the user asks for a specific identifiable character and no image is
  attached, FIRST web-search the character and (if possible) download a reference image, judge whether
  it's anime/二次元, and use it as the `--image` reference so the result resembles them (see "Named
  character requests"). Skip only for generic/original subjects.
- **When the user provides an input image, FIRST read/view that image** (open it and look) to judge
  whether it is already anime/二次元 (illustration, drawn) or a real photo, before generating. Use
  that judgement to pick the mode: anime/illustration source or an anime/PVC target → Anima
  (`--anime --image`, img2img); a real photo you want kept photoreal/edited → FLUX (`--image`). If the
  source is already anime and the user wants a different anime style (e.g. PVC), keep `--anime --image`
  and a lower `--strength` to preserve the original character.
- Photo→anime (`--anime --image`) uses `--strength` (default 0.65). Tune it from user feedback:
  too far from the original → lower it; not anime enough → raise it; keep `--seed` fixed while tuning.
- PVC / figure / 手辦 / フィギュア style requests: keep `--anime` and include "pvc figure" in the prompt;
  the script auto-swaps to the PVC Anima checkpoint + @gpt-image-2. Don't try to load PVC as a LoRA
  (it's a full checkpoint). Only Anima-base LoRAs/checkpoints work on the Anima backend.
- Do NOT enable or keep the FLUX warm daemon resident (it OOMs the box); all requests run in-process.
- Prefer default 9B-KV `1360x768 → 1920x1080` mode for normal (non-anime) requests.
- Use `--fast-preview` / 4B only when the user asks for quick preview / 快速預覽 / 草稿.
- Use `--native-1080p` / 9B native only when the user asks for high quality / 高畫質 / native / 原生1080p.
- Keep the ROCm/VAE buckets fixed: 9B default output `1360x768`, 4B preview output `1024x576`, reference conditioning `768x432`, native output `1920x1088`; avoid direct arbitrary 4:3 / 1:1 generation because VAE decode can take several minutes on ROCm.
- Do not kill, stop, or restart `llama-server` / `qwen-mtp.service` for image generation.
- Do not enable VAE tiling for 1080p unless debugging; it is stable but very slow.
- If native 1080p OOMs or available memory is too low, report the issue and fall back to default upscale mode instead of stopping other services.
- Always report generation time from the JSON `timings` object when benchmarking.
