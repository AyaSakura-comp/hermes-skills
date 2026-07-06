---
name: create-image
description: Generate or edit images locally (FLUX.2 + Anima on ROCm 7.2). Use for /create-image or any request to create/generate/edit/convert an image (incl. photo→anime, photo→PVC). IMPORTANT FOR AGENTS - image generation is ALREADY DEPLOYED here; do NOT write your own diffusers/Stable-Diffusion/FLUX script and do NOT download models - RUN THIS SKILL'S SCRIPT. To run, activate the FLUX venv then call the script (works for all modes including anime/PVC, which only need urllib+PIL)- `cd /home/chihmin/models-work/flux2 && source .venv-rocm72/bin/activate && python ~/.hermes/skills/create-image/scripts/create_image.py "PROMPT" [flags]` - it prints JSON; attach its final_path PNG. Flags - (none)=FLUX.2 photoreal 1080p default; --fast-preview=quick draft; --native-1080p=high quality; --anime=anime/二次元/動漫/美少女/插畫/waifu (ComfyUI+Anima); --anime --image PHOTO=photo→anime img2img (--strength tunes how anime); --refcontrol --image PHOTO "style"=change a PHOTO's style keeping structure (depth+ref lock + style LoRA; THE photo 改風格 path); PVC/figure/手辦/フィギュア prompts auto-switch to the Anima PVC checkpoint (use --anime). Read SKILL.md body for env/models/details before improvising.
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
# Prepend FLUX2_BIG_WMMA_LINEAR=1 to enable custom tuned wmma kernel acceleration
FLUX2_BIG_WMMA_LINEAR=1 python ~/.hermes/skills/create-image/scripts/create_image.py "YOUR PROMPT HERE"
```

That prints a JSON object — take the `final_path` field and **you MUST attach that PNG file in your
reply to the user** (on Discord, include `[[image: /path/to/file.png]]` in your reply so it sends as a real
attachment). Never just report the path or describe the image in text without attaching the actual file.

Pick the mode by what the user asked for:

| User wants | Command (append to the `python … create_image.py "PROMPT"` line) |
|---|---|
| normal / photo / general (default) | *(nothing — default 9B → 1080p, ~25–60s)* |
| quick draft / 快速預覽 / 草稿 | `--fast-preview` *(4B, ~7s)* |
| high quality / 原生 / 高畫質 / native | `--native-1080p` *(~195s for 16:9; for FLUX 1080p photo look prefer `--aspect-ratio 3:2`, see note below)* |
| **anime / 二次元 / 動漫 / 美少女 / 插畫 / waifu** | `--anime` *(MANDATORY: 二次元一定走 Anima; default 2:3 portrait, 768x1152→1184x1776, ~60s; cfg 5.0 default)* |
| **PVC figure / 手辦 / フィギュア style** | `--anime` *(prompt with "pvc figure …" → auto base-swap to PVC checkpoint)* |
| anime, high quality | `--anime --native-1080p` *(~320s at default cfg 5.0; ~160s if you drop to `--guidance-scale 1`)* |
| **turn a photo INTO anime** | `--anime --image /path/to/photo.jpg` *(img2img; add `--strength 0.5–0.8` to tune)* |
| **sketch / 草稿 → finished anime CG** | `--anime --image /path/to/sketch.jpg --strength 0.9 --guidance-scale 2` *(default for rough sketches; first understand the sketch and write a detailed Anima prompt)* |
| **change a PHOTO's style / 改風格 (keep structure)** | `--refcontrol --image PHOTO "<style direction>"` *(depth+ref lock structure; THE photo restyle path — see RefControl section)* |
| edit a photo (non-anime, freeform) | `--image /path/to/photo.jpg` |
| **Fuji / analog film / 富士底片 / 膠卷 look ON A PHOTO** | *(auto — film keywords + `--image` run the RefControl flow; structure-locked film restyle)* |
| **Fuji / analog film look (text2img, no photo)** | *(auto — keywords trigger the Analog Redmond LoRA; or force with `--film`)* |

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
  `vae/qwen_image_vae.safetensors`, `loras/gpt-image-2_anima-base1_v1-1.safetensors`. Additional artist-style LoRAs:
  - **Kanzarin LoRA**: `loras/kanzarin_v1_step1500.safetensors` (Civitai 1793178 v2980620; trigger `@k4nz4r1n`).
  - **Dropkun LoRA**: `loras/dolphro-kun_v1_step400.safetensors` (Civitai 1709811 v2969468; trigger `@dropkun`).
  These are chained using the `--loras` parameter rather than hardcoded in the Python script.

### FLUX.2 film / analog style LoRA (Analog Redmond)

For a **Fuji / analog-film photography** look, the FLUX.2 path applies artificialguybr's *Analog
Redmond* LoRA (for FLUX.2-klein-9B). It's **generative** and loaded **on demand** — only when
requested — so normal generation is unaffected. (There is no non-generative color-grade path; style
changes always go through generation.) For style transfer with a reference image, keep the prompt to
the style trigger words + target style — don't list the objects in the source photo.

- **Auto-trigger**: if the prompt mentions film/analog terms (`fuji`, `fujifilm`, `富士`, `底片`,
  `膠卷`/`胶卷`, `菲林`, `膠片`/`胶片`, `analog`, `analog film`, `film grain`, `film camera`, `35mm`,
  `filmic`, `disposable camera`, …) the LoRA auto-loads (skip with `--no-auto-lora`). Bare "film" does
  NOT trigger it (avoids "film director" etc.). **Note:** if `--image` is also present (a photo), these
  same keywords instead route to the **RefControl flow** (structure-locked film restyle, see that
  section) — the plain analog-LoRA path here is for text2img / no-image runs.
- **Force it**: `--film` (aliases `--analog`, `--fuji`).
- Trigger words `analog, AnalogRedmAF,` are **prepended automatically** (use this order for plain/ordinary film style); weight = `--lora-scale`
  (default 0.8). Adapter is loaded via `pipe.load_lora_weights(...)` + `set_adapters(["analog"], [scale])`.
- **9B only** (the 4B fast-preview model has no matching LoRA; the LoRA is skipped under `--fast-preview`).
- File: `/home/chihmin/models-work/flux2/loras/analog_redmond_fluxklein9b.safetensors` (~166 MB,
  from `artificialguybr/ANALOG-REDMOND-FLUXKLEIN9B`). The JSON result reports the applied LoRA under
  `lora` and the final prompt under `prompt_used`.

```bash
# auto (keyword) — analog LoRA applied automatically
python ~/.hermes/skills/create-image/scripts/create_image.py "a Tokyo street in summer, Fujifilm analog film look, warm grain"
# forced on any prompt
python ~/.hermes/skills/create-image/scripts/create_image.py "portrait of a girl by a window" --film
```

#### Proven template — user says 「底片風 f1.2」 / 「F1.2 底片風」 on an uploaded photo

Use this exact style prompt as the **fixed film base** with the user's uploaded photo; if the user
adds more style words, append them **after** this base. **Do not substitute a non-generative
post-processing filter** and do not add subject/scene descriptions unless the user requests content
changes:

```text
analog, AnalogRedmAF, F1.2 shallow depth of field, 35mm analog film photo, soft contrast, fine film grain, subtle halation, cinematic bokeh
```

Recommended LoRA settings from successful local runs:

- LoRA file: `/home/chihmin/models-work/flux2/loras/analog_redmond_fluxklein9b.safetensors`
- Adapter name: `analog`
- `--lora-scale` / adapter weight: `0.85`
- Use the uploaded image as `--image`; portrait photos should stay 2:3 (`832x1248 → 1184x1776`), landscape photos 3:2 (`1248x832 → 1776x1184`).
- Reply should state that Analog Redmond LoRA was actually loaded, and attach the generated image.

Sample command for an uploaded portrait photo:

```bash
cd /home/chihmin/models-work/flux2
source .venv-rocm72/bin/activate
python ~/.hermes/skills/create-image/scripts/create_image.py \
  "analog, AnalogRedmAF, F1.2 shallow depth of field, 35mm analog film photo, soft contrast, fine film grain, subtle halation, cinematic bokeh" \
  --image /path/to/uploaded-photo.jpg \
  --lora-scale 0.85 \
  --steps 2
