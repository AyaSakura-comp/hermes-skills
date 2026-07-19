#!/usr/bin/env python3
"""Synthesize speech with a named OmniVoice profile or a one-off reference file."""
import argparse
import json
import mimetypes
import os
import random
import sys
import urllib.request
import uuid


TTS_URL = "http://localhost:8026"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Synthesize speech through the local OmniVoice server."
    )
    parser.add_argument("text")
    parser.add_argument("output_path", nargs="?", default="taigi_speak.wav")
    parser.add_argument("language", nargs="?", default="nan")
    parser.add_argument("speaker", nargs="?", default="default")
    parser.add_argument(
        "--ref-audio",
        help="One-off local reference WAV/MP3/etc.; overrides the named speaker for this request.",
    )
    parser.add_argument("--ref-text", help="Optional transcript of --ref-audio.")
    return parser.parse_args()


def multipart_body(fields, file_field, file_path):
    """Return a minimal multipart body suitable for FastAPI's /clone endpoint."""
    boundary = uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        if value is None:
            continue
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode(),
            b"\r\n",
        ])

    filename = os.path.basename(file_path)
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    with open(file_path, "rb") as ref_file:
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            ref_file.read(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ])
    return boundary, b"".join(chunks)


def synthesize(args, seed):
    if not args.ref_audio:
        body = {
            "text": args.text,
            "language": args.language,
            "num_step": 10,
            "seed": seed,
            "use_default_speaker": True,
            "speaker": args.speaker,
        }
        return urllib.request.Request(
            f"{TTS_URL}/synthesize",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    ref_audio = os.path.abspath(args.ref_audio)
    if not os.path.isfile(ref_audio):
        raise FileNotFoundError(f"Reference audio not found: {ref_audio}")
    boundary, body = multipart_body(
        {
            "text": args.text,
            "language": args.language,
            "num_step": 10,
            "seed": seed,
            "ref_text": args.ref_text,
        },
        "ref_audio",
        ref_audio,
    )
    return urllib.request.Request(
        f"{TTS_URL}/clone",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


def main():
    args = parse_args()
    output_path = os.path.abspath(args.output_path)

    try:
        request = synthesize(args, random.randint(0, 999999))
        with urllib.request.urlopen(request, timeout=90) as response:
            with open(output_path, "wb") as output:
                output.write(response.read())
        print(f"[SUCCESS] Audio saved to: {output_path}")
        print(f"[[file:{output_path}]]")
    except Exception as exc:
        print(f"[ERROR] Synthesis failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
