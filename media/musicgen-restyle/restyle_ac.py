#!/usr/bin/env python3
"""
restyle_ac.py — Restyle a song using AudioCraft MusicGen-Style + stem separation.

Pipeline:
  1. Separate vocals + instrumental from the input song (audio-separator)
  2. Pass the instrumental to MusicGen-Style as style reference, with target style description
  3. Generate new instrumental in the target style
  4. Mix original vocals over the generated instrumental

Usage:
  python restyle_ac.py \
    --input ./song.mp3 \
    --style "lofi jazz: mellow Rhodes piano over relaxed hip-hop drums, warm and contemplative mood. No heavy bass, no synth leads." \
    --output ./restyled.mp3 \
    [--duration 15] [--strength 0.6] [--cfg 3.0] [--topk 250]

Options:
  --input    Input audio file or URL (required)
  --style    Target style description in English (required)
  --output   Output path (default: ./restyled_ac.mp3)
  --duration Duration in seconds (default: 15, max 30)
  --strength Style transfer strength (not directly used in MusicGen, kept for API consistency)
  --cfg      CFG coefficient (default: 3.0)
  --topk     Top-k sampling (default: 250)
  --temp     Temperature (default: 1.0)
  --excerpt  Style reference excerpt length in seconds (default: 3.0, max 4.5)
  --voc_gain Vocal gain in final mix (default: 1.0)
  --music_gain Music gain in final mix (default: 1.5)
  --loudness Target LUFS (default: -13)
  --sep_dir  Audio-separator directory (default: ~/src/audio-separator)
  --ace_dir  ACE-Step directory for separation (default: ~/src/ACE-Step-1.5)
"""

import argparse
import logging
import os
import subprocess as sp
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import torch
import torchaudio

logger = logging.getLogger("restyle_ac")


def setup_env():
    """Set up ROCm environment for this box (gfx1151, ROCm 7.2)."""
    os.environ["PYTORCH_HIP_ALLOC_CONF"] = "expandable_segments:True"
    os.environ["MIOPEN_FIND_MODE"] = "FAST"
    os.environ["PYTORCH_ROCM_ARCH"] = "gfx1151"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"


def download_or_load_audio(input_path, tmpdir):
    """Download audio from URL if needed, otherwise use local file."""
    if input_path.startswith(("http://", "https://")):
        logger.info(f"Downloading audio from URL: {input_path}")
        cmd = [
            "yt-dlp", "-f", "bestaudio", "-x", "--audio-format", "wav",
            "--no-playlist", "-o", os.path.join(tmpdir, "input.%(ext)s"),
            input_path
        ]
        sp.run(cmd, check=True, capture_output=True)
        input_path = Path(tmpdir) / "input.wav"
        assert input_path.exists(), f"yt-dlp failed for {input_path}"

    # Normalize to 48kHz stereo wav
    out_path = Path(tmpdir) / "src_48k.wav"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", input_path,
        "-ac", "2", "-ar", "48000",
        str(out_path)
    ]
    sp.run(cmd, check=True, capture_output=True)
    return str(out_path)


def separate_stems(input_wav, out_dir, sep_dir):
    """
    Separate vocals + instrumental using audio-separator (UVR-MDX-NET).
    Returns paths to vocals and instrumental stems.
    """
    sep_bin = os.path.join(sep_dir, ".venv", "bin", "audio-separator")
    model_dir = os.path.join(sep_dir, "models")
    model_file = "UVR-MDX-NET-Inst_HQ_4.onnx"

    logger.info(f"Separating stems with audio-separator (model={model_file})...")
    cmd = [
        sep_bin, input_wav,
        "--model_filename", model_file,
        "--model_file_dir", model_dir,
        "--output_dir", out_dir,
        "--output_format", "WAV",
        "--mdx_segment_size", "512",
        "--mdx_overlap", "0.85",
        "--log_level", "INFO"
    ]
    result = sp.run(cmd, capture_output=True, text=True)
    # Filter noisy output
    for line in result.stderr.split("\n"):
        if not any(k in line for k in ["MIOpen", "IsEnoughWorkspace", "UserWarning", "warnings.warn", "iB/s", "it/s"]):
            logger.debug(line)

    # Find stems
    vocals = None
    instrumental = None
    for f in Path(out_dir).iterdir():
        if "(Vocals)" in f.name and f.name.endswith(".wav"):
            vocals = str(f)
        elif "(Instrumental)" in f.name and f.name.endswith(".wav"):
            instrumental = str(f)

    assert vocals is not None, f"Vocals stem not found in {out_dir}"
    assert instrumental is not None, f"Instrumental stem not found in {out_dir}"

    logger.info(f"  Vocals:     {vocals}")
    logger.info(f"  Instrumental: {instrumental}")
    return vocals, instrumental