```

Perf note from the cat-photo regression sample (`832x1248 → 1184x1776`, RefControl + Analog LoRA):
`--steps 2` is about 108s end-to-end / 90s warm generate; default `--steps 4` is about 193s end-to-end.

### Color tone / 色調 in the prompt

Color tone is set by **style words in the prompt**, separate from the subject/content words and from the
LoRA weight. Three independent levers for the look:

1. **LoRA trigger** (`analog, AnalogRedmAF`) — activates the film LoRA at all.
2. **`--lora-scale`** — overall strength of that LoRA (0.4–0.5 subtle, 0.8 default, 1.0 strong).
3. **Color-tone words in the prompt** — steer the *palette* itself. These work with or without the LoRA.

Useful color-tone vocabulary (add to the style group, not the content group):

- **Warm / cool**: `warm tones`, `golden / amber tone`, `warm Kodak Portra tones`; `cool tones`,
  `teal shadows`, `cyan-green cast` (Fuji look), `blue hour`.
- **Saturation**: `muted colors` / `desaturated`, `pastel palette`, `vivid / saturated colors`.
- **Contrast & blacks**: `soft / low contrast`, `lifted / faded blacks`, `washed-out`, `high contrast`.
- **Film stocks** (each carries a palette): `Kodak Portra` (warm skin), `Fujifilm / Fujicolor`
  (green-cyan), `Cinestill 800T` (tungsten teal + red halation), `Kodak Gold` (warm nostalgic).
- **White balance / light**: `daylight`, `tungsten / warm indoor`, `golden hour`, `overcast cool`.
- **Mono**: `black and white`, `sepia`, `monochrome`.

To change **only the tone**, edit these words and keep `--seed` fixed (and the same `--lora-scale`);
to change strength of the whole film effect, move `--lora-scale`. e.g. swap `warm Kodak Portra tones`
→ `cool Fuji green-cyan tones` for a cooler palette at the same composition.

### RefControl restyle path — `--refcontrol` (THE path for changing a photo's style)

**When the user uploads a PHOTO and wants to change its style, use `--refcontrol`.** It locks the
original structure with a **depth map** while a **style LoRA** restyles — ControlNet-style img2img on
FLUX.2-klein, **no dev model needed**. (For an already-anime/二次元 source, still use the Anima path
`--anime --image`; refcontrol is the FLUX.2 photographic restyle path.)

**Prompt discipline for photo style changes (preserve composition):** if the user is only asking to
change the *look* of an existing photo (底片風, Fuji, Leica, F1.2/bokeh look, color tone, cinematic,
etc.), keep the prompt **minimal style-only**. Do **not** add subject descriptions, scene descriptions,
quality tags, or extra composition instructions (e.g. avoid "主體狐獴清晰銳利", "photorealistic",
"glass reflections", "foreground natural") unless the user explicitly asks to change content. Extra
content words make the model re-compose/re-draw the scene. Good prompts: `底片風`, `F1.2 大光圈`,
`F1.2 大光圈，底片風`, `cool Fuji green-cyan tones`. Bad prompts: long descriptions of what is already
in the image.

> **AUTO-TRIGGER — 底片風 / film style on a photo.** If the user asks for a **film / 底片 / 膠卷 /
> fuji / analog** look on an **uploaded photo**, the script **auto-runs this RefControl flow** (you
> don't need to pass `--refcontrol` — any of the film/analog keywords + `--image` triggers it; the
> analog LoRA + tuned grade are applied automatically). Disable with `--no-auto-lora`. Film keywords
> *without* an image (text2img) just apply the analog LoRA on the normal FLUX path instead.
>
> **🔒 LOCKED prompt for 底片風 (do NOT improvise).** The film look is forced to one fixed canonical
> **base** prompt — `refcontrol, analog, AnalogRedmAF, ` + the tuned grade (`deep shadows,
> natural color with slight desaturation, crisp sharp rendering, fine grain, editorial mood`). If the
> user adds extra free-text style words, the script keeps this fixed film base first and **appends the
> extra words after it**. Don't try to tweak the film base itself via the prompt — just pass the photo
> with a film keyword and any extra style words you want to keep. (Only *non-film* refcontrol
> restyles, e.g. an explicit custom direction like "leica reportage", use free-text words.)

```bash
cd /home/chihmin/models-work/flux2 && source .venv-rocm72/bin/activate
python ~/.hermes/skills/create-image/scripts/create_image.py "<style direction>" \
  --refcontrol --image /path/to/photo.jpg
