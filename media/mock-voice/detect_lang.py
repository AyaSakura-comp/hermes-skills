#!/usr/bin/env python3
"""Detect the language of a text and print an OmniVoice language code (ja/zh/en/ko/...).

Script-based detection (fast, offline) covering the common cases; for Latin-script text it
uses `langdetect` if available, else falls back to English. OmniVoice accepts the printed code
(or a full name) and gracefully falls back to language-agnostic mode for anything unknown.

Usage:  python detect_lang.py "今日はいい天気ですね"   ->  ja
"""
import sys, re


def detect(text: str) -> str:
    # Script ranges
    if re.search(r"[぀-ゟ゠-ヿ]", text):   # hiragana / katakana
        return "ja"
    if re.search(r"[가-힯ᄀ-ᇿ]", text):   # hangul
        return "ko"
    if re.search(r"[一-鿿㐀-䶿]", text):   # Han (no kana/hangul above) -> Chinese
        return "zh"
    if re.search(r"[Ѐ-ӿ]", text):                # Cyrillic
        return "ru"
    if re.search(r"[؀-ۿ]", text):                # Arabic
        return "ar"
    if re.search(r"[฀-๿]", text):                # Thai
        return "th"
    if re.search(r"[ऀ-ॿ]", text):                # Devanagari -> Hindi
        return "hi"
    # Latin / other: try langdetect, else default English
    try:
        from langdetect import detect as _ld
        code = _ld(text)            # ISO 639-1, mostly aligns with OmniVoice codes
        return code.split("-")[0]
    except Exception:
        return "en"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: detect_lang.py <text>")
    print(detect(" ".join(sys.argv[1:])))
