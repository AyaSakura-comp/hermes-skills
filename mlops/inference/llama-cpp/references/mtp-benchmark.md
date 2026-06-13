# llama.cpp MTP (Multi-Token Prediction) Benchmark Guide

MTP models embed an auxiliary smaller model (e.g., 3B "A3B") as a speculative draft head within the main model file. `llama-server` with MTP enabled parallelizes prefill between the large model and the draft head, and accelerates decode via speculative token acceptance.

## Key Concepts

| Metric | Meaning |
|--------|---------|
| `ttft_ms` | Time to first token — prefill duration |
| `prefill_tps` | Input tokens / TTFT — speed of processing the prompt |
| `decode_tps` | Output tokens / decode duration — raw token generation speed |
| `effective_tps` | Total tokens / total time — reflects MTP speedup |
| `overall_tps` | (input + output) / total time — same as effective_tps |

**MTP behavior:**
- MTP parallelizes prefill: the large model and auxiliary draft head build KV cache concurrently. This means prefill TPS can be dramatically higher for short prompts than for long prompts (which hit different batching paths).
- MTP speedup is reflected in `effective_tps`, NOT raw `decode_tps`. Raw decode TPS often stays similar to non-MTP because the draft tokens must be verified by the main model.
- KV cache from previous runs **interferes** with repeat benchmarking — restart the server between benchmark categories.

## Enabling MTP

```bash
# CORRECT flag:
./llama-server -m model.gguf --spec-type mtp

# WRONG flags (will NOT enable MTP):
# --mctx-max-tokens     (wrong — this is for mctx, not MTP)
# --cont-ctx-len        (wrong)
```

## Benchmark Script

Use a **hybrid streaming/non-streaming** approach to capture both TTFT and accurate token counts:

```python
import requests, time, json

API = "http://localhost:8080"

def bench_mtp(prompt, max_tokens=256):
    """Benchmark MTP model via hybrid streaming/non-streaming."""
    messages = [{"role": "user", "content": prompt}]

    # Step 1: Streaming — capture TTFT and prefill timing
    start = time.time()
    ttft = None
    first_tokens = []
    with requests.post(f"{API}/v1/chat/completions", json={
        "model": "local", "messages": messages,
        "max_tokens": max_tokens, "stream": True
    }, stream=True, timeout=300) as r:
        for line in r.iter_lines():
            if line:
                chunk = json.loads(line.decode("utf-8").replace("data: ", ""))
                if ttft is None:
                    ttft = (time.time() - start) * 1000  # ms
                    first_tokens.append(chunk)
    elapsed_total = time.time() - start

    # Step 2: Non-streaming — get exact token counts from usage
    r2 = requests.post(f"{API}/v1/chat/completions", json={
        "model": "local", "messages": messages,
        "max_tokens": max_tokens, "stream": False
    }, timeout=300)
    usage = r2.json().get("usage", {})
    content = r2.json()["choices"][0]["message"]["content"]
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    # Calculate metrics
    ttft_s = ttft / 1000
    prefill_tps = prompt_tokens / ttft_s if ttft_s > 0 else 0
    decode_tps = completion_tokens / (elapsed_total - ttft_s) if elapsed_total > ttft_s else 0
    total_tokens = prompt_tokens + completion_tokens
    effective_tps = total_tokens / elapsed_total if elapsed_total > 0 else 0

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "ttft_ms": round(ttft, 0),
        "prefill_tps": round(prefill_tps, 1),
        "decode_tps": round(decode_tps, 1),
        "effective_tps": round(effective_tps, 1),
        "content": content[:100]
    }

# Run benchmarks
short_result = bench_mtp("Explain quantum computing in one paragraph.", 256)
long_result = bench_mtp("Write a comprehensive technical essay about machine learning, including history, architectures, applications, and future directions. Cover transformers, CNNs, RNNs, GANs, and diffusion models.", 256)

for label, r in [("Short", short_result), ("Long", long_result)]:
    print(f"\n=== {label} ===")
    for k, v in r.items():
        if k != "content":
            print(f"  {k}: {v}")
```

## MTP Benchmark Results: Qwen3.6-35B-A3B (AMD Radeon 8060S iGPU)

| Category | Prefill Tokens | Decode Tokens | TTFT | PreFill TPS | Decode TPS | Effective TPS |
|----------|---------------|---------------|------|-------------|------------|---------------|
| Short Text (46 tok) | 46 | 194 | 2.08s | ~68 | ~123 | 106 |
| Long Prompt (~4k tok) | 3,966 | 475 | 11.2s | ~1,180 | ~61 | 397 |

**Observations:**
1. **Decode TPS:** ~123 (short) → ~61 (long). MTP helps on short responses where the draft model's speculations are more likely to be accepted. Long sequences degrade draft acceptance rate.
2. **Prefill TPS:** 68 (short) → 1,180 (long). The massive jump is due to MTP batch prefill — the large model and 3B draft head process KV cache construction in parallel for long sequences.
3. **Effective TPS:** ~106 (short), ~397 (long). This is where MTP speedup is visible.

## Important Caveats

1. **Model capability:** Qwen3.6-35B-A3B-UD is **text-only**. The "A3B" refers to the auxiliary 3B speculative head, NOT audio or vision. Vision+image prompts return empty responses.
2. **KV cache interference:** Repeated benchmarks on the same server session produce `TTFT=0` or inflated prefill TPS. Always restart the server between benchmark categories.
3. **API limitations:** The OpenAI-compatible `/v1/chat/completions` response omits `prompt_eval_duration` and `eval_duration`. Streaming is required for TTFT measurement.
4. **Draft model quality matters:** The speedup from MTP depends on how well the auxiliary model's predictions match the main model's output. For highly technical or creative text, draft acceptance rates drop.
5. **VRAM consumption:** MTP models load the full model file (e.g., 22.6 GB for Qwen3.6-35B-UD-Q4_K_M). The auxiliary head is embedded — no separate model file needed.

## Server Launch Command

```bash
./llama-server \
    -m /path/to/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf \
    --spec-type mtp \
    --host 0.0.0.0 \
    --port 8080 \
    -c 8192 \
    -ngl 99 \
    -np 4
```

## Comparing MTP vs Non-MTP

To measure the actual benefit of MTP, run the same benchmark script against both configurations:

```bash
# Non-MTP baseline
./llama-server -m model.gguf -ngl 99 -c 8192

# MTP enabled
./llama-server -m model.gguf --spec-type mtp -ngl 99 -c 8192
```

Key comparison: focus on `effective_tps` improvement, not `decode_tps`.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `TTFT=0` or near-zero | KV cache hit from previous run | Restart server |
| Vision/image returns empty string | Model is text-only (A3B ≠ vision) | Use a vision-capable model |
| Decode TPS doesn't improve with MTP | Draft model acceptance rate too low | Acceptable — MTP benefits are in effective_tps |
| Connection refused on port 8080 | Server process died | Check PID with `ps aux | grep llama-server` |
| Out of memory | Model too large for VRAM | Lower quant (Q5→Q8) or reduce context |

## References

- llama.cpp MTP: https://github.com/ggml-org/llama.cpp
- Qwen3.6-35B-A3B-GGUF: https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF
- Model local-app page: https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF?local-app=llama.cpp
