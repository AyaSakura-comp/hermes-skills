---
name: create-music
description: Generate full songs from lyrics + genre tags using HeartMuLa (heartlib), an open-source Suno-like music model, on the local ROCm GPU. Use when the user wants to create/compose music, make a song, generate an instrumental, or turn lyrics into audio with a chosen style/genre.
version: 1.0.0
author: Hermes Agent
license: MIT
prerequisites:
  commands: [ffmpeg]
  paths: [~/src/heartlib]
metadata:
  hermes:
    tags: [music, song, generation, ai, heartmula, lyrics, genre, suno, audio]
    related_skills: [heartmula, mock-voice]
---

# Create Music — HeartMuLa song generation (lyrics + genre, GPU)

Generate a full song from **lyrics** and **genre/style tags** using HeartMuLa (`heartlib`),
an open-source Suno-like model, on the local AMD GPU (ROCm). Deployed at `~/src/heartlib`.

## When to use

- "Write/generate a song about X" / "make me a lofi track" / "compose a happy piano piece"
- User provides lyrics and/or a genre/mood and wants an audio file out.
- Instrumental (no lyrics) or full vocal songs.

## Quick start (one-shot wrapper)

```bash
~/.claude/skills/create-music/create_music.sh -t "piano,happy,lofi" -l ./my_lyrics.txt -o song.mp3
```

Inline lyrics (no file needed; `\n` = line break):
```bash
~/.claude/skills/create-music/create_music.sh \
  -t "jazz,piano,relaxing" \
  -L "[Verse]\nMidnight city lights are glowing\n[Chorus]\nWe are dreaming, we are flowing" \
  -d 60 -o ./assets/mysong.mp3
```

Options:
- `-t TAGS` — genre/style, **comma-separated** (e.g. `"rock,energetic,guitar"`). Drives the vibe.
- `-l FILE` — lyrics file path (structured, see format below).
- `-L TEXT` — inline lyrics string (overrides `-l`).
- `-o OUT` — output path. `.mp3` is auto-encoded at **320kbps** (generated lossless then ffmpeg);
  `.wav`/`.flac` = lossless. Default `./assets/output.mp3`.
- `-d SEC` — max length in seconds. Default **90** (1:30). Use larger for full songs.
- `-T TEMP` — temperature (default 1.0; higher = more variation).
- `-c CFG` — guidance scale (default 1.5; higher = follow tags/lyrics more strictly).
- `-k TOPK` — top-k sampling (default 50).
- `-Q LEVEL` — **quality preset** (default `high`):
  - `high` — 320kbps mp3 + codec_steps 16 (best fidelity).
  - `low` — 128kbps mp3 + codec_steps 8 (faster, smaller — drafts/quick previews).
- `-q STEPS` — override the preset's HeartCodec decode steps (higher = better fidelity, slower).
- `-C` — compile the MuLa model using TorchDynamo (recommended for long runs, e.g., > 3 minutes).

### Audio quality

- **`-Q high` (default)** = 320kbps mp3; **`-Q low`** = 128kbps mp3 (faster). The wrapper renders
  the model's audio to a lossless wav then ffmpeg-encodes at the preset bitrate (avoids
  soundfile's low default mp3 bitrate and double-lossy).
- For lossless, use `-o name.flac` or `-o name.wav` (bitrate preset is ignored for those).
- `-q` overrides codec decode steps (reconstruction fidelity); `-Q high` already uses 16.
- Codec runs in bfloat16 for a massive 4.25x speedup on ROCm with negligible quality difference.

### Clarity Repair (audio-separator post-processing, `-S`)

Pass `-S` to run the finished song through **audio-separator** (UVR-MDX-NET-Inst_HQ_4) on the
ROCm GPU as a clarity-repair pass. It splits the song into vocals + instrumental stems and sums
the cleaned stems back into one mix — the MDX model only passes through learned musical content,
so the reconstruction drops broadband noise / muddiness it treats as non-music. **Keeps vocals**
(it is not a karaoke/instrumental-only extraction).

