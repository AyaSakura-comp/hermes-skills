---
name: mock-voice
description: Clone a voice from YouTube audio and synthesize custom dialogue using OmniVoice (k2-fsa, diffusion-LM TTS). Use when the user provides a YouTube URL and wants to generate speech in that voice — anime character impersonations, VTuber-style lines, voice-over demos, multilingual (600+ languages) output.
version: 3.0.0
author: Hermes Agent
license: MIT
prerequisites:
  commands: [yt-dlp, ffmpeg]
  paths: [~/src/OmniVoice]
metadata:
  hermes:
    tags: [voice, TTS, cloning, YouTube, OmniVoice, diffusion, anime, cosplay, multilingual]
---

# Mock Voice — YouTube Voice Cloning + OmniVoice TTS

Download audio from a YouTube link, extract a short voice prompt, then synthesize custom
dialogue using **OmniVoice** (k2-fsa diffusion-LM zero-shot TTS, 600+ languages,
GPU-accelerated on ROCm / gfx1151).

## When to use this skill

- "Clone this anime character's voice and make them say X"
- "Use this YouTube video as voice prompt for: [dialogue]"
- "/mock-voice [URL] '台詞'"
- Any request combining a YouTube video + custom speech output (any of 600+ languages)

## Prerequisites

- `yt-dlp` — YouTube audio extraction (`~/.local/bin/yt-dlp`)
- `ffmpeg` — audio trim / format conversion
- OmniVoice at `~/src/OmniVoice` with GPU torch (`torch 2.11.0+rocm7.2`), installed in
  `.venv` (see `~/SOUND.md`). Model `k2-fsa/OmniVoice` auto-downloads on first run.

## No vocal isolation needed

OmniVoice tolerates background music well — it auto-transcribes the reference with
Whisper-large-v3-turbo and clones via diffusion. **You do NOT need to strip BGM with
demucs/UVR for normal clips.** Just trim to a clean window and go. (Only if the source has
very loud music drowning the voice, see the optional demucs fallback at the bottom.)

## Workflow

### Step 0: Clean old WAV files

Clear all previous WAV outputs before starting — prevents stale references from interfering:
```bash
rm -f ~/src/OmniVoice/asset_mock/*.wav
rm -f ~/src/OmniVoice/results_omni/*.wav
```

### Step 1: Download audio from YouTube

```bash
cd ~/src/OmniVoice/asset_mock   # mkdir -p if needed
yt-dlp -f "bestaudio" --extract-audio --audio-format wav \
  --output "ref.%(ext)s" --no-playlist \
  "https://youtube.com/shorts/Ir3C_O7r3IA" 2>&1 | tail -5
```

Reference voice source used to build this skill: `https://youtube.com/shorts/Ir3C_O7r3IA`

### Step 2: Trim to a clean 3–10s clip (16kHz mono)

OmniVoice wants a 3–10s reference of clear speech. Pick a window without intro/music
(adjust `-ss` start):
```bash
cd ~/src/OmniVoice/asset_mock
ffmpeg -y -i ref.wav -ss 2 -t 8 -ar 16000 -ac 1 -c:a pcm_s16le ref_16k.wav
```

### Step 3: Synthesize with OmniVoice (GPU)

```bash
cd ~/src/OmniVoice
PYTHONUTF8=1 .venv/bin/python -m omnivoice.cli.infer \
  --text "こんにちは、私の声をクローンできましたか？" \
  --language Japanese \
  --ref_audio asset_mock/ref_16k.wav \
  --output results_omni/mock.wav \
  --device cuda
```

Notes:
- `--device cuda` uses the AMD GPU (ROCm torch reports as cuda). Auto-detected if omitted.
- **Japanese takes natural kanji/kana directly** — no katakana conversion needed (unlike
  CosyVoice). Chinese/English/etc. likewise natural text. `--language` accepts a name
  (`Japanese`, `English`, `Chinese`) or code (`ja`, `en`, `zh`).
- `PYTHONUTF8=1` must be set or CJK text garbles.
- **Speed**: each run re-transcribes the ref with Whisper (slow). Pass `--ref_text "what the
  reference says"` to skip Whisper and run much faster.