def load_musicgen_model():
    """Load MusicGen-Style model."""
    logger.info("Loading MusicGen-Style model...")
    from audiocraft.models import MusicGen
    from audiocraft.data.audio_utils import convert_audio

    model = MusicGen.get_pretrained("facebook/musicgen-style")
    # MusicGen is already in eval mode by default, no .eval() needed
    logger.info(f"  Model: {model.name}")
    logger.info(f"  Sample rate: {model.sample_rate}")
    logger.info(f"  Frame rate: {model.frame_rate}")
    logger.info(f"  Max duration: {model.max_duration}s")

    return model, convert_audio


def generate_instrumental(model, convert_audio, instrumental_wav, target_style, duration,
                          cfg_coef=3.0, topk=250, temp=1.0, excerpt_length=3.0):
    """
    Generate new instrumental in the target style using MusicGen-Style.

    Args:
        model: MusicGen model (style)
        convert_audio: audio conversion function
        instrumental_wav: path to original instrumental (style reference)
        target_style: text description of target style
        duration: duration in seconds (max 30)
        cfg_coef: CFG coefficient
        topk: top-k sampling
        temp: temperature
        excerpt_length: length of excerpt to use as style reference (max 4.5s)
    """
    logger.info(f"Generating new instrumental ({duration}s, style='{target_style[:50]}...')")

    # Set generation params
    model.set_generation_params(
        duration=duration,
        top_k=topk,
        top_p=0.0,
        temperature=temp,
        cfg_coef=cfg_coef,
        cfg_coef_beta=5.0 if cfg_coef > 0 else None  # double CFG for style + text
    )
    model.set_style_conditioner_params(eval_q=3, excerpt_length=excerpt_length)

    # Load the instrumental (style reference) and convert to model's format
    sr, instrumental = torchaudio.load(instrumental_wav)
    sr = int(sr)
    instrumental = instrumental.float()
    if instrumental.dim() == 1:
        instrumental = instrumental.unsqueeze(0)

    # Convert to model's sample rate (32kHz) and mono
    instrumental = convert_audio(instrumental, sr, model.sample_rate, 1)

    # Generate
    logger.info("  Running generation...")
    wav = model.generate_with_chroma(
        descriptions=[target_style],
        melody_wavs=[instrumental],
        melody_sample_rate=model.sample_rate,
        progress=True,
        return_tokens=False
    )

    # wav shape: [1, 1, samples]
    wav = wav[0].cpu().float()
    logger.info(f"  Output shape: {wav.shape} ({wav.shape[-1] / model.sample_rate:.1f}s)")
    return wav


def mix_final(vocals_wav, generated_wav, sample_rate, vocal_gain=1.0, music_gain=1.5, loudness=-13):
    """
    Mix original vocals over generated instrumental.

    Uses ffmpeg for mixing and loudness normalization.
    """
    logger.info(f"Mixing vocals (gain={vocal_gain}) over generated music (gain={music_gain})")

    # Save intermediates for ffmpeg
    vocals_out = Path(vocals_wav)
    music_out = Path(tempfile.mktemp(suffix="_gen_music.wav"))
    final_out = Path(tempfile.mktemp(suffix="_final.wav"))

    # Save generated music to wav
    torchaudio.save(str(music_out), generated_wav, sample_rate)

    # Mix with ffmpeg
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(vocals_out),
        "-i", str(music_out),
        "-filter_complex",
        f"[0]aresample=48000,volume={vocal_gain}[v];"
        f"[1]aresample=48000,volume={music_gain}[m];"
        f"[v][m]amix=inputs=2:duration=longest:normalize=0[mix];"
        f"[mix]loudnorm=I={loudness}:TP=-1.0:LRA=11,alimiter=limit=0.891:level=disabled[a]",
        "-map", "[a]", "-ac", "2", "-ar", "48000",
        str(final_out)
    ]
    sp.run(cmd, check=True, capture_output=True)

    logger.info(f"  Final mix: {final_out}")
    return str(final_out)