# e.g. "warm vintage fujifilm film, golden hour"  or  "cool teal cinematic, overcast"
```

**What it does (and the full environment it sets up — all handled by the script):**
- **Depth map** of the input via **Depth Anything V2 (ViT-L)** = `depth-anything/Depth-Anything-V2-Large-hf`
  through `transformers` (matches the LoRA's training preprocessor). ~2.5 s.
- **Two LoRAs stacked** (both in `/home/chihmin/models-work/flux2/loras/`):
  - `refcontrol_klein9b_depth.safetensors` — structure, trigger word `refcontrol`, weight `--refcontrol-scale` (default **1.0**). From `thedeoxen/refcontrol-FLUX.2-klein-9B-reference-depth-lora`.
  - `analog_redmond_fluxklein9b.safetensors` — style (film), triggers `analog, AnalogRedmAF`, weight `--lora-scale` (default **0.55** on this path). Skipped gracefully if absent.
- **Conditioning** = `image=[reference, depth]` (FLUX.2 native multi-reference); both resize-then-cropped to the gen bucket (aspect from the photo's orientation: vertical→2:3, horizontal→3:2).
- **Prompt assembled automatically** = `refcontrol, analog, AnalogRedmAF, <your style words>, ` + the tuned grade `deep shadows, natural color with slight desaturation, crisp sharp rendering, fine grain, editorial mood`. So you only pass the *style direction*; triggers + grade are added for you.
- **Steps** = `--steps` or **5** by default (klein is few-step distilled; 5 ≈ 20-step quality). **9B only** (4B has no matching LoRA; `--fast-preview` is ignored here).
- **Env set by the script**: `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1` (AOTriton flash — **REQUIRED**; without it the dual-reference attention materializes the N² matrix → OOM / ~30 min), `MIOPEN_FIND_MODE=FAST` + persistent `MIOPEN_USER_DB_PATH=~/.cache/miopen-flux2` (VAE convs), `HF_XET_HIGH_PERFORMANCE=1`.
- **Custom Tuned wmma Linear Kernel acceleration**: Prepended environment variable `FLUX2_BIG_WMMA_LINEAR=1` is **REQUIRED** to enable the custom GOMEA-tuned `v_wmma` BF16 linear kernel (specifically optimizing the huge `12168, 4096, 4096` matrix shape). Without it, PyTorch runs default Tensile, which is slightly slower.
- **Global contiguous-SDPA patch** (top of `create_image.py`, applies to ALL FLUX.2 runs): forces q/k/v
  `.contiguous()` before SDPA because AOTriton `attn_fwd` is ~2.5× slower on the non-contiguous tensors
  diffusers passes. **Bit-exact** (verified max|Δ|=0; dual-ref step 38.4 s→14.8 s). Disable with
  `CREATE_IMAGE_NO_CONTIG=1`.

**Performance / memory (gfx1151):** ~**90 s** for a 5-step 832×1248 restyle. The denoiser cost is
attention-dominated above ~6–8k tokens (dual-reference = 3× tokens ≈ 12168 → past the cliff); the
contiguous patch is what keeps it at ~15 s/step instead of ~40 s. Coexists with `qwen-mtp` (flash keeps
memory bounded) — **do not stop qwen for it**. If you ever run this as a detached background job, use
`setsid` (a plain `nohup &` gets SIGKILL'd with the process group at a turn boundary).

**Tuning:** style direction (your prompt words) drives the look; `--lora-scale` = film strength
(0.4 subtle … 0.9 strong; default 0.55); `--refcontrol-scale` = how hard structure is locked (default
1.0); keep `--seed` fixed while tuning one variable. The JSON result reports `prompt_used`, both LoRA
scales, and `depth_model`.

### Memory / co-residency (important on this 122 GB UMA box)
- **Do NOT keep the FLUX warm daemon resident** and do NOT keep multiple big models loaded — it OOMs.
- Other always-on services (`qwen-mtp.service` ~43 GB GTT, etc.) coexist with normal image gen, but
  do NOT stop/kill them for image generation.
- ComfyUI/Anima (~6 GB GTT) is light; it can stay running between anime requests.

## Default mode

Default prioritizes quality while staying much faster than native 1080p:

1. Use `FLUX.2-klein-9B-kv`
2. Generate at `1360x768` (16:9 landscape)
3. Lanczos upscale to exact `1920x1080`
4. Return the final `*_1080p.png`

**Important FLUX/photo sizing convention:** when a user says **1080p** for a photo/film-style image,
interpret it as **1080p-equivalent pixels in the 3:2 photo aspect**, i.e. final `1776x1184`, not
necessarily video-shaped `1920x1080`. Use `--aspect-ratio 3:2`; if they also say **native / 原生 / 高畫質**,
use `--aspect-ratio 3:2 --native-1080p` so generation happens directly at `1776x1184`. Only use 16:9
`1920x1080` when the user explicitly asks for 16:9 / widescreen / video wallpaper.

FLUX supports `--aspect-ratio`, but keep FLUX text-to-image default at 16:9 when no 1080p/photo sizing
is requested. For FLUX edits with `--image` and no explicit `--aspect-ratio`, the script follows the
source orientation and uses a 1080p-equivalent photo bucket: landscape sources become `3:2`
(`1248x832 → 1776x1184`), portrait sources become `2:3` (`832x1248 → 1184x1776`), and square sources
become `1:1`.

```bash
cd /home/chihmin/models-work/flux2
source .venv-rocm72/bin/activate
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "PROMPT HERE"
```

Expected time: about 22–46 seconds of compute for 9B-KV `1360x768 → 1920x1080` run in-process, plus
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

> **HARD RULE — user uploaded image means img2img/reference-conditioned generation.** If the user
> attaches or provides an image and asks to generate, redraw, convert, CG-ify, restyle, edit, improve,
> or make a new version from it, you **must pass that exact user-provided image via `--image`**. Do not
> ignore the attachment and run pure text-to-image. Use the image as the composition/content source;
> choose the backend from the image/request: anime/illustration target or source, **or any explicit
> anime/二次元/插畫 output request** → `--anime --image` (even if the source image is a real photo),
> real-photo photoreal edit → FLUX `--image`, photo style-change → `--refcontrol --image`. Only skip
> `--image` when the uploaded file is explicitly just informational/context and the user clearly asks
> for unrelated text-to-image.

> **⚠️ Restyle requests on an uploaded image — judge the SOURCE first (REQUIRED).**
> When the user sends an image and asks to **change/convert its style** ("把這張改成…", "make this
> into … style", "turn this into …"), the FIRST step is to **open/view the image and decide whether
> the source is anime / 二次元 / illustration / drawn**:
> - **Source is anime/二次元/illustration → use the Anima backend: `--anime --image <img>`** (Anima
>   img2img). This applies even if the user doesn't say the word "anime" — if the picture is already
>   a drawing/二次元, route to Anima. Tune `--strength` (lower = stay closer to the original art).
> - **Source is a real photo but the user explicitly asks for anime/二次元/插畫 output → use
>   `--anime --image PHOTO`** (Anima img2img). Explicit target style wins over source type.
> - **Source is a real photo + wants a non-anime photoreal style change (different look, keep the scene) → use
>   `--refcontrol --image PHOTO "<style direction>"`** (the RefControl restyle path: depth+reference
>   lock structure while a style LoRA restyles — see "RefControl restyle path"). This is the default
>   for photo 改風格 when the target is still photoreal/non-anime. Other photo targets: PVC/figure →
>   `--anime` with "pvc figure"; a freeform non-style edit → plain `--image`.
>
> Do NOT send an already-二次元 image through the FLUX photoreal path for a style change — use Anima.

### Build the edit prompt: read the image first, then describe "from → to"

Whenever the user uploads an image to **edit or restyle** (FLUX `--image` *or* Anima `--anime --image`),
first **actually look at the image** to choose the correct backend and understand what should be preserved.
For **pure style-change requests** (e.g. "改成底片風格", "make it watercolor", "turn this into anime"),
keep the generation prompt **as short as possible and only include the target style / LoRA trigger words** —
do NOT describe the source scene, subject, objects, composition, pose, lighting, or what to preserve. The
input image already supplies all content; verbose source descriptions make FLUX/ComfyUI reinterpret and
redraw the scene. If a style LoRA is used, the prompt should usually be just the LoRA-required trigger plus
minimal style words. For film/底片 on a photo, the fixed film base is always applied first and any extra
style words are appended after it. Avoid extra words that push the image toward harsh lighting or blown
highlights (e.g. 強光、高光、過曝、hard light、harsh light、overexposed). Example for Analog Redmond:
`analog, AnalogRedmAF, ordinary 35mm analog film photo, soft contrast, subtle film grain, mild halation`.

For **content edits** (adding/removing/changing objects, pose, scene, lighting direction, etc.), then write
a prompt that states the **original state** and the **desired change** so the model knows what to preserve
and what to alter. Both backends follow prompts better when content changes are explicit.

1. **Read the source image** — note the concrete elements:
   - **Scene / setting & details**: location, time of day, season, weather/atmosphere. Read the
     **scene depth in layers — foreground / midground / background** — and note what's in each:
     props, objects, furniture, environment elements, signage/text, background characters or crowds,
     architecture/landscape. Note clutter vs. minimal, and small telling details (textures, plants,
     reflections) that should be preserved or changed.
   - **Subject(s) / characters**: who/what, count, pose, expression, clothing, framing (close-up,
     full-body), where they sit in the frame.
   - **Action / motion**: what the subject is *doing* — the implied action, gesture, or movement
     captured (running, mid-jump, reaching, turning, hair/cloth in motion), direction of movement,
     and any sense of speed/dynamism vs. a static pose.
   - **Composition**: shot type, camera angle/height, lens feel (wide/telephoto), rule-of-thirds /
     symmetry / leading lines, perspective.
   - **Lighting & color**: light direction & quality (soft/hard), key/rim/ambient, time-of-day light,
     color palette, mood/contrast, shadows.
   - **Style/medium**: photo vs illustration vs 3D, art style, texture, grain.
2. **If it is only a style change, use only style words in the prompt.** Avoid restating the cat/person,
   room, pose, objects, or composition unless the user explicitly wants those changed. Example:
   *`35mm analog film photo, warm Kodak Portra tones, subtle film grain, soft halation, gentle faded
   contrast, natural handheld snapshot`*.
3. **If it is a content edit, compose the prompt as "from → to"**: briefly describe the original parts to
   KEEP, then clearly state what to CHANGE. Example: *"A young woman standing centered, three-quarter
   view — keep her pose, face and composition; change the background into a rainy neon Tokyo street."*
4. **Keep what the user didn't ask to change.** For content edits, naming preserved elements (pose, face,
   layout, lighting direction) stops drift. For pure style changes, keeping the prompt short is usually the
   best way to preserve the input. Tune adherence with `--strength` (Anima img2img) and keep `--seed`
   fixed while iterating.

This applies to both backends — Anima for anime/二次元 sources or anime targets, FLUX for photoreal
edits (mode chosen by the rule above).

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

The reference image is **resized-then-center-cropped (cover, no distortion) to the generation/output
size** before conditioning — the aspect ratio is first derived from the input's orientation (read from
metadata/EXIF: vertical → `2:3`, horizontal → `3:2`, square → `1:1`), so the resize keeps proportions
and only crops overflow. Edited output uses the selected bucket:

- no explicit `--aspect-ratio`: follows source orientation with 1080p-equivalent photo buckets:
  - landscape source → `3:2`, 9B-KV `1248x832 → 1776x1184`
  - portrait source → `2:3`, 9B-KV `832x1248 → 1184x1776`
  - square source → `1:1`, 9B-KV `1024x1024 → 1440x1440`
- explicit `--aspect-ratio`: use the requested bucket (e.g. `16:9`, `3:2`, `2:3`, `1:1`)
- native/high quality: generate directly at the selected final bucket size, rounded to /16 as needed

This is intentional: arbitrary output/reference shapes can trigger very slow ROCm VAE kernels.

## Native/high-quality 1080p mode

Use only when the user explicitly says high quality, high resolution, native, 原生1080p, 高畫質, 高解析度, or similar.

For FLUX/photo requests, **1080p native means 3:2 1080p-equivalent by default**: add
`--aspect-ratio 3:2 --native-1080p` to generate `1776x1184` directly. For explicit 16:9 native,
`--native-1080p --aspect-ratio 16:9` generates `1920x1088`, then center-crops to exact `1920x1080`.

```bash
cd /home/chihmin/models-work/flux2
source .venv-rocm72/bin/activate
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "PROMPT HERE" \
  --native-1080p
