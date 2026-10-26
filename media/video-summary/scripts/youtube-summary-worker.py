#!/usr/bin/env python3
"""
YouTube Summary + Gist Upload
=============================
Downloads YouTube videos, transcribes Taiwanese Hokkien with Breeze ASR 26
or other languages with Whisper Turbo, then generates a structured summary
**directly from the transcript** (no external LLM calls).

Supports single video or concurrent multi-video parallel batch processing.

Usage:
    python3 youtube-summary.py <youtube_url> [title]
    python3 youtube-summary.py <url1> <url2> <url3> [--workers 3]
    python3 youtube-summary.py --asr breeze <youtube_url> [title]  # Taiwanese Hokkien

Environment:
    YOUTUBE_SUMMARY_PYTHON     -> Python for Whisper worker (default: Breeze ROCm venv)
    YOUTUBE_SUMMARY_WHISPER_MODEL  -> HF model path or ID
    YOUTUBE_SUMMARY_WHISPER_LANGUAGE -> Force language (e.g. "english")
    YOUTUBE_SUMMARY_YT_DLP     -> Path to yt-dlp executable (auto-discovered from PATH/local if omitted)
    HF_HOME                    -> Hugging Face cache root
    ~/.hermes/.env  -> GITHUB_TOKEN for gist upload
"""

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BREEZE_ASR_URL = "http://127.0.0.1:8025"
BREEZE_ASR_MAX_DURATION = 28  # seconds per segment
WORK_DIR = "/tmp/youtube-summary"
SCRIPT_PATH = os.path.abspath(__file__)
DEFAULT_WHISPER_PYTHON = "/home/chihmin/models-work/flux2/.venv-rocm72/bin/python"
DEFAULT_WHISPER_MODEL = "openai/whisper-large-v3-turbo"


def resolve_whisper_python():
    """Select the ROCm-compatible Python used by the Breeze streaming project."""
    configured = os.environ.get("YOUTUBE_SUMMARY_PYTHON")
    if configured:
        return configured
    if os.path.isfile(DEFAULT_WHISPER_PYTHON):
        return DEFAULT_WHISPER_PYTHON
    return sys.executable


def resolve_whisper_model():
    """Prefer a locally cached HF model, while retaining a portable model ID fallback."""
    configured = os.environ.get("YOUTUBE_SUMMARY_WHISPER_MODEL")
    if configured:
        return configured

    hf_home = Path(os.environ.get("HF_HOME", "/home/chihmin/hf-models"))
    snapshots = hf_home / "hub" / "models--openai--whisper-large-v3-turbo" / "snapshots"
    candidates = [path for path in snapshots.glob("*") if path.is_dir()]
    if candidates:
        return str(max(candidates, key=lambda path: path.stat().st_mtime))
    return DEFAULT_WHISPER_MODEL


def build_whisper_command(audio_path, output_path, python_path=None, model_path=None):
    """Build the Breeze-style Transformers worker command, never the openai-whisper CLI."""
    command = [
        python_path or resolve_whisper_python(),
        SCRIPT_PATH,
        "--whisper-worker",
        "--worker-model", model_path or resolve_whisper_model(),
        "--worker-audio", audio_path,
        "--worker-output", output_path,
    ]
    language = os.environ.get("YOUTUBE_SUMMARY_WHISPER_LANGUAGE")
    if language:
        command.extend(["--worker-language", language])
    return command


def whisper_environment(base=None):
    """Return ROCm settings required by Strix Halo/gfx1151."""
    environment = dict(base or os.environ)
    environment.setdefault("HF_HOME", "/home/chihmin/hf-models")
    environment.setdefault("HSA_OVERRIDE_GFX_VERSION", "11.5.1")
    environment.setdefault("PYTORCH_HIP_ALLOC_CONF", "expandable_segments:True")
    environment.setdefault("TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL", "1")
    environment.setdefault("MIOPEN_FIND_MODE", "FAST")
    return environment


def run(cmd, **kwargs):
    """Run a command and return stdout with useful failure diagnostics."""
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0 and kwargs.get("check", True):
        command = " ".join(cmd)
        details = result.stderr.strip() or result.stdout.strip() or "no output"
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {command}\n{details[-2000:]}"
        )
    return result.stdout.strip()


