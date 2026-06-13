---
name: mock-voice
description: Clone a voice from YouTube audio and synthesize custom dialogue using CosyVoice 3 (Fun-CosyVoice3-0.5B). Use when the user provides a YouTube URL and wants to generate speech in that voice — anime character impersonations, VTuber-style lines, voice-over demos, multilingual (zh/en/ja/yue/ko) output.
version: 2.0.0
author: Hermes Agent
license: MIT
prerequisites:
  commands: [yt-dlp, ffmpeg]
  paths: [~/src/CosyVoice]
metadata:
  hermes:
    tags: [voice, TTS, cloning, YouTube, CosyVoice, CosyVoice3, anime, cosplay, multilingual]
---

# Mock Voice — YouTube Voice Cloning + CosyVoice 3 TTS

Download audio from a YouTube link, extract a short **clean** voice prompt, then synthesize
custom dialogue using **CosyVoice 3** (FunAudioLLM `Fun-CosyVoice3-0.5B`, GPU-accelerated
zero-shot TTS on ROCm / gfx1151).

## When to use this skill

- "Clone this anime character's voice and make them say X"
- "Use this YouTube video as voice prompt for: [dialogue]"
- "/mock-voice [URL] '台詞'"
- Any request combining a YouTube video + custom speech output (Chinese / English / Japanese / Cantonese / Korean)

## Prerequisites

- `yt-dlp` — YouTube audio extraction (`~/.local/bin/yt-dlp`)
- `ffmpeg` — audio trim / format conversion
- CosyVoice at `~/src/CosyVoice` with GPU torch (`torch 2.11.0+rocm7.2`) and the
  `Fun-CosyVoice3-0.5B` model under `pretrained_models/` (see `~/SOUND.md`).
- Generic runner `run_cosyvoice.py` (uses `AutoModel`, saves via soundfile).
- **For best quality:** `demucs` vocal isolation in `~/src/CosyVoice/.venv-demucs` (see Step 2b).

## Quality matters: clean the prompt first

**The single biggest quality lever is a clean reference clip.** YouTube clips usually have
background music / SFX, which makes the clone muddy. Always:
1. pick a 5–15s window of clear single-speaker speech (skip intro/music), and
2. isolate vocals with demucs to strip BGM (Step 2b).

## Two synthesis modes

| Mode | Use for | Needs prompt transcription? |
|---|---|---|
| `zero_shot` (default) | same-language clone where you know what the prompt says | ✅ `--prompt_text` |
| `cross_lingual` | different language, OR unknown prompt transcription | ❌ |

For anime/YouTube clones with unknown prompt words, **`cross_lingual` is easier** (no
transcription). Japanese output **must be written in katakana**.

## Workflow

### Step 1: Download audio from YouTube

```bash
cd ~/src/CosyVoice/asset/mock   # mkdir -p if needed
yt-dlp -f "bestaudio" --extract-audio --audio-format wav \
  --output "ref.%(ext)s" --no-playlist \
  "https://youtube.com/shorts/Ir3C_O7r3IA" 2>&1 | tail -5
```

Reference voice source used to build this skill: `https://youtube.com/shorts/Ir3C_O7r3IA`

### Step 2a: Trim to a clean ~10s clip

Pick a window of clear speech (adjust `-ss` start):
```bash
cd ~/src/CosyVoice/asset/mock
ffmpeg -y -i ref.wav -ss 2 -t 10 ref_trim.wav
```

### Step 2b: Isolate vocals (remove BGM) — recommended

```bash
cd ~/src/CosyVoice/asset/mock
.venv-demucs/bin/demucs --two-stems vocals -o demucs_out ref_trim.wav   # run from ~/src/CosyVoice
# demucs writes demucs_out/htdemucs/ref_trim/vocals.wav
ffmpeg -y -i demucs_out/htdemucs/ref_trim/vocals.wav -ar 16000 -ac 1 -c:a pcm_s16le ref_16k.wav
```

If demucs is unavailable, fall back to ffmpeg denoise (weaker against music):
```bash
ffmpeg -y -i ref_trim.wav -af "highpass=f=80,lowpass=f=8000,afftdn=nr=20" \
  -ar 16000 -ac 1 -c:a pcm_s16le ref_16k.wav
```

Either way the final prompt must be **16kHz mono**.

### Step 3: Synthesize with CosyVoice 3

**cross_lingual (recommended for anime / unknown-transcript / Japanese):**
```bash
cd ~/src/CosyVoice
PYTHONUTF8=1 .venv/bin/python run_cosyvoice.py \
  --mode cross_lingual \
  --text "コンニチワ、キョウ ワ イイ テンキ デス ネ。" \
  --prompt_wav asset/mock/ref_16k.wav \
  --out results/mock.wav
```

