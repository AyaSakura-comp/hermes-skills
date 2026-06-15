---
name: restyle-music
description: Change the style/genre of an existing song while keeping its original melody and structure, using ACE-Step 1.5 "cover" mode on the local ROCm GPU. Use when the user provides an audio file and asks to convert/restyle/re-arrange it into another genre or instrumentation (e.g. "make this song traditional Japanese", "turn this into lofi jazz", "orchestral version of this track").
version: 1.0.0
author: Hermes Agent
license: MIT
prerequisites:
  commands: [ffmpeg, yt-dlp, ollama]
  paths: [~/src/ACE-Step-1.5, ~/src/audio-separator]
metadata:
  hermes:
    tags: [music, cover, restyle, genre, style-transfer, ace-step, audio, gpu, rocm]
    related_skills: [create-music, mock-voice]
---

# Restyle Music — change a song's style, keep its melody (ACE-Step 1.5 cover, GPU)

Take an **existing audio file** + a **target style description** and re-render the song in that
style while preserving the original melody/structure, via ACE-Step 1.5's `cover` task on the
local AMD GPU (ROCm, gfx1151). Deployed at `~/src/ACE-Step-1.5`.

## When to use

- "Change this song into <genre>" / "make this traditional Japanese / lofi / orchestral / metal"
- "Re-arrange / cover this track in another style", "swap the instrumentation"
- User gives an input audio file and a vibe; wants a restyled audio file out.

This is **cover** (melody-preserving style transfer), not text-to-music from scratch — for
generating a brand-new song from lyrics+tags use the `create-music` skill instead.

## Keep the ORIGINAL singing voice (`-k`)

Cover mode **re-synthesizes the whole song, vocals included** — so on its own it cannot keep the
real original voice (it renders a new singer over the kept melody). To genuinely preserve the
original voice, pass `-k`: the skill splits the song into **vocals + instrumental** with
`audio-separator` (UVR-MDX-NET, on the GPU), restyles **only the instrumental**, then mixes the
**original vocal stem** back on top. Result = your original singer over a new-genre backing.

```bash
~/.claude/skills/restyle-music/restyle_music.sh \
  -i ./song.mp3 -k \
  -s "lofi jazz, mellow Rhodes piano, brushed drums, upright bass, instrumental" \
  -V 1.0 -o ./lofi_keepvocals.mp3
```

