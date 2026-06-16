#!/usr/bin/env python3
"""Transcribe a reference audio clip via Ollama gemma4:e2b (audio-capable), print the text.

Replaces OmniVoice's built-in Whisper for generating --ref_text. Ollama passes audio
through the chat API's `images` field (base64) for audio-capable models.

Usage:
  python ref_transcribe.py asset_mock/ref_16k.wav
  # then: ... omnivoice.cli.infer --ref_text "$(python ref_transcribe.py ref.wav)" ...
"""
import sys, base64, json, urllib.request

MODEL = "gemma4:e2b"
HOST = "http://localhost:11434"
PROMPT = ("Transcribe the speech in this audio verbatim, in its original language. "
          "Output ONLY the transcription text — no quotes, no notes, no translation.")


def transcribe(wav_path: str, model: str = MODEL) -> str:
    with open(wav_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT, "images": [b64]}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
    }
    req = urllib.request.Request(
        f"{HOST}/api/chat", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    return data.get("message", {}).get("content", "").strip()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: ref_transcribe.py <wav> [model]")
    model = sys.argv[2] if len(sys.argv) > 2 else MODEL
    print(transcribe(sys.argv[1], model))