def get_duration(filepath):
    """Get audio duration in seconds."""
    out = run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", filepath],
        check=False
    )
    try:
        return float(out.split(".")[0])
    except (ValueError, IndexError):
        return 0


def find_downloaded_audio(work_dir):
    """Return yt-dlp downloaded audio file regardless of its container extension."""
    candidates = sorted(Path(work_dir).glob("audio.*"))
    if not candidates:
        candidates = sorted(Path(work_dir).glob("video.*"))
    if not candidates:
        media_exts = {".webm", ".mp4", ".m4a", ".ogg", ".opus", ".wav", ".mkv"}
        candidates = sorted([p for p in Path(work_dir).iterdir() if p.suffix.lower() in media_exts])
    if not candidates:
        raise FileNotFoundError(f"yt-dlp did not produce an audio file in {work_dir}")
    return str(candidates[0])


# Backward compatibility alias
find_downloaded_video = find_downloaded_audio


def resolve_yt_dlp():
    """Resolve the yt-dlp executable path from env, common paths, or PATH."""
    configured = os.environ.get("YOUTUBE_SUMMARY_YT_DLP")
    if configured and os.path.isfile(configured) and os.access(configured, os.X_OK):
        return configured

    # Common installation locations
    common_candidates = [
        os.path.expanduser("~/.local/bin/yt-dlp"),
        "/usr/local/bin/yt-dlp",
        "/usr/bin/yt-dlp",
    ]
    for candidate in common_candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    which_candidate = shutil.which("yt-dlp")
    if which_candidate:
        return which_candidate

    # Fallback: search PATH manually
    for dir_path in os.environ.get("PATH", "").split(os.pathsep):
        if not dir_path:
            continue
        candidate = os.path.join(dir_path, "yt-dlp")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
        candidate_windows = candidate + ".exe"
        if os.path.isfile(candidate_windows):
            return candidate_windows
    return "yt-dlp"


def download_video(url, work_dir=None):
    """Download audio directly with yt-dlp using reliable player clients in an isolated directory."""
    target_dir = work_dir or WORK_DIR
    os.makedirs(target_dir, exist_ok=True)

    yt_dlp = resolve_yt_dlp()
    out_pattern = os.path.join(target_dir, "audio.%(ext)s")
    run([
        yt_dlp,
        "--extractor-args", "youtube:player_client=ios,android,web",
        "-f", "bestaudio/best",
        "-o", out_pattern,
        url
    ])
    return find_downloaded_audio(target_dir)


def extract_audio(video_path, work_dir=None):
    """Convert downloaded audio to Breeze ASR format (ogg)."""
    target_dir = work_dir or os.path.dirname(video_path) or WORK_DIR
    audio_path = os.path.join(target_dir, "audio.ogg")
    run([
        "ffmpeg", "-y", "-i", video_path,
        "-acodec", "libopus",
        "-ar", "48000",
        "-ac", "1",
        "-b:a", "16k",
        "-application", "voip",
        audio_path
    ])
    return audio_path


def get_segments(audio_path, work_dir=None):
    """Split audio into 28-second segments for Breeze ASR."""
    target_dir = work_dir or os.path.dirname(audio_path) or WORK_DIR
    total_duration = get_duration(audio_path)
    num_segments = max(1, int((total_duration + BREEZE_ASR_MAX_DURATION - 1) // BREEZE_ASR_MAX_DURATION))

    segments = []
    for i in range(num_segments):
        start = i * BREEZE_ASR_MAX_DURATION
        seg_path = os.path.join(target_dir, f"part{i}.ogg")
        run([
            "ffmpeg", "-y", "-ss", str(start), "-t", str(BREEZE_ASR_MAX_DURATION),
            "-i", audio_path,
            "-vn",
            "-acodec", "libopus",
            "-ar", "48000",
            "-ac", "1",
            "-b:a", "16k",
            "-application", "voip",
            seg_path
        ])
        segments.append(seg_path)
    return segments


def transcribe_segment(segment_path):
    """Transcribe a single audio segment with Breeze ASR."""
    with open(segment_path, "rb") as f:
        boundary = "----form-boundary-123456"
        body = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"file\"; filename=\"audio.ogg\"\r\n"
            f"Content-Type: audio/ogg\r\n\r\n"
        ).encode()
        body += f.read()
        body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BREEZE_ASR_URL}/transcribe",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }
    )

    try:
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read().decode())
        return result.get("text", ""), result.get("elapsed_s", 0)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"⚠️  ASR error on segment: {error_body[:200]}", file=sys.stderr)
        return "", 0
    except Exception as e:
        print(f"⚠️  ASR failed: {e}", file=sys.stderr)
        return "", 0