```

Expected warm time: about 195 seconds. Avoid VAE tiling for native 1080p because it can take 10+ minutes on this ROCm/iGPU setup.

## Anime / 二次元 mode (Anima backend)

For anime / 二次元 / 動漫 / 美少女 / 插畫 / waifu / illustration-style requests, **ALWAYS use the
Anima backend** by adding `--anime`. **Do not use FLUX for 二次元/anime/illustration generation or
anime-style image edits.** This routes to ComfyUI + the Anima checkpoint (NVIDIA Cosmos-Predict2-2B
finetune) + the `@gpt-image-2` style LoRA. To stack other artist-style LoRAs (such as Kanzarin and Dropkun), use the `--loras` parameter explicitly (e.g. to combine both, pass `--loras "gpt-image-2_anima-base1_v1-1.safetensors:1.0,kanzarin_v1_step1500.safetensors:0.7,dolphro-kun_v1_step400.safetensors:0.7"`).

Default anime behaviour (fast, recommended): generate a **2:3 portrait** at `768x1152` — inside
Anima's 512–1536 trained range — then **Lanczos upscale to 1184x1776** (~1080p-equivalent pixels).
**No hi-res fix** (a 2nd diffusion pass barely saves time on this GPU and isn't worth it).
Use `--aspect-ratio 16:9`, `--aspect-ratio 3:2`, `--aspect-ratio 1:1`, etc. when the user asks for a
specific shape.

```bash
cd /home/chihmin/models-work/flux2
source .venv-rocm72/bin/activate
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "a cute anime girl with twin tails, school uniform, cherry blossoms" \
  --anime
