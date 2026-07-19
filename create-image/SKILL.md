---
name: create-image
description: Generate new images locally with FLUX.2 or Anima on ROCm 7.2. Use for /create-image and text-to-image requests, including photoreal, anime, illustration, and PVC figures. For editing, restyling, or converting an uploaded photo—especially Fuji/film looks—use photo-editing instead.
---

# Create Image

Generate **new** images only. Image-to-image, retouching, restyling, and uploaded-photo requests belong to `photo-editing`.

## Mandatory research

Before every request, web-search unfamiliar or meaningful names, characters, locations, franchises, products, memes, and styles. For named characters, verify their design and turn the reference into a detailed visual description; do not assume the model knows the name.

## Run

Use the deployed script only—do not write a Diffusers/SD script or download models.

```bash
cd /home/chihmin/models-work/flux2
source .venv-rocm72/bin/activate
FLUX2_BIG_WMMA_LINEAR=1 python ~/.hermes/skills/create-image/scripts/create_image.py "YOUR PROMPT"
```

The script prints JSON. Attach its `final_path` in the same Discord reply:

```text
[[image: /absolute/path/to/result.png]]
```

## Choose a generation mode

| Request | Flags |
|---|---|
| Photoreal / general | none — FLUX.2 9B, default 16:9 1080p output |
| Quick draft | `--fast-preview` (4B) |
| Native high-quality | `--native-1080p` (for photo aspect normally also `--aspect-ratio 3:2`) |
| Anime / illustration / waifu | `--anime` — mandatory Anima backend |
| High-quality anime | `--anime --native-1080p` |
| PVC / figure / 手辦 / フィギュア | `--anime`; include `pvc figure` in prompt (the script switches checkpoint) |
| 二次元像素風 / pixel art / sprite / ドット絵 | `--anime`; pixel keyword auto-loads the Elin pixel-sprite LoRA + `pixel art, chibi, white background, simple background` (drops the background words when the prompt asks for a scene) |
| Text-only Fuji / analog film look | film wording in prompt (auto LoRA), or `--film` |

Examples:

```bash
# photoreal
python ~/.hermes/skills/create-image/scripts/create_image.py \
  "editorial portrait of a jazz pianist, warm window light" --aspect-ratio 3:2

# anime
python ~/.hermes/skills/create-image/scripts/create_image.py \
  "masterpiece, best quality, score_7, safe, 1girl, reading at a cafe window, muted colors, detailed anime background" --anime

# text-to-image analog film
python ~/.hermes/skills/create-image/scripts/create_image.py \
  "a Tokyo street in summer, Fujifilm analog film look, warm grain" --aspect-ratio 3:2
```

## Prompting

### FLUX.2 photoreal
State subject, scene, composition, lighting, palette, and intended photographic treatment. Use `--aspect-ratio 3:2` for a conventional still-photo framing; use 16:9 only for an explicit widescreen request.

### Anima
Use `--anime` for every anime/illustration output. Start with `masterpiece, best quality, score_7, safe`, then specify count, appearance, action, composition, setting, palette, and lighting. Do not ask it to render long exact text. For a named character, include a detailed researched appearance—not only their name.

Anima defaults to 2:3, `768x1152 → 1184x1776`; use `--aspect-ratio` only when a different shape is requested. `--guidance-scale 1` is faster when strong adherence is not needed. Lighting words can auto-load the lighting LoRA; avoid those terms for deliberately flat lighting.

## Constraints

- Do not enable `create-image-daemon.service`; keeping FLUX resident risks OOM.
- Do not start ComfyUI manually. The Anima path starts and cleans up its worker automatically.
- Do not stop or restart Qwen/Gemma MTP services for generation.
- `--fast-preview` is only for explicitly requested drafts; `--native-1080p` is only for explicitly requested high quality.
- Always attach the generated PNG in the first result reply.