def transcribe_with_breeze(audio_path, work_dir=None):
    """Transcribe Taiwanese audio with Breeze ASR 26."""
    target_dir = work_dir or os.path.dirname(audio_path) or WORK_DIR
    segments = get_segments(audio_path, target_dir)
    transcript_segments = []  # (start_s, end_s, text)
    total_elapsed = 0

    for i, seg in enumerate(segments):
        start_s = i * BREEZE_ASR_MAX_DURATION
        text, elapsed = transcribe_segment(seg)
        transcript_segments.append((start_s, start_s + BREEZE_ASR_MAX_DURATION, text))
        total_elapsed += elapsed
        if os.path.exists(seg):
            try:
                os.remove(seg)
            except OSError:
                pass

    return "".join(s[2] for s in transcript_segments), transcript_segments, total_elapsed


def normalize_whisper_segments(chunks):
    """Convert HF Whisper chunks to valid (start, end, text) tuples."""
    normalized = []
    for chunk in chunks:
        text = str(chunk.get("text", "")).strip()
        timestamp = chunk.get("timestamp") or [None, None]
        if not text or timestamp[0] is None:
            continue
        start = float(timestamp[0])
        end = timestamp[1]
        end = float(end) if end is not None else start + 0.01
        if end <= start:
            end = start + 0.01
        normalized.append((start, end, text))
    return normalized


def transcribe_with_whisper(audio_path, work_dir=None):
    """Transcribe non-Taiwanese audio through Breeze Transformers/ROCm path."""
    target_dir = work_dir or os.path.dirname(audio_path) or WORK_DIR
    output_path = os.path.join(target_dir, "audio.json")
    started = time.perf_counter()
    run(
        build_whisper_command(audio_path, output_path),
        env=whisper_environment(),
    )
    elapsed = time.perf_counter() - started

    with open(output_path, encoding="utf-8") as f:
        result = json.load(f)
    transcript_segments = normalize_whisper_segments(result.get("chunks", []))
    return result.get("text", "").strip(), transcript_segments, result.get("elapsed_s", elapsed)


def run_whisper_worker(audio_path, output_path, model_path, language=None):
    """Run inside the Breeze ROCm venv and serialize a Transformers Whisper result."""
    os.environ.update(whisper_environment())
    import torch
    from transformers import AutomaticSpeechRecognitionPipeline, WhisperForConditionalGeneration, WhisperProcessor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    print(
        f"Whisper worker: torch={torch.__version__}, hip={torch.version.hip}, "
        f"device={device}, dtype={dtype}",
        file=sys.stderr,
    )
    processor = WhisperProcessor.from_pretrained(model_path)
    model = WhisperForConditionalGeneration.from_pretrained(
        model_path,
        dtype=dtype,
        attn_implementation="sdpa",
        low_cpu_mem_usage=True,
    ).to(device).eval()
    pipeline = AutomaticSpeechRecognitionPipeline(
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        device=0 if device == "cuda" else -1,
        dtype=dtype,
    )

    started = time.perf_counter()
    generate_kwargs = {"task": "transcribe"}
    if language:
        generate_kwargs["language"] = language
    with torch.inference_mode():
        result = pipeline(audio_path, return_timestamps=True, generate_kwargs=generate_kwargs)
        if device == "cuda":
            torch.cuda.synchronize()
    result = {
        "text": result.get("text", "").strip(),
        "chunks": result.get("chunks", []),
        "elapsed_s": time.perf_counter() - started,
    }
    with open(output_path, "w", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False)