```

Expected warm time: about **59–70 seconds** for `768x1152 -> 1184x1776` (30 steps, er_sde, **default cfg 5.0**). cfg 5 gives stronger prompt adherence; drop to `--guidance-scale 1` for the ~2x faster (~30s) path when adherence isn't critical.

High-quality / native anime 1080p — only when the user explicitly asks for high quality / 原生1080p /
高畫質 / native:

```bash
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "PROMPT" --anime --native-1080p
```

Native anime generates `1920x1088` directly then center-crops to `1920x1080`. Expected warm time:
about **320 seconds** at **default cfg 5.0** (about **160 seconds** if you drop to `--guidance-scale 1`);
quality is higher and avoids the slight over-range artifacts of pushing beyond 1536).

Anima specifics (fixed, no need to change):
- diffusion model `anima_baseV10.safetensors`, text encoder `anima_baseV10_txt.safetensors`
  (CLIPLoader type `qwen_image`), VAE `qwen_image_vae.safetensors`, LoRA
  `gpt-image-2_anima-base1_v1-1.safetensors` at strength 1.0. To use additional artist LoRAs (like Kanzarin or Dropkun), chain them explicitly via `--loras`.
- defaults: aspect ratio 2:3, steps 30, **cfg 5.0** (`ANIME_CFG` in `anima.py`), sampler `er_sde`,
  scheduler `simple`. Override with `--aspect-ratio`, `--steps`, `--guidance-scale` / `--lora-scale`
  if asked. cfg 5.0 is the default for stronger prompt adherence; `--guidance-scale 1` is ~2x faster
  if adherence isn't critical.
- ComfyUI (port 8188, repo `/home/chihmin/src/ComfyUI`) is started on demand if not already running.

### Anima prompting guide (official-style)

Anima's upstream/model-card guidance: it is an **anime / illustration / non-photorealistic** model; do
not prompt it like a realistic-photo model. It understands **Danbooru/Gelbooru-style tags**, **natural
language captions**, and mixtures of both.

**Recommended positive prefix** (put this at the start unless the user asks for a very specific raw style):

```text
masterpiece, best quality, score_7, safe,
```

**Recommended negative from the Anima guide** (not currently exposed by `create_image.py`; use as a
future implementation reference or if running a manual ComfyUI workflow):

```text
worst quality, low quality, score_1, score_2, score_3, artist name
```

**Tag order formula:**

```text
[quality/meta/year/safety tags], [1girl/1boy/1other], [character], [series], [artist/style], [general tags]
```

Good mixed tag + prose structure:

```text
masterpiece, best quality, score_7, safe, 1girl, character name, series name, highres, core appearance tags.
One sentence describing the scene/action/composition/camera.
One sentence describing color palette, lighting level, mood, and background detail.
```

**What to describe (priority order):**
1. **Character identity/count**: `1girl`, `1boy`, `solo`, character name, series name.
2. **Canonical appearance**: hair color/style, eyes, outfit, accessories, animal ears/tail, weapons/props.
   For named characters, always describe appearance; do **not** rely on the name alone.
3. **Pose/action**: sitting, running, leaping, holding a spear, looking at viewer, etc.
4. **Scene/background**: cafe, rooftop, mountain, classroom, fantasy ruins; include foreground/background if important.
5. **Composition/camera**: close-up, full body, low-angle wide shot, centered composition, dynamic diagonal composition.
6. **Style/mood/color/light**: anime screenshot, official art, painterly anime style, muted colors, low contrast,
   overcast ambient light, dramatic rim light, etc.

**Tag hygiene:**
- Use lowercase for tags and spaces instead of underscores, except score tags like `score_7`.
- Prefer focused tags over exhaustive tag spam; Anima was trained with tag dropout, so not every detail is needed.
- Use Gelbooru-style tag names when Danbooru/Gelbooru differ.
- For artist tags, prefix with `@`. When using `--loras` manually, ensure you include the trigger words (like `@k4nz4r1n` or `@dropkun`) in the prompt if style activation requires them.
- Pure natural-language prompts should be at least **two descriptive sentences**; very short prompts can drift.
- Avoid asking Anima to render long text. If exact text is needed, add it later with an editor.

**Lighting auto-LoRA gotcha:** anime prompts containing lighting terms (`lighting`, `glow`, `rim light`,
`reflections`, `moonlit`, `volumetric`, etc.) auto-chain the lighting enhancer LoRA. If the user asks
for flat/no-light/low-light output, avoid those keywords and, if needed, override the chain explicitly:

```bash
--loras "gpt-image-2_anima-base1_v1-1.safetensors:1.0"
```

**Template for named characters:**

```text
masterpiece, best quality, score_7, safe, 1girl, <character>, <series>, highres,
<hair>, <eyes>, <outfit>, <signature accessories/ears/tail/weapon>.
She is <action> in <scene>, <composition/camera>.
<palette/light/mood>, detailed background, clean anime linework.
```

Example:

```text
masterpiece, best quality, score_7, safe, 1girl, Rossi, Arknights Endfield, highres,
petite wolf-girl, long light blonde hair, red wolf ears, red hooded cape, white short dress,
fluffy tan wolf tail, black thigh-high boots.
She sits by a cafe window reading a book, with a cup of coffee on a wooden table and potted plants nearby.
Muted matte colors, very low contrast, flat overcast ambient light, quiet slice-of-life mood, detailed cafe background.
```

### Sketch / rough draft → finished anime CG (img2img default)

When the user provides a **rough sketch / 草稿 / storyboard / pencil layout** and asks to turn it into
anime / 二次元 / CG / illustration, use Anima directly (or use a FLUX pencil-cleanup first only if the
user asks for that intermediate step). **Default command settings for rough sketches:**

```bash
--anime --image /path/to/sketch.jpg --strength 0.9 --guidance-scale 2
```

Why: `--strength 0.9` lets Anima fill in missing anatomy, faces, clothing, props, and finish quality;
`--guidance-scale 2` keeps the prompt influential without the harsh over-control/gray haze that higher
CFG can introduce on weak sketches. If the output drifts too far from the sketch, lower strength to
`0.75–0.85`; if it is not finished enough, keep strength high and improve the prompt.

**Prompting workflow (required): first understand the sketch, then complete it explicitly.** Before
running, inspect the image and write a prompt using Anima's tag+caption style:

1. Start with the Anima prefix and count tags: `masterpiece, best quality, score_7, safe, 1girl/2girls/1cat/...`.
2. Identify the sketch's **composition**: portrait/landscape, foreground/midground/background,
   camera angle, close-up/full-body, diagonals, symmetry, negative space, and where each subject sits.
3. Identify **subjects and actions**: character/animal count, pose, gesture, facial direction,
   interaction between subjects, props being held, motion lines or implied movement.
4. Fill in **missing character details** following the Anima guide: hair color/style, eye color,
   outfit layers, accessories, gloves/boots, weapons/props, animal ears/tail/wings/horns if implied,
   body type, expression, and overall color scheme.
5. Fill in **scene/background details** only when useful: room/cafe/sky/bed/curtain, foreground and
   background objects, atmosphere, but do not invent clutter that fights the sketch.
6. Add **style/mood/color/light**: `polished full-color anime CG illustration`, `crisp colored
   linework`, `smooth cel shading`, palette words, lighting/mood, and quality goals.
7. Add cleanup constraints when converting from a photo/sketch: `no whiteboard`, `no red marker lines`,
   `no photo glare`, `no gray haze`, `no pencil marks` (as applicable). Avoid long exact text requests.

Template:

```text
masterpiece, best quality, score_7, safe, <count tags>, <subject/style tags>, highres,
polished full-color anime CG illustration. Use the sketch as a <composition description>.
In the foreground/midground/background, <who is where, doing what, with what props>.
Fill in missing <faces/anatomy/hair/outfit/accessories/props/background>.
<palette>, crisp colored linework, smooth cel shading, <mood/lighting>, no <source artifacts>.
```

For sketch-to-CG style blending, prefer chaining `gpt-image-2` + Kanzarin + Dropkun LoRAs (see below)
with the same `--strength 0.9 --guidance-scale 2` defaults.

### Photo → anime (img2img)

**First step whenever an input image is given: open and look at the image** to decide if it's already
anime/二次元 or a real photo — that determines the backend (Anima for anime targets, FLUX for photoreal
edits) and a sensible `--strength`. Real photos without a rough-sketch/CG-completion request usually
start lower than sketch completion.

Turn a normal photo into anime style: add `--anime --image /path/to/photo.jpg`. The photo is
cover-cropped into an aspect-preserving /16 bucket (landscape `1280x720`, portrait `720x1280`,
square `1024x1024`), VAE-encoded, then partially re-diffused and Lanczos-upscaled (long side 1920).

```bash
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "anime girl, beautiful detailed illustration" \
  --anime --image /path/to/photo.jpg
