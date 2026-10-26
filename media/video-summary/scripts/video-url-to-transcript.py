#!/usr/bin/env python3
"""Download a video URL as audio and transcribe the complete recording."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SUMMARY_SCRIPT = Path.home() / "Desktop/hermes-agent/skills/media/youtube-summary/scripts/youtube-summary.py"
DEFAULT_PYTHON = "/home/chihmin/models-work/flux2/.venv-rocm72/bin/python"
DEFAULT_MODEL_ROOT = Path.home() / "hf-models/hub/models--openai--whisper-large-v3-turbo/snapshots"
WHISPER_CHUNK_SECONDS = 300


class GlobalWhisperQueue:
    """Feed one persistent Whisper worker in FIFO order across all videos."""

    _STOP = object()

    def __init__(self, handler, maxsize=8):
        self._handler = handler
        self._queue = queue.Queue(maxsize=maxsize)
        self._thread = None
        self._error = None

    def start(self):
        if self._thread is not None:
            raise RuntimeError("GlobalWhisperQueue has already started")
        self._thread = threading.Thread(target=self._run, name="whisper-queue", daemon=True)
        self._thread.start()

    def submit(self, job):
        if self._thread is None:
            raise RuntimeError("GlobalWhisperQueue must be started before submit")
        if self._error is not None:
            raise RuntimeError("Global Whisper worker failed") from self._error
        self._queue.put(job)
        if self._error is not None:
            raise RuntimeError("Global Whisper worker failed") from self._error

    def _run(self):
        while True:
            job = self._queue.get()
            try:
                if job is self._STOP:
                    return
                if self._error is None:
                    self._handler(job)
            except BaseException as exc:  # propagate worker failures through close()
                self._error = exc
            finally:
                self._queue.task_done()

    def close(self):
        if self._thread is None:
            return
        self._queue.put(self._STOP)
        self._queue.join()
        self._thread.join()
        if self._error is not None:
            raise RuntimeError("Global Whisper worker failed") from self._error


def run(cmd: list[str], env=None) -> None:
    print("+", " ".join(map(str, cmd)), file=sys.stderr)
    subprocess.run(cmd, check=True, env=env)


def yt_dlp() -> str:
    configured = os.environ.get("YOUTUBE_SUMMARY_YT_DLP")
    if configured:
        return configured
    return shutil.which("yt-dlp") or str(Path.home() / ".local/bin/yt-dlp")


def newest_snapshot() -> str | None:
    candidates = [p for p in DEFAULT_MODEL_ROOT.glob("*") if p.is_dir()]
    return str(max(candidates, key=lambda p: p.stat().st_mtime)) if candidates else None


def import_summary_module():
    spec = importlib.util.spec_from_file_location("youtube_summary", SUMMARY_SCRIPT)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load {SUMMARY_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def download(url: str, out: Path) -> Path:
    run([yt_dlp(), "--no-playlist", "--extractor-args", "youtube:player_client=ios,android,web", "-f", "bestaudio/best", "-o", str(out / "source.%(ext)s"), url])
    files = [p for p in out.glob("source.*") if p.suffix not in {".part", ".ytdl"}]
    if not files:
        raise RuntimeError("yt-dlp did not produce an audio file")
    return max(files, key=lambda p: p.stat().st_mtime)


def extract_visual_frames(source: Path, out: Path, count: int) -> list[str]:
    """Extract evenly spaced keyframes for visual/video recognition."""
    if count <= 0:
        return []
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(source)], capture_output=True, text=True)
    if not probe.stdout.strip():
        return []
    frames_dir = out / "visual-frames"
    frames_dir.mkdir(exist_ok=True)
    duration_probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(source)], capture_output=True, text=True, check=True)
    duration = max(float(duration_probe.stdout.strip()), 1.0)
    fps = count / duration
    run(["ffmpeg", "-y", "-i", str(source), "-vf", f"fps={fps:.8f},scale=640:-1", "-frames:v", str(count), str(frames_dir / "frame_%03d.jpg")])
    return [str(p) for p in sorted(frames_dir.glob("frame_*.jpg"))]


def convert(source: Path, out: Path) -> tuple[Path, Path]:
    mp3 = out / "audio.mp3"
    ogg = out / "audio.ogg"
    run(["ffmpeg", "-y", "-i", str(source), "-vn", "-codec:a", "libmp3lame", "-q:a", "2", str(mp3)])
    run(["ffmpeg", "-y", "-i", str(mp3), "-acodec", "libopus", "-ar", "48000", "-ac", "1", "-b:a", "16k", "-application", "voip", str(ogg)])
    return mp3, ogg


def transcribe_breeze(ogg: Path, out: Path):
    mod = import_summary_module()
    text, segments, elapsed = mod.transcribe_with_breeze(str(ogg), str(out))
    return text, [(float(a), float(b), str(t)) for a, b, t in segments], elapsed


def transcribe_whisper(mp3: Path, out: Path):
    """Use the approved ROCm worker per five-minute chunk."""
    worker_python = os.environ.get("YOUTUBE_SUMMARY_PYTHON", DEFAULT_PYTHON)
    model = os.environ.get("YOUTUBE_SUMMARY_WHISPER_MODEL") or newest_snapshot() or "openai/whisper-large-v3-turbo"
    chunks_dir = out / "whisper-chunks"
    chunks_dir.mkdir(exist_ok=True)
    run(["ffmpeg", "-y", "-i", str(mp3), "-f", "segment", "-segment_time", "300", "-c", "copy", str(chunks_dir / "chunk_%03d.mp3")])
    segments = []
    full_text = []
    chunks = sorted(chunks_dir.glob("chunk_*.mp3"))
    env = os.environ.copy()
    env.update({"HSA_OVERRIDE_GFX_VERSION": "11.5.1", "PYTORCH_HIP_ALLOC_CONF": "expandable_segments:True", "TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL": "1"})
    for index, chunk in enumerate(chunks):
        result_path = out / f"chunk_{index:03d}.json"
        cmd = [worker_python, str(SUMMARY_SCRIPT), "--whisper-worker", "--worker-model", model, "--worker-audio", str(chunk), "--worker-output", str(result_path)]
        run(cmd, env=env)
        data = json.loads(result_path.read_text(encoding="utf-8"))
        full_text.append(data.get("text", "").strip())
        for item in data.get("chunks", []):
            ts = item.get("timestamp") or [None, None]
            if ts[0] is None:
                continue
            start = float(ts[0]) + index * 300
            end = float(ts[1] if ts[1] is not None else ts[0] + 0.01) + index * 300
            if end <= start:
                end = start + 0.01
            text = str(item.get("text", "")).strip()
            if text:
                segments.append((start, end, text))
    return "\n".join(t for t in full_text if t), segments, None


class WhisperServer:
    """Keep one ROCm/Whisper process alive for the whole global queue."""

    def __init__(self, model: str, language: str | None = None):
        worker_python = os.environ.get("YOUTUBE_SUMMARY_PYTHON", DEFAULT_PYTHON)
        command = [
            worker_python,
            str(SUMMARY_SCRIPT),
            "--whisper-worker-server",
            "--worker-model", model,
        ]
        if language:
            command.extend(["--worker-language", language])
        env = os.environ.copy()
        env.update({
            "HSA_OVERRIDE_GFX_VERSION": "11.5.1",
            "PYTORCH_HIP_ALLOC_CONF": "expandable_segments:True",
            "TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL": "1",
        })
        print("+", " ".join(command), file=sys.stderr)
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            bufsize=1,
            env=env,
        )
        self._status_errors = []
        self._reader = threading.Thread(target=self._read_status, name="whisper-status", daemon=True)
        self._reader.start()

    def _read_status(self):
        assert self.process.stdout is not None
        for line in self.process.stdout:
            try:
                status = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not status.get("ok", False):
                self._status_errors.append(status.get("error", "unknown Whisper error"))

    def send(self, job):
        if self.process.poll() is not None:
            raise RuntimeError(f"Whisper server exited with code {self.process.returncode}")
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(job, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def close(self):
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        returncode = self.process.wait()
        self._reader.join(timeout=5)
        if returncode != 0:
            raise RuntimeError(f"Whisper server exited with code {returncode}")
        if self._status_errors:
            raise RuntimeError("Whisper job failed: " + self._status_errors[0])


def split_whisper_chunks(mp3: Path, out: Path) -> list[Path]:
    """Create five-minute chunks before they enter the global Whisper queue."""
    chunks_dir = out / "whisper-chunks"
    chunks_dir.mkdir(exist_ok=True)
    for old_chunk in chunks_dir.glob("chunk_*.mp3"):
        old_chunk.unlink()
    run([
        "ffmpeg", "-y", "-i", str(mp3),
        "-f", "segment", "-segment_time", str(WHISPER_CHUNK_SECONDS),
        "-c", "copy", str(chunks_dir / "chunk_%03d.mp3"),
    ])
    return sorted(chunks_dir.glob("chunk_*.mp3"))


def prepare_whisper_url(url: str, out: Path, visual_frames: int) -> dict:
    """Download and prepare one video; ASR is submitted later to the global queue."""
    out.mkdir(parents=True, exist_ok=True)
    source = download(url, out)
    visuals = extract_visual_frames(source, out, visual_frames)
    mp3, _ogg = convert(source, out)
    source.unlink(missing_ok=True)
    chunks = split_whisper_chunks(mp3, out)
    return {"url": url, "out": out, "audio": mp3, "visuals": visuals, "chunks": chunks}


def valid_whisper_result(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and "text" in data and "chunks" in data


def finalize_whisper_video(prepared: dict) -> dict:
    """Join per-chunk results and restore whole-video timestamps."""
    out = prepared["out"]
    segments = []
    full_text = []
    for index, _chunk in enumerate(prepared["chunks"]):
        result_path = out / f"chunk_{index:03d}.json"
        data = json.loads(result_path.read_text(encoding="utf-8"))
        text = data.get("text", "").strip()
        if text:
            full_text.append(text)
        for item in data.get("chunks", []):
            ts = item.get("timestamp") or [None, None]
            if ts[0] is None:
                continue
            start = float(ts[0]) + index * WHISPER_CHUNK_SECONDS
            end = float(ts[1] if ts[1] is not None else ts[0] + 0.01) + index * WHISPER_CHUNK_SECONDS
            if end <= start:
                end = start + 0.01
            item_text = str(item.get("text", "")).strip()
            if item_text:
                segments.append((start, end, item_text))

    text = "\n".join(full_text)
    transcript_path = out / "transcript.txt"
    timestamped_path = out / "transcript.json"
    transcript_path.write_text(text + "\n", encoding="utf-8")
    timestamped_path.write_text(
        json.dumps({"text": text, "segments": segments}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest = {
        "url": prepared["url"],
        "asr": "whisper",
        "source": None,
        "source_deleted": True,
        "visual_frames": prepared["visuals"],
        "audio": str(prepared["audio"]),
        "transcript": str(transcript_path),
        "timestamped_transcript": str(timestamped_path),
        "transcript_chars": len(text),
        "elapsed_s": None,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def process_url(url: str, out: Path, asr: str, visual_frames: int) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    source = download(url, out)
    visuals = extract_visual_frames(source, out, visual_frames)
    mp3, ogg = convert(source, out)
    source.unlink(missing_ok=True)
    if asr == "breeze":
        text, segments, elapsed = transcribe_breeze(ogg, out)
    else:
        text, segments, elapsed = transcribe_whisper(mp3, out)
    transcript_path = out / "transcript.txt"
    timestamped_path = out / "transcript.json"
    transcript_path.write_text(text + "\n", encoding="utf-8")
    timestamped_path.write_text(json.dumps({"text": text, "segments": segments}, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"url": url, "asr": asr, "source": None, "source_deleted": True, "visual_frames": visuals, "audio": str(mp3), "transcript": str(transcript_path), "timestamped_transcript": str(timestamped_path), "transcript_chars": len(text), "elapsed_s": elapsed}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def process_whisper_batch(jobs: list[tuple[str, Path]], prepare_workers: int, visual_frames: int) -> list[dict]:
    """Prepare URLs concurrently, then serialize all GPU ASR through one queue."""
    model = os.environ.get("YOUTUBE_SUMMARY_WHISPER_MODEL") or newest_snapshot() or "openai/whisper-large-v3-turbo"
    language = os.environ.get("YOUTUBE_SUMMARY_WHISPER_LANGUAGE")
    server = WhisperServer(model, language)
    whisper_queue = GlobalWhisperQueue(server.send, maxsize=8)
    whisper_queue.start()
    prepared = {}
    errors = {}
    try:
        worker_count = max(1, min(prepare_workers, len(jobs)))
        print(
            f"Preparing {len(jobs)} video(s) with {worker_count} worker(s); "
            "Whisper uses one global GPU queue.",
            file=sys.stderr,
        )
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            future_to_index = {
                pool.submit(prepare_whisper_url, url, out, visual_frames): index
                for index, (url, out) in enumerate(jobs)
            }
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                url, _out = jobs[index]
                try:
                    item = future.result()
                    prepared[index] = item
                    for chunk_index, chunk in enumerate(item["chunks"]):
                        result_path = item["out"] / f"chunk_{chunk_index:03d}.json"
                        if not valid_whisper_result(result_path):
                            whisper_queue.submit({
                                "audio": str(chunk),
                                "output": str(result_path),
                            })
                except Exception as exc:
                    errors[index] = {"url": url, "error": str(exc)}
        whisper_queue.close()
    finally:
        server.close()

    results = []
    for index, (url, _out) in enumerate(jobs):
        if index in errors:
            results.append(errors[index])
            continue
        try:
            results.append(finalize_whisper_video(prepared[index]))
        except Exception as exc:
            results.append({"url": url, "error": str(exc)})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="+", help="one or more video URLs")
    parser.add_argument("--output-dir", default="/tmp/video-transcript")
    parser.add_argument("--asr", choices=["whisper", "breeze"], default="whisper")
    parser.add_argument(
        "--workers", type=int, default=1,
        help="parallel download/FFmpeg preparation workers; Whisper stays in one global GPU queue",
    )
    parser.add_argument("--visual-frames", type=int, default=0, help="evenly spaced frames for raw video recognition; 0 disables extraction (default)")
    args = parser.parse_args()
    base = Path(args.output_dir).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    jobs = []
    for index, url in enumerate(args.urls, 1):
        out = base if len(args.urls) == 1 else base / f"item_{index:02d}"
        jobs.append((url, out))
    if args.asr == "whisper":
        results = process_whisper_batch(jobs, max(1, args.workers), args.visual_frames)
    else:
        results = []
        if args.workers <= 1 or len(jobs) == 1:
            for url, out in jobs:
                results.append(process_url(url, out, args.asr, args.visual_frames))
        else:
            with ThreadPoolExecutor(max_workers=min(args.workers, len(jobs))) as pool:
                futures = [pool.submit(process_url, url, out, args.asr, args.visual_frames) for url, out in jobs]
                for future in as_completed(futures):
                    results.append(future.result())
            results.sort(key=lambda item: args.urls.index(item["url"]))
    batch = {"count": len(results), "results": results}
    if len(results) > 1:
        (base / "batch-manifest.json").write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(batch if len(results) > 1 else results[0], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
