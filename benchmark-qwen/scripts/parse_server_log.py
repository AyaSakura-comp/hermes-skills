#!/usr/bin/env python3
"""Parse exactly one llama-server request's timing metrics as JSON."""

import json
import re
import sys
from pathlib import Path


PATTERNS = {
    "prefill": re.compile(
        r"^prompt eval time =\s+([0-9.]+) ms /\s+(\d+) tokens .*?([0-9.]+) tokens per second",
        re.MULTILINE,
    ),
    "decode": re.compile(
        r"^\s*eval time =\s+([0-9.]+) ms /\s+(\d+) tokens .*?([0-9.]+) tokens per second",
        re.MULTILINE,
    ),
    "acceptance": re.compile(r"^draft acceptance rate =\s+([0-9.]+)", re.MULTILINE),
}


def fail(message: str) -> "None":
    raise SystemExit(f"ERROR: {message}")


def main() -> int:
    if len(sys.argv) != 2:
        fail(f"usage: {Path(sys.argv[0]).name} LLAMA_SERVER_LOG")

    text = Path(sys.argv[1]).read_text(errors="replace")
    matches = {name: pattern.findall(text) for name, pattern in PATTERNS.items()}
    counts = {name: len(values) for name, values in matches.items()}
    if any(count != 1 for count in counts.values()):
        fail(f"expected exactly one request with timing metrics; found {counts}")

    prompt_ms, prompt_tokens, prompt_tps = matches["prefill"][0]
    decode_ms, output_tokens, server_decode_tps = matches["decode"][0]
    n_output = int(output_tokens)
    decode_ms_f = float(decode_ms)
    if n_output < 2:
        fail("need at least 2 output tokens for standard decode TPS")
    if decode_ms_f <= 0:
        fail("decode time must be positive")
    server_decode_tps_f = float(server_decode_tps)
    recomputed_server_tps = n_output / (decode_ms_f / 1000.0)
    if abs(server_decode_tps_f - recomputed_server_tps) > max(0.02, recomputed_server_tps * 0.001):
        fail(
            "inconsistent decode TPS: "
            f"log={server_decode_tps_f}, recomputed={recomputed_server_tps:.6f}"
        )

    result = {
        "prompt_tokens": int(prompt_tokens),
        "prompt_ms": float(prompt_ms),
        "prompt_tps": float(prompt_tps),
        "output_tokens": n_output,
        "decode_ms": decode_ms_f,
        "server_decode_tps": server_decode_tps_f,
        "standard_decode_tps_estimate": (n_output - 1) / (decode_ms_f / 1000.0),
        "mtp_acceptance": float(matches["acceptance"][0]),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