```

- `--strength` controls the denoise (0.0–1.0, default **0.5**). **Let the user drive it by feedback:**
  - If the user says it looks **too different from the original photo** (lost the face/composition),
    **lower** `--strength` (e.g. 0.55 → 0.45 → 0.35) and regenerate.
  - If the user says it's **not anime enough** (still looks like a photo), **raise** `--strength`
    (e.g. 0.7 → 0.8) and regenerate.
  - Keep the same `--seed` when tuning strength so only the style amount changes.
- A short prompt still helps steer the style (`@gpt-image-2` trigger is auto-added).
- Warm time ≈ **60–70 s** at default cfg 5.0 (≈32–35 s if you drop to `--guidance-scale 1`). Output preserves the photo's orientation.

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

- Works with text2img and `--image` (photo → PVC figure). ~60–70 s at 720p→1080p with default cfg 5.0 (~32–35 s at `--guidance-scale 1`).
- File location: `ComfyUI/models/diffusion_models/PVCStyleModelMovable_anima10.safetensors`.

### Lighting / atmosphere enhancer (auto)

When an anime request emphasizes **lighting / 光影 / 打光 / glow / volumetric / cinematic lighting /
dramatic lighting / rim light / chiaroscuro / moonlit / reflections**, auto-chain the **Anima Lighting
Atmosphere Enhancer** LoRA from Civitai (`exposure_Lighting-step00000300.safetensors`, model 2628200,
version 3034647) after `@gpt-image-2` at strength **0.5**, and add a short lighting trigger.

Why moderate strength: the author recommends 0–0.9 and notes stronger exposure can lose details or create
unclear vertical lines; local A/B testing showed 0.5 gives a more visible lighting boost while still preserving the subject reasonably well.
If the file is not installed, the script degrades gracefully to prompt-only lighting.

Good prompt phrases: `soft cinematic lighting`, `moonlit water reflections`, `dramatic rim light`,
`subtle volumetric glow`, `starry night`, `blue hour`, `reflected lake light`.

To override manually, use `--loras`, e.g.
`--loras "gpt-image-2_anima-base1_v1-1.safetensors:1.0,exposure_Lighting-step00000300.safetensors:0.25"` or `:0.4`.

### Chaining multiple Anima LoRAs (Kanzarin + Dropkun Artist Blending)

For high-quality sketch-to-CG anime illustration or when artist style blending is desired, we combine the base `@gpt-image-2` style with BOTH **Kanzarin** and **Dropkun** LoRAs at a balanced strength of **0.7** each. For rough sketches / 草稿, default to **`--strength 0.9 --guidance-scale 2`** so Anima fully completes the missing details while still using the sketch as composition guidance.

Since the Python backend keeps its LoRA loading logic generic for flexibility, you MUST explicitly chain these LoRAs using the `--loras` argument, rather than hardcoding them in Python.

Example run command:
```bash
python /home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py \
  "1girl, solo, masterpiece, best quality" \
  --anime \
  --image "/path/to/sketch.png" \
  --loras "gpt-image-2_anima-base1_v1-1.safetensors:1.0,kanzarin_v1_step1500.safetensors:0.7,dolphro-kun_v1_step400.safetensors:0.7" \
  --strength 0.9 \
  --guidance-scale 2