- Diffusion knobs: `--num_step` (16 fast / 32 quality, default 32), `--guidance_scale`
  (default 2.0), `--speed` (>1 faster, <1 slower).
- Voice design instead of cloning: drop `--ref_audio`, add `--instruct "a calm young female
  voice"` (+ `--language`).

### Step 4: Output

```bash
cp ~/src/OmniVoice/results_omni/mock.wav /tmp/mock_voice.wav
```

## Parameter Reference (`omnivoice.cli.infer`)

| Parameter | Required | Description |
|---|---|---|
| `--text` | ✅ | Text to synthesize (natural script, 600+ languages) |
| `--output` | ✅ | Output WAV path |
| `--ref_audio` | for cloning | Reference voice WAV (3–10s clean speech, 16kHz mono) |
| `--ref_text` | optional | Transcription of the ref — **skips Whisper, much faster** |
| `--language` | recommended | Language name or code (`Japanese`/`ja`, …) |
| `--instruct` | voice design | Style description (use instead of `--ref_audio`) |
| `--device` | — | `cuda` (AMD GPU via ROCm) / auto |
| `--num_step` | — | Diffusion steps (16 fast / 32 quality) |
| `--speed` | — | Speaking rate (>1 faster, <1 slower) |
| `--guidance_scale` | — | CFG scale (default 2.0) |

## Example: Full Pipeline (used to build this skill)

```bash
# 0. Clean old WAVs
rm -f ~/src/OmniVoice/asset_mock/*.wav ~/src/OmniVoice/results_omni/*.wav

# 1. Download
cd ~/src/OmniVoice/asset_mock
yt-dlp -f "bestaudio" --extract-audio --audio-format wav \
  --output "ref.%(ext)s" --no-playlist "https://youtube.com/shorts/Ir3C_O7r3IA"

# 2. Trim to 8s @16kHz mono (no BGM removal needed)
ffmpeg -y -i ref.wav -ss 2 -t 8 -ar 16000 -ac 1 -c:a pcm_s16le ref_16k.wav

# 3. Synthesize (Japanese, natural kanji)
cd ~/src/OmniVoice
PYTHONUTF8=1 .venv/bin/python -m omnivoice.cli.infer \
  --text "こんにちは、私の声をクローンできましたか？テスト成功ですね。" \
  --language Japanese --ref_audio asset_mock/ref_16k.wav \
  --output results_omni/mock.wav --device cuda
```

## Performance (Strix Halo gfx1151, ROCm 7.2)

- GPU is used automatically (`--device cuda`); GPU runs ~100% during diffusion.
- Warm run ~28s wall for ~3.5s audio — **dominated by model load + Whisper ASR of the ref**,
  not the diffusion itself. Use `--ref_text` to skip Whisper and cut most of that time.

## Common Pitfalls

- **Garbled text**: missing `PYTHONUTF8=1`.
- **Slow every run**: Whisper re-transcribing the ref → pass `--ref_text`.
- **`MIOpen(HIP): Warning [IsEnoughWorkspace]` / "Flash/Mem Efficient attention experimental"**:
  harmless AMD ROCm warnings, ignore. (Optional: `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1`.)
- **yt-dlp "No supported JavaScript runtime"**: non-fatal; falls back. Install `deno` to silence.
- **Wrong language/accent**: set `--language` explicitly to the target language.

## Optional: demucs vocal isolation (only for very noisy sources)

Normally unnecessary. If the clip has loud music drowning the voice, isolate vocals first
using the separate demucs venv (CPU), then feed the result as `--ref_audio`:
```bash
cd ~/src/CosyVoice   # demucs lives here: .venv-demucs (CPU torch 2.3.1 + soundfile)
.venv-demucs/bin/demucs --two-stems vocals -o /tmp/demucs_out /path/to/ref_trim.wav
ffmpeg -y -i /tmp/demucs_out/htdemucs/ref_trim/vocals.wav -ar 16000 -ac 1 \
  -c:a pcm_s16le ~/src/OmniVoice/asset_mock/ref_16k.wav
```
