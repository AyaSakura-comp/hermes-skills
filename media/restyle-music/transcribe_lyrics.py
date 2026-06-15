#!/usr/bin/env python3
"""Transcribe the sung lyrics of an audio file via Ollama gemma4:e2b (audio-capable).

Used by restyle_music.sh -A (auto-lyrics): feed the source song to Gemma, get the lyrics,
hand them to ACE-Step cover so the re-sung vocal keeps the original words while adopting the
new style. Ollama passes audio through the chat API's `images` field (base64), same as the
mock-voice skill's ref_transcribe.py. Prefer a 16kHz mono wav to keep the payload small.

Usage:
  python transcribe_lyrics.py song_16k.wav [model]
"""
import sys, base64, json, urllib.request

MODEL = "gemma4:e2b"
HOST = "http://localhost:11434"
PROMPT = ("Transcribe the sung lyrics in this audio verbatim, in their original language. "
          "Output ONLY the lyrics, one line per sung line — no titles, no timestamps, "
          "no notes, no translation, no commentary.")


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
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.load(resp)
    return data.get("message", {}).get("content", "").strip()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: transcribe_lyrics.py <wav> [model]")
    model = sys.argv[2] if len(sys.argv) > 2 else MODEL
    print(transcribe(sys.argv[1], model))