- `-k` skips lyrics automatically (so the restyled backing stays instrumental).
- `-V GAIN` balances the kept voice against the new backing (default `1.0`; `1.2`–`1.4` if the
  vocal sits too low, `0.8` if it's too hot). Describe an **instrumental** style in `-s`.
- Needs `~/src/audio-separator` (already deployed; set `AUDIO_SEPARATOR_DIR` to override).
- Caveat: separation isn't perfect — faint bleed/reverb tails of the old backing can remain in
  the vocal stem. For a totally fresh (new) voice instead, run the normal mode without `-k`.

## Make the VOCAL match the new style (`-A`, auto-lyrics)

`-k` keeps the original voice unchanged, so the singing doesn't adopt the new genre. If instead
you want the **vocal re-sung in the target style while keeping the original words**, use `-A`:
the skill transcribes the source song's lyrics with **Ollama `gemma4:e2b`** (audio-capable),
feeds those lyrics to ACE-Step, and runs a **normal cover** (it auto-drops `-k`). The melody/
structure still follow the source (`-S`); the words come from the transcription; the timbre and
delivery adopt the new genre. Trade-off: it's a **new singer's voice**, not your original one.

```bash
~/.claude/skills/restyle-music/restyle_music.sh \
  -i "https://youtu.be/XXXX" -A \
  -s "energetic Japanese rock band, distorted guitars, driving drums" \
  -S 0.4 -g ja -o jrock.mp3
```

- `-A` auto-drops `-k` (can't both keep and re-sing the voice). Needs Ollama running with
  `gemma4:e2b` pulled (`ollama pull gemma4:e2b`). It transcribes a 16kHz mono downmix internally.
- Pair with `-g` for the vocal language and a lower `-S` (0.35–0.45) so the vocal moves further
  toward the new style. The transcribed lyrics are printed so you can sanity-check them.
- Prefer your own clean lyrics? Skip `-A` and pass `-l`/`-L` directly (same effect, no ASR step).

## Quick start (one-shot wrapper)

```bash
~/.claude/skills/restyle-music/restyle_music.sh \
  -i ./input_song.mp3 \
  -s "traditional Japanese wagaku: shamisen, koto, shakuhachi, taiko, no electric instruments" \
  -o ./restyled.mp3
```

With more control (looser style transfer + keep the vocal by supplying lyrics):
```bash
~/.claude/skills/restyle-music/restyle_music.sh \
  -i song.wav -s "lofi jazz, mellow Rhodes piano, brushed drums, upright bass" \
  -S 0.45 -l ./lyrics.txt -o lofi.mp3
```

### From YouTube / a URL

`-i` also accepts a **URL** (YouTube, etc.) — the wrapper runs `yt-dlp` to download the audio
first, then proceeds exactly as for a local file. No need to download by hand.

```bash
~/.claude/skills/restyle-music/restyle_music.sh \
  -i "https://youtu.be/XXXXXXXXXXX" -k \
  -s "traditional Japanese wagaku: shamisen, koto, taiko, instrumental" \
  -S 0.5 -o ./wagaku.mp3
```

(Equivalent manual step if you'd rather: `yt-dlp -x --audio-format wav -o song.wav "<url>"`,
then pass `-i song.wav`.)

Options:
- `-i FILE|URL` — **input audio**: a local file (any ffmpeg-readable: mp3/wav/flac/m4a…) **or** a
  YouTube/other URL (auto-downloaded via `yt-dlp`). Required.
- `-s TEXT` — **target style** description (instruments, genre, mood, tempo). Required. Be
  specific and say what to *remove* too (e.g. "no electric guitar, no synth").
- `-o OUT`  — output path. `.mp3` re-encoded (default `256k`); `.wav`/`.flac` = lossless. Default `./restyled.mp3`.
- `-S NUM`  — `audio_cover_strength` 0.0–1.0 (default **0.6**). **Lower = freer / more style change**
  (0.3–0.5 for a strong genre swap); **higher = stays closer to the original** (0.7–0.9 for a light
  re-skin). This is the main knob to tune.
- `-l FILE` / `-L "inline"` — lyrics (file or inline, `\n` = line break). Optional; supplying the
  song's lyrics helps keep clean vocals on vocal tracks. Omit for instrumental-ish sources.
- `-g LANG` — vocal language hint (`en`,`zh`,`ja`,…; default `auto`→en).
- `-q N`    — diffusion steps (default 8, turbo). More = slightly cleaner, slower.
- `-m NAME` — LM checkpoint (default `acestep-5Hz-lm-0.6B`; cover skips the LM so this rarely matters).
- `-b RATE` — mp3 bitrate (default `256k`).
- `-k`      — **keep the original singing voice** (separate → restyle instrumental → remix vocal). See above.
- `-V GAIN` — vocal gain for `-k` remix (default `1.0`).
- `-A`      — **auto-lyrics**: transcribe the source's lyrics via Ollama `gemma4:e2b` and re-sing
  them in the new style (drops `-k`). See above. Pair with `-g` and a lower `-S`.

The wrapper normalizes the input to 48kHz stereo wav, runs the cover on GPU, and encodes the result.
It prints `[restyle] done -> <path>`.

## Tuning — "I want to change X" → use this option

Every adjustment a user is likely to ask for maps to a specific option. Pick the matching row;
the wrapper is fast (cover skips LM planning), so iterating on `-S` / the `-s` caption is cheap.

| If the user wants to… | Use | How |
|---|---|---|
| **Change the genre/instrumentation** | `-s "…"` | The core control. Name instruments, genre, mood, tempo. Be specific. |
| **Remove a specific instrument** (e.g. drop the guitar/synth) | `-s "…"` | Say it explicitly: `"…, no electric guitar, no synth, no drums"`. |
| **More style change / "it still sounds like the original"** | `-S` ↓ | Lower it: `-S 0.4` (or 0.3) for a strong swap. |
| **Less style change / "it drifted too far, keep the original feel"** | `-S` ↑ | Raise it: `-S 0.75`–`0.9` for a light re-skin. |
| **Lost / mangled the original melody** | `-S` ↑ | Raise `-S`; higher = closer to the source structure. |
| **Keep the ORIGINAL singing voice** | `-k` | Splits vocals out, restyles only the backing, remixes the real voice back. Use an instrumental `-s`. |
| **A brand-new singer (don't keep the voice)** | *(omit `-k`)* | Normal cover re-synthesizes the vocal; pass `-l`/`-L` lyrics for clean diction. |
| **The VOCAL to match the new genre, keeping the words** | `-A` | Auto-transcribes the lyrics (Ollama `gemma4:e2b`) and re-sings them in the new style; drops `-k`. Pair with `-g` + lower `-S`. |
| **Kept vocal too quiet** (with `-k`) | `-V` ↑ | `-V 1.2`–`1.4`. |
| **Kept vocal too loud / drowns the backing** (with `-k`) | `-V` ↓ | `-V 0.8`–`0.9`. |
| **Garbled / mushy vocals** (without `-k`) | `-l` / `-L` | Supply the real lyrics (file or inline), or describe an instrumental style in `-s`. |
| **Wrong vocal language / accent** | `-g` | `-g ja` / `-g zh` / `-g en` … (default `auto`→en). |
| **Higher audio quality / cleaner result** | `-q` ↑ | More diffusion steps, e.g. `-q 16` (slower). |
| **Faster generation** | `-q` ↓ or `ACESTEP_ROCM_DTYPE=bfloat16` | Fewer steps, or `export ACESTEP_ROCM_DTYPE=bfloat16` (~2× diffusion). |
| **Lossless output** | `-o name.wav` / `.flac` | Any non-mp3 extension = lossless copy (may exceed Discord's 25MB). |
| **Different mp3 quality / file size** | `-b` | e.g. `-b 320k` (higher) or `-b 192k` (smaller). |
| **Use a different ACE-Step repo / models dir** | `ACE_ROOT=…` | Export before the call; `AUDIO_SEPARATOR_DIR=…` for the `-k` separator. |
| **Pin a specific GPU** | `HIP_VISIBLE_DEVICES=N` | Export before the call (default `0`). |
| **Out-of-memory during VAE decode** | `ACESTEP_ROCM_DTYPE=bfloat16` | Halves activation memory; alloc already uses `expandable_segments`. |

Anything not in this table (the LM checkpoint via `-m`, etc.) rarely affects cover output — `-S`
and the `-s` caption do almost all the work.

## Manual run (equivalent)

```bash
cd ~/src/ACE-Step-1.5
ffmpeg -y -i input.mp3 -ac 2 -ar 48000 /tmp/src.wav
# Full ROCm/gfx1151 env the wrapper now fills in automatically (ACE_ENV array in restyle_music.sh):
env -u HSA_OVERRIDE_GFX_VERSION \
  HIP_VISIBLE_DEVICES=0 \
  MIOPEN_FIND_MODE=FAST \
  MIOPEN_USER_DB_PATH=~/.claude/skills/restyle-music/.cache/miopen \
  MIOPEN_CUSTOM_CACHE_DIR=~/.claude/skills/restyle-music/.cache/miopen \
  PYTORCH_HIP_ALLOC_CONF=expandable_segments:True \
  TOKENIZERS_PARALLELISM=false \
  ACESTEP_LM_BACKEND=pt \
  ACESTEP_ROCM_DTYPE=float32 \
  ACE_ROOT=$PWD .venv/bin/python ~/.claude/skills/restyle-music/cover_runner.py \
    --src /tmp/src.wav --caption "lofi jazz, mellow piano" --out-dir ./output/restyle \
    --strength 0.6 --steps 8
```

The wrapper sets all of these for you (and for the `-k` separator step too), so a bare
`restyle_music.sh -i … -s …` runs on this box with no extra setup. Override any of them by
exporting it before the call (e.g. `ACESTEP_ROCM_DTYPE=bfloat16` for ~2× faster diffusion).
The pinned `MIOPEN_*` cache means MIOpen only JITs its kernels once; later runs skip the ~JIT.

`cover_runner.py` loads the DiT (turbo) + 0.6B LM (pt backend) and calls
`generate_music(..., task_type="cover", src_audio=..., audio_cover_strength=...)`.

## Performance & hardware (Strix Halo gfx1151, ROCm 7.2)

- Runs on the AMD GPU (AMD Radeon 8060S, 96GB GTT). dtype float32 by default; set
  `ACESTEP_ROCM_DTYPE=bfloat16` for ~2x faster diffusion if needed.
- A ~160s song: model load ~30–60s + **cover generation ~65s** (8 steps; cover skips LM planning,
  so it's faster than text2music's ~141s). Peak VRAM ~21GB.

## Notes / gotchas

- **Never set `HSA_OVERRIDE_GFX_VERSION`** on this box — the repo's stock ROCm launchers default it
  to `11.0.0`, which makes the GPU vanish ("No CUDA GPUs available"). rocm7.2 torch supports gfx1151
  natively; the wrapper already passes `env -u HSA_OVERRIDE_GFX_VERSION`.
- Requires `~/src/ACE-Step-1.5/.venv` with **torch 2.11+rocm7.2** and models in `checkpoints/`
  (DiT `acestep-v15-turbo` + VAE + Qwen3-Embedding + LM `acestep-5Hz-lm-0.6B`). Set `ACE_ROOT` to
  override the repo location.
- Output is 48kHz stereo. A full song's lossless wav can exceed Discord's 25MB limit — send the mp3.
- Harmless startup warnings: torchao CUTLASS `.so` load fail (CUDA-only), LyCORIS/bitsandbytes/
  pytorch_wavelets missing (training/DCW only).