def main():
    parser = argparse.ArgumentParser(description="Restyle a song using AudioCraft + stem separation")
    parser.add_argument("--input", "-i", required=True, help="Input audio file or URL")
    parser.add_argument("--style", "-s", required=True, help="Target style description (in English)")
    parser.add_argument("--output", "-o", default="./restyled_ac.mp3", help="Output path")
    parser.add_argument("--duration", type=int, default=15, help="Duration in seconds (max 30)")
    parser.add_argument("--strength", type=float, default=0.6, help="Style transfer strength")
    parser.add_argument("--cfg", type=float, default=3.0, help="CFG coefficient")
    parser.add_argument("--topk", type=int, default=250, help="Top-k sampling")
    parser.add_argument("--temp", type=float, default=1.0, help="Temperature")
    parser.add_argument("--excerpt", type=float, default=3.0, help="Style reference excerpt length (max 4.5)")
    parser.add_argument("--voc_gain", type=float, default=1.0, help="Vocal gain in final mix")
    parser.add_argument("--music_gain", type=float, default=1.5, help="Music gain in final mix")
    parser.add_argument("--loudness", type=float, default=-13, help="Target LUFS")
    parser.add_argument("--sep_dir", default=os.path.expanduser("~/src/audio-separator"))
    parser.add_argument("--ace_dir", default=os.path.expanduser("~/src/ACE-Step-1.5"))
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[restyle_ac] %(levelname)s: %(message)s"
    )

    setup_env()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Step 0: Download/normalize input
        logger.info("=" * 60)
        logger.info("Step 0: Loading input audio")
        src_wav = download_or_load_audio(args.input, tmpdir)

        # Step 1: Separate vocals + instrumental
        logger.info("=" * 60)
        logger.info("Step 1: Separating vocals + instrumental")
        stems_dir = os.path.join(tmpdir, "stems")
        os.makedirs(stems_dir, exist_ok=True)
        vocals_wav, instrumental_wav = separate_stems(src_wav, stems_dir, args.sep_dir)

        # Step 2: Generate new instrumental with MusicGen-Style
        logger.info("=" * 60)
        logger.info("Step 2: Generating new instrumental with MusicGen-Style")
        assert args.duration <= 30, "Duration must be <= 30 seconds"
        assert args.excerpt <= 4.5, "Excerpt length must be <= 4.5 seconds"

        model, convert_audio_fn = load_musicgen_model()
        generated_wav = generate_instrumental(
            model, convert_audio_fn,
            instrumental_wav, args.style,
            duration=args.duration,
            cfg_coef=args.cfg,
            topk=args.topk,
            temp=args.temp,
            excerpt_length=args.excerpt
        )

        # Step 3: Mix original vocals over generated instrumental
        logger.info("=" * 60)
        logger.info("Step 3: Mixing vocals over new instrumental")
        final_wav = mix_final(
            vocals_wav, generated_wav,
            sample_rate=48000,
            vocal_gain=args.voc_gain,
            music_gain=args.music_gain,
            loudness=args.loudness
        )

        # Step 4: Encode to output format
        logger.info("=" * 60)
        logger.info("Step 4: Encoding output")
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if args.output.endswith((".wav", ".flac")):
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", final_wav, str(out_path)]
        else:
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error", "-i", final_wav,
                "-b:a", "256k", str(out_path)
            ]
        sp.run(cmd, check=True, capture_output=True)

        logger.info(f"[restyle_ac] done -> {out_path}")
        print(f"[restyle_ac] done -> {out_path}")


if __name__ == "__main__":
    main()