def transcribe_audio(audio_path, asr, work_dir=None):
    """Route transcription to the selected ASR backend."""
    if asr == "breeze":
        return transcribe_with_breeze(audio_path, work_dir)
    return transcribe_with_whisper(audio_path, work_dir)


def format_timestamp(seconds):
    """Format seconds to MM:SS."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def summarize_text(text, max_len=12000):
    """Summarize a transcript by extracting key sentences and grouping by topic.
    
    Simple heuristic summary — no external model calls.
    """
    if not text.strip():
        return "（無可識別內容）"

    clean = " ".join(text.split())
    clean = clean[:max_len]

    sentences = []
    for s in re.split(r"(?<=[。！？.!?])\s*", clean):
        s = s.strip()
        if s:
            sentences.append(s)

    if not sentences:
        return "（無可識別內容）"

    n = len(sentences)
    key_indices = set()
    key_indices.add(0)
    if n > 1:
        key_indices.add(1)
    if n > 2:
        key_indices.add(n - 2)
    if n > 0:
        key_indices.add(n - 1)
    mid = n // 2
    key_indices.add(mid)
    step = max(1, n // 6)
    for i in range(step, n, step):
        key_indices.add(i)

    summary = " ".join(sentences[i] for i in sorted(key_indices) if i < n)
    return summary


def build_section_breakdown(transcript_segments):
    """Build a timestamped section breakdown from transcript segments."""
    if not transcript_segments:
        return []

    segments = [(s, e, t) for s, e, t in transcript_segments if t.strip()]
    if not segments:
        return []

    sections = []
    section_size = 10

    for i in range(0, len(segments), section_size):
        chunk = segments[i:i + section_size]
        start_ts = format_timestamp(chunk[0][0])
        end_ts = format_timestamp(chunk[-1][1])
        full_text = " ".join(t for _, _, t in chunk)
        sentences = re.split(r"(?<=[。！？.!?])\s*", full_text)
        topic_sentences = [s.strip() for s in sentences if s.strip()][:2]
        topic = " ".join(topic_sentences)[:120]
        if not topic:
            topic = f"第{len(sections)+1}段"
        sections.append((start_ts, end_ts, topic, chunk))

    return sections


def generate_summary(transcript, transcript_segments, video_title, video_url, duration_s):
    """Generate a summary directly from the transcript (no external LLM calls)."""
    if not video_title or video_title == "unknown":
        try:
            yt_dlp = resolve_yt_dlp()
            json_out = run([
                yt_dlp,
                "--extractor-args", "youtube:player_client=ios,android,web",
                "--skip-download",
                "-j",
                video_url
            ], check=False)
            if json_out:
                data = json.loads(json_out)
                video_title = data.get("title", "Unknown")
        except Exception:
            pass

    summary_text = summarize_text(transcript)
    sections = build_section_breakdown(transcript_segments)
    return summary_text, sections, video_title


def _load_content(arg):
    """Load content from a file if arg is an existing path, otherwise return arg as raw text."""
    if os.path.isfile(arg):
        with open(arg, "r", encoding="utf-8") as f:
            return f.read()
    return arg


def upload_to_gist(summary_text, transcript_text, title, youtube_url=""):
    """Upload summary and transcript to GitHub Gist."""
    summary_text = _load_content(summary_text)
    transcript_text = _load_content(transcript_text)

    env_path = os.path.expanduser("~/.hermes/.env")
    try:
        with open(env_path) as f:
            for line in f:
                if line.startswith("GITHUB_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                    break
            else:
                return None
    except FileNotFoundError:
        return None

    timestamp = time.strftime("%Y/%m/%d %H:%M:%S")
    formatted_summary = f"""# 🎬 {title}

**來源**: YouTube
{f"**原始連結**: {youtube_url}" if youtube_url else ""}
**上傳時間**: {timestamp}

---

{summary_text}

