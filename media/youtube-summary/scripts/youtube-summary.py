#!/usr/bin/env python3
"""
YouTube Summary + Gist Upload
=============================
Downloads a YouTube video, transcribes Taiwanese Hokkien with Breeze ASR 26
or other languages with Whisper Turbo, then generates a Chinese summary.

Usage:
    python3 youtube-summary.py <youtube_url> [title]

Environment:
    ~/.hermes/.env  -> GITHUB_TOKEN for gist upload
"""

import argparse
import sys
import os
import json
import subprocess
import time
import urllib.request
import urllib.error
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


def find_downloaded_video(work_dir):
    """Return yt-dlp's downloaded video regardless of its container extension."""
    candidates = sorted(Path(work_dir).glob("video.*"))
    if not candidates:
        raise FileNotFoundError(f"yt-dlp did not produce a video in {work_dir}")
    return str(candidates[0])


def download_video(url):
    """Download video with yt-dlp."""
    os.makedirs(WORK_DIR, exist_ok=True)
    os.chdir(WORK_DIR)

    print("📥 Downloading video...")
    run([
        "yt-dlp", "-f", "bestvideo+bestaudio/best",
        "-o", "video.%(ext)s",
        url
    ])
    return find_downloaded_video(WORK_DIR)


def extract_audio(video_path):
    """Extract and convert audio to Breeze ASR format."""
    audio_path = os.path.join(WORK_DIR, "audio.ogg")
    print("🎵 Extracting audio...")
    run([
        "ffmpeg", "-y", "-i", video_path,
        "-vn",
        "-acodec", "libopus",
        "-ar", "48000",
        "-ac", "1",
        "-b:a", "16k",
        "-application", "voip",
        audio_path
    ])
    return audio_path


