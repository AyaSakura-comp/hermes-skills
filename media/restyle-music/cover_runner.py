#!/usr/bin/env python3
"""Restyle/cover a source audio file into a new style with ACE-Step 1.5 (GPU/ROCm).

Invoked by restyle_music.sh. Loads DiT (turbo) + 0.6B LM, then runs task_type=cover:
keeps the source melody/structure, swaps the timbre/genre per --caption.
"""
import argparse, os, sys, time

for v in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
    os.environ.pop(v, None)

ACE_ROOT = os.environ.get("ACE_ROOT", os.path.expanduser("~/src/ACE-Step-1.5"))
sys.path.insert(0, ACE_ROOT)

from loguru import logger
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig, generate_music


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="source audio (wav, 48kHz preferred)")
    ap.add_argument("--caption", required=True, help="target style description")
    ap.add_argument("--out-dir", required=True, help="dir to save the rendered wav")
    ap.add_argument("--lyrics", default="", help="optional lyrics (improves vocal songs)")
    ap.add_argument("--strength", type=float, default=0.6,
                    help="audio_cover_strength 0..1 (low=looser/more style, high=closer to source)")
    ap.add_argument("--steps", type=int, default=8, help="diffusion steps (turbo default 8)")
    ap.add_argument("--language", default="auto", help="vocal language hint, or 'auto'")
    ap.add_argument("--lm", default="acestep-5Hz-lm-0.6B", help="LM checkpoint name")
    ap.add_argument("--bpm", type=int, default=0,
                    help="explicit BPM to lock the tempo/beat grid (0 = let ACE auto-estimate)")
    ap.add_argument("--keyscale", default="",
                    help="musical key to lock harmony, e.g. 'F# major' / 'A minor' ('' = auto)")
    ap.add_argument("--seed", type=int, default=-1)
    args = ap.parse_args()

    ckpt = os.path.join(ACE_ROOT, "checkpoints")
    os.makedirs(args.out_dir, exist_ok=True)

    import torch
    logger.info(f"torch {torch.__version__} hip={torch.version.hip} "
                f"gpu={torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'}")
    if not torch.cuda.is_available():
        logger.error("No GPU visible — make sure HSA_OVERRIDE_GFX_VERSION is UNSET on gfx1151.")
        sys.exit(2)

    t0 = time.time()
    dit = AceStepHandler()
    msg, ok = dit.initialize_service(project_root=ACE_ROOT, config_path="acestep-v15-turbo",
                                     device="auto", offload_to_cpu=False)
    assert ok, f"DiT init failed: {msg}"
    logger.info(f"DiT loaded in {time.time()-t0:.1f}s")

    t0 = time.time()
    llm = LLMHandler()
    msg, ok = llm.initialize(checkpoint_dir=ckpt, lm_model_path=args.lm,
                             backend="pt", device="auto", offload_to_cpu=False, dtype=None)
    assert ok, f"LM init failed: {msg}"
    logger.info(f"LM loaded in {time.time()-t0:.1f}s")

    params = GenerationParams(
        task_type="cover",
        src_audio=args.src,
        caption=args.caption,
        lyrics=args.lyrics,
        vocal_language=(args.language if args.language != "auto" else "en"),
        audio_cover_strength=args.strength,
        inference_steps=args.steps,
        guidance_scale=1.0,
        seed=args.seed,
        bpm=(args.bpm if args.bpm and args.bpm > 0 else None),
        keyscale=(args.keyscale or ""),
    )
    if args.bpm and args.bpm > 0:
        logger.info(f"conditioning on explicit BPM={args.bpm} (beat-grid lock)")
    if args.keyscale:
        logger.info(f"conditioning on key={args.keyscale} (harmony lock)")
    config = GenerationConfig(batch_size=1, audio_format="wav")

    t0 = time.time()
    result = generate_music(dit, llm, params=params, config=config, save_dir=args.out_dir)
    el = time.time() - t0
    if not result.success:
        logger.error(f"FAILED — {el:.1f}s — {result.status_message}")
        sys.exit(1)
    logger.info(f"OK — {el:.1f}s")
    for a in result.audios:
        p = a.get("path", "")
        if p:
            print(f"RESULT_WAV={p}")
            logger.info(f"  -> {p}")


if __name__ == "__main__":
    main()