---
*Generated by youtube-summary skill*
"""

    payload = {
        "description": f"YouTube Summary: {title[:80]}",
        "public": True,
        "files": {
            "summary.md": {"content": formatted_summary},
            "transcript.txt": {"content": transcript_text[:100000]}
        }
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        req = urllib.request.Request(
            "https://api.github.com/gists",
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
                "User-Agent": "pi-youtube-summary"
            }
        )
        resp = urllib.request.urlopen(req, timeout=30)
        gist_data = json.loads(resp.read().decode())
        return gist_data["html_url"]
    except Exception as e:
        print(f"❌ Gist upload error for {title}: {e}", file=sys.stderr)
        return None


def cleanup(work_dir=None):
    """Clean up temporary files."""
    if work_dir and os.path.exists(work_dir):
        try:
            shutil.rmtree(work_dir)
        except OSError:
            pass
    elif os.path.exists(WORK_DIR):
        try:
            shutil.rmtree(WORK_DIR)
        except OSError:
            pass


def process_single_video(youtube_url, video_title="unknown", asr="whisper", upload_gist_flag=True, verbose=True):
    """Process a single YouTube video in an isolated working directory."""
    task_work_dir = tempfile.mkdtemp(prefix="youtube-summary-")
    result = {
        "url": youtube_url,
        "title": video_title,
        "summary_md": "",
        "summary_text": "",
        "transcript": "",
        "segments": [],
        "gist_url": None,
        "elapsed_s": 0,
        "duration_s": 0,
        "error": None,
    }

    if verbose:
        print(f"🎯 [{youtube_url}] Starting processing...")

    try:
        # Step 1: Download
        if verbose:
            print(f"📥 [{youtube_url}] Downloading audio...")
        video_path = download_video(youtube_url, work_dir=task_work_dir)

        # Step 2: Extract audio
        if verbose:
            print(f"🎵 [{youtube_url}] Converting audio...")
        audio_path = extract_audio(video_path, work_dir=task_work_dir)

        # Step 3: Transcribe
        if verbose:
            asr_name = "Breeze ASR 26 (Taiwanese)" if asr == "breeze" else "Whisper Turbo"
            print(f"🎙️ [{youtube_url}] Transcribing with {asr_name}...")
        transcript, transcript_segments, elapsed = transcribe_audio(audio_path, asr, work_dir=task_work_dir)
        result["transcript"] = transcript
        result["segments"] = transcript_segments
        result["elapsed_s"] = elapsed

        if not transcript.strip() and verbose:
            print(f"⚠️  [{youtube_url}] Transcription returned empty text (music/silent video).")

        # Step 4: Generate summary
        audio_duration = get_duration(audio_path)
        result["duration_s"] = audio_duration
        summary_text, sections, final_title = generate_summary(
            transcript, transcript_segments, video_title, youtube_url, audio_duration
        )
        result["title"] = final_title
        result["summary_text"] = summary_text

        # Build formatted summary markdown
        timestamp = time.strftime("%Y/%m/%d %H:%M:%S")
        duration_str = f"{int(audio_duration // 60)} 分 {int(audio_duration % 60)} 秒"
        summary_md = f"""# 🎬 {final_title}

**來源**: YouTube
**原始連結**: {youtube_url}
**影片長度**: {duration_str}
**上傳時間**: {timestamp}

---

## 一、完整摘要

{summary_text}

---

## 二、逐段內容拆解