```bash
~/.claude/skills/create-music/create_music.sh -t "lofi,chill,jazz" -L "[Verse]\n..." -d 60 -S -o song.mp3
```

- Runs on GPU via the onnx2torch→torch-ROCm path (no onnxruntime EP needed; gfx1151-safe).
- Deployed at `~/src/audio-separator` (uv venv, torch 2.11+rocm7.2). Wrapper:
  `~/src/audio-separator/enhance_clarity.sh -i in.mp3 -o out.mp3` (standalone use on any audio).
- First run JITs MIOpen kernels (~30s extra); the kernel cache persists, then it's ~RTF 1 on GPU
  (a 6s clip ≈ 3s separation). A full 4-min song ≈ ~2 min.
- Caveat: MDX works at **44.1kHz**, so the repaired output is 44.1kHz (HeartMuLa natively outputs
  48kHz). It's a clarity/de-noise pass, not bandwidth extension.

## Lyrics format

Use section headers in square brackets. Lines under each become the sung lyrics. For an
**instrumental**, use only structural tags with empty sections (e.g. just `[Intro]`).

```txt
[Intro]

[Verse]
The sun creeps in across the floor
I hear the traffic outside the door

[Prechorus]
The world keeps spinning round and round

[Chorus]
Every day the light returns
Every day the fire burns

[Bridge]
It is not always easy, not always bright

[Outro]
```

Supported sections: `[Intro] [Verse] [Prechorus] [Chorus] [Bridge] [Outro]` (multilingual lyrics
are supported — HeartMuLa covers most languages).

## Genre / tags ideas

Comma-separated descriptors of instrument, mood, genre, tempo, vocals. Examples:
- `piano, happy, upbeat`
- `lofi, chill, mellow, jazz`
- `rock, energetic, electric guitar, male vocals`
- `orchestral, epic, cinematic`
- `electronic, synth, dance, female vocals`
- `acoustic, folk, soft, warm`

## Manual run (equivalent)

```bash
cd ~/src/heartlib
# edit assets/lyrics.txt and assets/tags.txt, then:
PYTHONUTF8=1 .venv/bin/python ./examples/run_music_generation.py \
  --model_path=./ckpt --version=3B --lazy_load true \
  --tags ./assets/tags.txt --lyrics ./assets/lyrics.txt \
  --max_audio_length_ms 240000 --save_path ./assets/output.mp3
```

Key flags: `--tags`/`--lyrics` (file paths), `--max_audio_length_ms`, `--temperature`,
`--cfg_scale`, `--topk`, `--save_path`. `--lazy_load true` keeps GPU use ~6.2GB.

## Performance & hardware (Strix Halo gfx1151, ROCm 7.2)

- Runs on the AMD GPU. With AOTriton-based memory efficient attention (`TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1` enabled by default), generation runs at **~7.3 iterations/second** (saving ~50% compute time compared to baseline).
- A 15-second song takes **~30 seconds** end-to-end. A 90-second song takes **~172 seconds (2.8 minutes)**.
- Compiling the model via `-C` increases step generation rate to **~7.8 iterations/second**, but adds a ~20-second startup overhead. Only recommended for songs longer than 3 minutes.

## Notes / gotchas

- Must use **torch 2.11+rocm7.2** in `~/src/heartlib/.venv`. The `rocm7.1` torch wheel SIGSEGVs
  in `libhsa-runtime64.so` on this gfx1151 (even a bare GPU matmul) — do not downgrade to it.
- Output saving is patched to use `soundfile` (torch 2.11's `torchaudio.save` needs torchcodec).
- Models live in `~/src/heartlib/ckpt` (HeartMuLaGen + HeartMuLa-oss-3B + HeartCodec-oss, ~21G).
- If the box's qwen `llama-server` (:8001) is also running, there's still ~40GB GTT free — both
  fit, but if you hit a true OOM, lower its context (`-c`) rather than `-np`.