def get_segments(audio_path):
    """Split audio into 28-second segments for Breeze ASR."""
    total_duration = get_duration(audio_path)
    num_segments = max(1, int((total_duration + BREEZE_ASR_MAX_DURATION - 1) // BREEZE_ASR_MAX_DURATION))

    print(f"🔪 Splitting into {num_segments} segment(s) ({total_duration:.0f}s total)...")

    segments = []
    for i in range(num_segments):
        start = i * BREEZE_ASR_MAX_DURATION
        seg_path = os.path.join(WORK_DIR, f"part{i}.ogg")
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
        # Build multipart form data manually
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
        print(f"⚠️  ASR error on segment: {error_body[:200]}")
        return "", 0
    except Exception as e:
        print(f"⚠️  ASR failed: {e}")
        return "", 0


def transcribe_with_breeze(audio_path):
    """Transcribe Taiwanese audio with Breeze ASR 26."""
    segments = get_segments(audio_path)
    transcript_segments = []  # (start_s, end_s, text)
    total_elapsed = 0

    print("🎤 Transcribing...")
    for i, seg in enumerate(segments):
        start_s = i * BREEZE_ASR_MAX_DURATION
        text, elapsed = transcribe_segment(seg)
        transcript_segments.append((start_s, start_s + BREEZE_ASR_MAX_DURATION, text))
        total_elapsed += elapsed
        print(f"  [{i+1}/{len(segments)}] {elapsed:.1f}s -> {len(text)} chars")
        os.remove(seg)  # Clean up segment

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


def transcribe_with_whisper(audio_path):
    """Transcribe non-Taiwanese audio through Breeze's Transformers/ROCm path."""
    output_path = os.path.join(WORK_DIR, "audio.json")
    print("🎤 Transcribing with Breeze-style Whisper Turbo...")
    print(f"   Python: {resolve_whisper_python()}")
    print(f"   Model: {resolve_whisper_model()}")
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


def transcribe_audio(audio_path, asr):
    """Route transcription to the selected ASR backend."""
    if asr == "breeze":
        return transcribe_with_breeze(audio_path)
    return transcribe_with_whisper(audio_path)


def format_timestamp(seconds):
    """Format seconds to MM:SS."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def generate_summary(transcript, transcript_segments, video_title, video_url, duration_s):
    """Generate a section-by-section breakdown summary using Qwen."""
    # First get the video title from yt-dlp if not provided
    if not video_title or video_title == "unknown":
        try:
            json_out = run([
                "yt-dlp", "--skip-download", "-j", video_url
            ], check=False)
            if json_out:
                data = json.loads(json_out)
                video_title = data.get("title", "Unknown")
        except:
            pass

    # Build a concise version with timestamps for the prompt
    timestamped_text = ""
    for start, end, text in transcript_segments:
        if text.strip():
            timestamped_text += f"[{format_timestamp(start)}-{format_timestamp(end)}] {text}\n"

    summary_prompt = f"""請根據以下 YouTube 影片逐字稿（已分段帶時間軸），整理出詳細的摘要。

⚠️ **重要：請先寫「完整摘要」在最前面，讓讀者不用往下看就能掌握重點。**

影片標題：{video_title}
影片長度：{int(duration_s // 60)} 分 {int(duration_s % 60)} 秒

逐字稿（帶時間軸）：
{timestamped_text[:15000]}  # Limit to avoid token limits

請用繁體中文整理出以下結構：

---

## 一、完整摘要

用 3-5 個要點總結整支影片的核心內容，讓讀者看完就能掌握重點。
例如：
- **核心觀點**：...
- **關鍵發現**：...
- **結論**：...

---

## 二、逐段內容拆解

把影片分成幾個主要段落，每段標註時間軸和重點：

### ⏱️ 00:00 - 01:30 【第一段主題】
- 這段在講什麼...
- 關鍵信息...

### ⏱️ 01:30 - 03:45 【第二段主題】
- 這段在講什麼...
- 關鍵數據或論點...

（依此類推，直到影片結束）

---

## 三、重點數據／事實
列出影片中提到的重要數據、比較、或事實（如果有）

---

## 四、結論／感想
影片最後的結論或觀眾應該帶走什麼

請用繁體中文回答，語氣自然流暢，每個大段之間用 --- 分隔線隔開。"""

    print("🤖 Generating summary with Qwen...")
    # We'll let Qwen handle this via the normal chat flow
    return summary_prompt, video_title


def upload_to_gist(summary_text, transcript_text, title):
    """Upload summary and transcript to GitHub Gist."""
    # Read token
    env_path = os.path.expanduser("~/.hermes/.env")
    try:
        with open(env_path) as f:
            for line in f:
                if line.startswith("GITHUB_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                    break
            else:
                print("❌ GITHUB_TOKEN not found in ~/.hermes/.env")
                return None
    except FileNotFoundError:
        print("❌ ~/.hermes/.env not found")
        return None

    # Create formatted summary
    timestamp = __import__("datetime").datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    formatted_summary = f"""# 🎬 {title}

**來源**: YouTube
**原始連結**: {youtube_url}
**上傳時間**: {timestamp}

---

{summary_text}

---
*Generated by youtube-summary skill*
"""

    # Build payload using Python for safe JSON encoding
    payload = {
        "description": f"YouTube Summary: {title[:80]}",
        "public": True,
        "files": {
            "summary.md": {"content": formatted_summary},
            "transcript.txt": {"content": transcript_text[:100000]}  # Limit size
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

    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"❌ Gist upload failed: HTTP {e.code}")
        print(error_body[:500])
        return None
    except Exception as e:
        print(f"❌ Gist upload error: {e}")
        return None


def cleanup():
    """Clean up temporary files."""
    import shutil
    if os.path.exists(WORK_DIR):
        shutil.rmtree(WORK_DIR)


def parse_args(argv=None):
    """Parse command-line options for the YouTube summary pipeline and worker."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--asr", choices=("whisper", "breeze"), default="whisper",
        help="Use Breeze ASR 26 (Taiwanese) or the Breeze-style Whisper Turbo worker.",
    )
    parser.add_argument("--whisper-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--worker-audio", help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", help=argparse.SUPPRESS)
    parser.add_argument("--worker-model", help=argparse.SUPPRESS)
    parser.add_argument("--worker-language", help=argparse.SUPPRESS)
    parser.add_argument("url", nargs="?", help="YouTube video URL")
    parser.add_argument("title", nargs="?", default="unknown", help="Optional video title")
    return parser.parse_args(argv)


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
    if not args.url:
        raise ValueError("YouTube URL is required")
    youtube_url = args.url
    video_title = args.title

    print(f"🎯 Processing: {youtube_url}")
    print(f"📝 Title: {video_title}")
    print(f"🎙️ ASR: {'Breeze ASR 26 (Taiwanese)' if args.asr == 'breeze' else 'Whisper Turbo'}")
    print()

    try:
        # Step 1: Download
        video_path = download_video(youtube_url)

        # Step 2: Extract audio
        audio_path = extract_audio(video_path)

        # Step 3: Transcribe
        transcript, transcript_segments, elapsed = transcribe_audio(audio_path, args.asr)

        if not transcript.strip():
            print("⚠️  Transcription returned empty text!")
            print("   The video might have no speech or music only.")

        print(f"\n📊 Total transcription time: {elapsed:.1f}s")
        print(f"📝 Transcript length: {len(transcript)} chars")

        # Step 4: Generate detailed summary prompt (Qwen will do the summarization)
        summary_prompt, final_title = generate_summary(transcript, transcript_segments, video_title, youtube_url, get_duration(audio_path))

        # Return transcript and summary prompt for Qwen to process
        print(f"\n{'='*60}")
        print("📄 TRANSCRIPT:")
        print(f"{'='*60}")
        print(transcript)
        print(f"\n{'='*60}")
        print("📝 SUMMARY PROMPT (for Qwen):")
        print(f"{'='*60}")
        print(summary_prompt)

        # Also save transcript_segments for Qwen to reference
        segments_json = json.dumps(transcript_segments, ensure_ascii=False)
        print(f"\n{'='*60}")
        print("📋 TRANSCRIPT SEGMENTS (JSON for Qwen):")
        print(f"{'='*60}")
        print(segments_json)

        # Cleanup
        cleanup()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        cleanup()
        sys.exit(1)


if __name__ == "__main__":
    main()