```

Use the **Anima-base1** LoRA variants only; SDXL, Illustrious, and ZImage variants are incompatible with this backend. Note many Civitai "Anima" entries are full checkpoints rather than LoRAs (like PVC above) — those are base swaps, not chain entries.

## Named character requests (search for a reference first)

If the user asks for a specific named character (an anime/game/VTuber/cartoon/celebrity character —
anything you think is a real, identifiable character), **don't rely on the prompt alone**:

> **Treat any unfamiliar proper-noun / name-like input as a POSSIBLE character.** If the prompt
> contains a word or phrase that could be an anime/game/VTuber character name (a name you don't
> recognize, a Japanese/romaji name, "<name> from <series>", etc.) — even if you're not sure it's a
> real character — **search the web first** instead of guessing the look. If the search shows it's a
> real character, follow the steps below; if nothing comes up, treat it as a generic subject.

1. **Search the web for the character's 設定 (official design / character sheet) AND reference images**
   (WebSearch / image search: "<name>", "<name> 設定", "<name> character design", "<name> reference").
   Confirm who they are and gather their canonical look.
   **Then write an EXTREMELY DETAILED appearance description** from what you find — this is the most
   important step, be exhaustive (aim for a dense, specific paragraph, not a few tags):
   - **Hair**: exact color (incl. gradients/streaks/ahoge), length, hairstyle, parting, bangs,
     twin-tails/braids/buns, hair ornaments.
   - **Eyes**: color (incl. heterochromia), shape, pupil style; **face**: skin tone, makeup, markings.
   - **Outfit**: every garment named with its color/material/pattern, layering, sleeves, collar,
     skirt/pants, footwear; **accessories**: headgear, ribbons, jewelry, gloves, belts, weapons/props.
   - **Distinguishing features**: animal ears/tail, wings, horns, tattoos, scars, unique items.
   - **Body type / overall color scheme / vibe.**
   Put this whole description into the prompt — **do not just write the character's name** (the model
   likely doesn't know it). The richer/more specific the description, the closer the result.
2. **Reference images are for YOU to read off the appearance, not to feed the model.** Search
   full-body (全身) refs ("<name> full body / 全身 / character design"), **download a candidate and
   OPEN/READ it** to extract every visual detail into the description above. Verify it's a usable
   single clear depiction (NOT a logo/banner/text/meme/collage/grid/thumbnail/unrelated image); if not,
   try the next candidate (up to ~20). Multiple refs (front/back/different art) help you describe more
   accurately.
3. **Generate from the DETAILED DESCRIPTION (text-to-image), not img2img:**
   - **anime / 二次元 character → `--anime` with the detailed description prompt, and do NOT pass the
     downloaded image as `--image`.** The downloaded reference is only your source for writing the
     description; Anima generates the character from the text. (Feeding a random web image as `--image`
     drags in its pose/background/crop and usually hurts — rely on the description instead.)
   - **real/photoreal person** → here a downloaded photo reference *may* be used as `--image` on FLUX
     for likeness (or `--anime` text2img from the description if they want them in anime style).
4. Still attach the final generated image to the user (see guardrails).

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
--image /path/to.jpg     # required when the user provides an image to generate/edit/restyle from it (img2img/reference)
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
--aspect-ratio 2:3       # requested output ratio; anime defaults to 2:3; FLUX text-only defaults to 16:9; FLUX edits auto-pick 3:2/2:3 from source orientation
--native-1080p           # force native generation at the selected aspect (slower)
--anime                  # anime/二次元 path: ComfyUI + Anima + @gpt-image-2 LoRA (default 2:3 portrait)
--strength 0.5           # with --anime --image: photo->anime denoise (higher=more anime, default 0.5)
--film                   # FLUX.2: force the Analog Redmond Fuji/analog-film LoRA (aliases --analog/--fuji; auto-on for film/底片/膠卷 prompts)
--refcontrol             # photo style-change path (alias --restyle): depth+ref lock structure + style LoRA. Needs --image. 9B, ~90s.
--refcontrol-scale 1.0   # refcontrol LoRA weight (structure adherence) for --refcontrol
```