**zero_shot (when you know the prompt's transcription):**
```bash
cd ~/src/CosyVoice
PYTHONUTF8=1 .venv/bin/python run_cosyvoice.py \
  --text "要合成的內容" \
  --prompt_text "參考音實際說的逐字稿" \
  --prompt_wav asset/mock/ref_16k.wav \
  --out results/mock.wav
```

Notes:
- `PYTHONUTF8=1` **must** be set, or CJK text garbles.
- The runner auto-prepends the CV3 system prompt `You are a helpful assistant.<|endofprompt|>`.
  Override with `--sys_prompt`, e.g. Cantonese: `--sys_prompt "请用广东话表达。"`.
- Language tags for cross_lingual text: `<|zh|>` `<|en|>` `<|ja|>` `<|yue|>` `<|ko|>` at the
  start of `--text`. **Japanese must be katakana** (kanji input → wrong readings).
- Default model is `Fun-CosyVoice3-0.5B`; pass `--model_dir pretrained_models/CosyVoice2-0.5B`
  for CosyVoice 2.

### Step 4: Output

```bash
cp ~/src/CosyVoice/results/mock.wav /tmp/mock_voice.wav
```

## Parameter Reference (`run_cosyvoice.py`)

| Parameter | Required | Description |
|---|---|---|
| `--text` | ✅ | Text to synthesize (zh/en/ja-katakana/yue/ko; use `<|lang|>` tags in cross_lingual) |
| `--prompt_wav` | ✅ | Reference voice WAV (16kHz mono, ~5–15s of CLEAN single-speaker speech) |
| `--mode` | — | `zero_shot` (default) or `cross_lingual` |
| `--prompt_text` | zero_shot only | What the reference audio says |
| `--out` | — | Output WAV path (default `results/out.wav`) |
| `--model_dir` | — | Default `pretrained_models/Fun-CosyVoice3-0.5B`; or CosyVoice2-0.5B |
| `--sys_prompt` | — | CV3 system prompt (default `You are a helpful assistant.`) |
| `--stream` | — | Chunked streaming inference |

## Example: Full Pipeline (used to build this skill)

```bash
# 1. Download
cd ~/src/CosyVoice/asset/mock
yt-dlp -f "bestaudio" --extract-audio --audio-format wav \
  --output "ref.%(ext)s" --no-playlist "https://youtube.com/shorts/Ir3C_O7r3IA"

# 2. Trim + isolate vocals + to 16kHz mono
ffmpeg -y -i ref.wav -ss 2 -t 10 ref_trim.wav
cd ~/src/CosyVoice
.venv-demucs/bin/demucs --two-stems vocals -o asset/mock/demucs_out asset/mock/ref_trim.wav
ffmpeg -y -i asset/mock/demucs_out/htdemucs/ref_trim/vocals.wav -ar 16000 -ac 1 \
  -c:a pcm_s16le asset/mock/ref_16k.wav

# 3. Synthesize (cross_lingual, Japanese katakana)
PYTHONUTF8=1 .venv/bin/python run_cosyvoice.py --mode cross_lingual \
  --text "コンニチワ、ワタシ ノ コエ ヲ クローン デキマシタ カ？テスト セイコウ デス ネ。" \
  --prompt_wav asset/mock/ref_16k.wav --out results/mock.wav
```

## Performance (Strix Halo gfx1151, ROCm 7.2)

- CV3 synth: **RTF ~2.4** (~15–21s compute per ~5–9s audio), plus ~tens of seconds to load the
  9G model per process start.
- demucs on a ~10s clip: a few seconds (CPU). onnxruntime runs on CPU (harmless
  `CUDAExecutionProvider not available` warning).

## Common Pitfalls

- **Muddy / wrong-sounding clone**: prompt had BGM or was too long/noisy. Isolate vocals
  (demucs) and trim to a clean 5–15s window.
- **ONNX RuntimeError / broadcast / axis error**: prompt too long → trim.
- **Garbled text**: missing `PYTHONUTF8=1`.
- **Wrong Japanese reading**: passed kanji → convert to **katakana**.
- **Chinese came out instead of target language**: in cross_lingual prepend `<|ja|>` / `<|en|>`
  … and/or use a prompt clip in the target language.
- **`MIOpen(HIP): Warning [IsEnoughWorkspace] ... GemmFwdRest`**: harmless AMD warnings, ignore.
- **yt-dlp "No supported JavaScript runtime"**: non-fatal; falls back. Install `deno` to silence.

## Troubleshooting

### Switching back to CosyVoice 2
`--model_dir pretrained_models/CosyVoice2-0.5B`. CV2 zero_shot `--prompt_text` does **not** need
the `<|endofprompt|>` prefix (the runner only adds it for CV3).

### Don't know the prompt transcription
Use `--mode cross_lingual` (needs none), or transcribe by ear for zero_shot.