"""
        for start_ts, end_ts, topic, chunk in sections:
            summary_md += f"### ⏱️ {start_ts} - {end_ts} 【{topic}】\n"
            for _, _, text in chunk:
                if text.strip():
                    summary_md += f"- {text.strip()}\n"
            summary_md += "\n"

        summary_md += "---\n*Generated by youtube-summary skill (no external LLM calls)*\n"
        result["summary_md"] = summary_md

        # Gist upload
        if upload_gist_flag:
            summary_file = os.path.join(task_work_dir, "summary.md")
            transcript_file = os.path.join(task_work_dir, "transcript.txt")
            with open(summary_file, "w", encoding="utf-8") as f:
                f.write(summary_md)
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(transcript)
            gist_url = upload_to_gist(summary_file, transcript_file, final_title, youtube_url)
            result["gist_url"] = gist_url

        if verbose:
            print(f"✅ [{youtube_url}] Finished in {elapsed:.1f}s — '{final_title}'")

    except Exception as e:
        result["error"] = str(e)
        if verbose:
            print(f"❌ [{youtube_url}] Error: {e}", file=sys.stderr)
    finally:
        cleanup(task_work_dir)

    return result


def parse_args(argv=None):
    """Parse command-line options for the YouTube summary pipeline and worker."""
    parser = argparse.ArgumentParser(description="YouTube Summary with ASR + Concurrency")
    parser.add_argument(
        "--asr", choices=("whisper", "breeze"), default="whisper",
        help="Use Breeze ASR 26 (Taiwanese) or Breeze-style Whisper Turbo worker.",
    )
    parser.add_argument(
        "--workers", "-w", type=int, default=3,
        help="Max concurrent workers for batch processing (default: 3).",
    )
    parser.add_argument(
        "--no-gist", action="store_true",
        help="Skip uploading to GitHub Gist.",
    )
    parser.add_argument("--whisper-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--worker-audio", help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", help=argparse.SUPPRESS)
    parser.add_argument("--worker-model", help=argparse.SUPPRESS)
    parser.add_argument("--worker-language", help=argparse.SUPPRESS)
    parser.add_argument("positionals", nargs="*", help="YouTube URL(s) or URL and optional Title")

    args = parser.parse_args(argv)

    # Reconstruct single URL / title / multi-urls for backward compatibility
    pos = args.positionals or []
    if len(pos) == 2 and not pos[1].startswith(("http://", "https://", "youtu.be", "youtube.com")):
        args.urls = [pos[0]]
        args.url = pos[0]
        args.title = pos[1]
    elif len(pos) >= 1:
        args.urls = pos
        args.url = pos[0]
        args.title = "unknown"
    else:
        args.urls = []
        args.url = None
        args.title = "unknown"

    return args


def main():
    args = parse_args()
    if args.whisper_worker:
        if not all((args.worker_audio, args.worker_output, args.worker_model)):
            raise ValueError("Whisper worker requires audio, output, and model paths")
        run_whisper_worker(
            args.worker_audio,
            args.worker_output,
            args.worker_model,
            args.worker_language,
        )
        return

    if not args.urls:
        raise ValueError("At least one YouTube URL is required")

    upload_gist = not args.no_gist
    num_urls = len(args.urls)

    # Single video mode
    if num_urls == 1:
        url = args.urls[0]
        title = args.title
        res = process_single_video(url, title, asr=args.asr, upload_gist_flag=upload_gist, verbose=True)

        if res["error"]:
            print(f"\n❌ Pipeline failed: {res['error']}", file=sys.stderr)
            sys.exit(1)

        print(f"\n{'='*60}")
        print("📄 TRANSCRIPT:")
        print(f"{'='*60}")
        print(res["transcript"])
        print(f"\n{'='*60}")
        print("📝 FORMATTED SUMMARY:")
        print(f"{'='*60}")
        print(res["summary_md"])
        print(f"\n{'='*60}")
        print("📋 TRANSCRIPT SEGMENTS (JSON):")
        print(f"{'='*60}")
        print(json.dumps(res["segments"], ensure_ascii=False))

        if res["gist_url"]:
            print(f"\n✅ Gist URL: {res['gist_url']}")
        return

    # Concurrent Multi-Video Batch Mode
    print(f"🚀 Launching concurrent batch for {num_urls} videos with {min(num_urls, args.workers)} workers...")
    t0 = time.time()
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(num_urls, args.workers)) as executor:
        future_to_url = {
            executor.submit(process_single_video, url, "unknown", args.asr, upload_gist, True): url
            for url in args.urls
        }
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                data = future.result()
                results.append(data)
            except Exception as exc:
                results.append({"url": url, "title": "Failed", "error": str(exc), "gist_url": None})

    total_time = time.time() - t0
    print(f"\n{'='*60}")
    print(f"🎉 BATCH COMPLETED ({len(results)}/{num_urls} processed in {total_time:.1f}s)")
    print(f"{'='*60}")

    for idx, res in enumerate(results, 1):
        print(f"\n[{idx}/{len(results)}] {res.get('title', 'Unknown')}")
        print(f"🔗 URL: {res['url']}")
        if res.get("gist_url"):
            print(f"📋 Gist: {res['gist_url']}")
        if res.get("error"):
            print(f"⚠️ Error: {res['error']}")
        else:
            print(f"📝 Summary:\n{res.get('summary_text', '')}\n")


if __name__ == "__main__":
    main()