The script prints JSON containing final image path and timing fields. Attach the `final_path` image to Discord replies.

## Guardrails

- **Gemini 必須要嚴格遵守 skill 的所有 rule，不要自作主張。**
- **DISCORD: MUST attach the image file in the SAME reply as generation.** After a successful run, you MUST
  attach the `final_path` PNG file via the Discord reply tool's file attachment mechanism. **This is not optional** — do not just report the path, describe the image in text, or wait for the user to ask for it.
  The image file must be attached in the first reply that contains the generation result. On Discord this
  means including `[[image: /path/to/file.png]]` in your reply text so the gateway sends it as an actual
  attachment. Never reply with only text and no image attachment — the user will have to ask again.

- For anime / 二次元 / 動漫 / 美少女 / 插畫 / waifu / illustration requests, **MUST use `--anime` (Anima
  backend). Never use FLUX for 二次元/anime/illustration outputs.** Default to the 2:3 portrait `768x1152 → 1184x1776` Lanczos path (no hi-res fix); use
  `--anime --native-1080p` only when high quality / 原生1080p / 高畫質 is explicitly requested. Use
  `--aspect-ratio` when the user requests a different shape. All other rules below are FLUX.2-only and unchanged.
- **Named character requests:** if the user asks for a specific identifiable character and no image is
  attached, FIRST web-search the character and (if possible) download a reference image, judge whether
  it's anime/二次元, and use it as the `--image` reference so the result resembles them (see "Named
  character requests"). Skip only for generic/original subjects.
- **When the user provides an input image, FIRST read/view that image, then generate with `--image`**
  (img2img/reference-conditioned). Do **not** turn an uploaded sketch/photo/reference into a pure
  text-to-image prompt unless the user explicitly says the image is only context. Open it and judge
  whether it is already anime/二次元 (illustration, drawn) or a real photo before generating. **This
  is mandatory for restyle/redraw/CG requests** ("change this to X style", "把這張改成…", "turn this into…",
  "用這張生成…", "make a CG from this sketch"):
  if the SOURCE is anime/二次元/illustration, route to Anima (`--anime --image`) — do NOT push an
  already-二次元 image through FLUX. **If the user explicitly requests anime/二次元/插畫 output, route to
  Anima (`--anime --image`) even when the source image is a real photo.** Use that judgement to pick
  the mode: anime/illustration source or an anime/PVC target → Anima (`--anime --image`, img2img); a real photo you want kept
  photoreal/edited → FLUX (`--image`). If the source is already anime and the user wants a different
  anime style (e.g. PVC), keep `--anime --image` and a lower `--strength` to preserve the original
  character. (See "Restyle requests on an uploaded image" under Image editing.)
- Sketch/草稿→finished anime CG defaults to `--anime --image <sketch> --strength 0.9 --guidance-scale 2`. First inspect the sketch, write a detailed Anima tag+caption prompt that completes subject count, composition, action, hair/eyes/outfits/accessories/props, scene/background, palette, lighting, and source-artifact cleanup constraints.
- Photo→anime (`--anime --image`) uses `--strength` (default 0.5 for ordinary photos; sketch completion uses 0.9). Tune it from user feedback:
  too far from the original → lower it; not anime enough → raise it; keep `--seed` fixed while tuning.
- PVC / figure / 手辦 / フィギュア style requests: keep `--anime` and include "pvc figure" in the prompt;
  the script auto-swaps to the PVC Anima checkpoint + @gpt-image-2. Don't try to load PVC as a LoRA
  (it's a full checkpoint). Only Anima-base LoRAs/checkpoints work on the Anima backend.
- Do NOT enable or keep the FLUX warm daemon resident (it OOMs the box); all requests run in-process.
- Prefer default 9B-KV `1360x768 → 1920x1080` 16:9 mode for normal text-only (non-anime) requests. For FLUX edits with `--image`, omit `--aspect-ratio` unless the user requested a specific shape; the script auto-picks 3:2 for landscape sources and 2:3 for portrait sources at roughly 1080p-equivalent pixels.
- Use `--fast-preview` / 4B only when the user asks for quick preview / 快速預覽 / 草稿.
- Use `--native-1080p` / 9B native only when the user asks for high quality / 高畫質 / native / 原生1080p.
- Keep the ROCm/VAE buckets fixed: FLUX 9B text-only default output `1360x768`, FLUX edit auto buckets `1248x832` (3:2 landscape) / `832x1248` (2:3 portrait), 4B preview uses the same aspect at preview pixel area, reference conditioning is resize-then-cropped to the generation size; Anima default output `768x1152 → 1184x1776`. Prefer the built-in `--aspect-ratio` buckets over arbitrary sizes.
- Do not kill, stop, or restart `llama-server` / `qwen-mtp.service` for image generation.
- Do not enable VAE tiling for 1080p unless debugging; it is stable but very slow.
- If native 1080p OOMs or available memory is too low, report the issue and fall back to default upscale mode instead of stopping other services.
- Always report generation time from the JSON `timings` object when benchmarking.
