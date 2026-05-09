---
name: ollama-amd-igpu-troubleshooting
description: Diagnose and resolve memory issues when running LLMs on AMD iGPUs (APUs) via Ollama/ROCm.
---

# Ollama AMD iGPU (APU) Troubleshooting

This skill covers the diagnostic workflow for when Ollama fails to load or run models on AMD internal graphics (e.g., Radeon 780M, 8060S, Ryzen AI series), specifically addressing the confusion between "Virtual VRAM" and "Physical RAM".

## Trigger Conditions
- User reports Ollama crashes or "won't run" a specific model.
- System uses an AMD APU/iGPU (check via `lspci | grep VGA`).
- Discrepancy between reported VRAM in `rocm-smi` and system crashes.

## Diagnostic Steps

### 1. Identify Model & Physical RAM
Compare the model's required size against the actual physical memory.
```bash
ollama list
free -h
```
*   **Pitfall:** A "35B Q8" model requires ~38GB. If `free -h` shows only 32GB total RAM, it will fail regardless of what the GPU reports.

### 2. Inspect GPU Memory Reporting
```bash
# rocm-smi is NOT in PATH — use full path
/opt/rocm/bin/rocm-smi --showmeminfo vram gtt
# Or for ROCm 7.x:
/opt/rocm-7.2.2/bin/rocm-smi --showmeminfo vram gtt
```
*   **Knowledge:** AMD iGPUs often report a "Virtual VRAM" or "GTT" (Graphics Translation Table) limit that is significantly higher than physical RAM (e.g., 96GB or 220GB). This is a *theoretical addressing limit*, not physical storage.

### 3. Verify OOM (Out of Memory) Events
Check if the Linux kernel killed the process.
```bash
journalctl -u ollama --no-pager -n 100
# OR check the log directly
tail -n 100 ~/.ollama/logs/server.log
```
*   **Look for:** `ollama.service: A process of this unit has been killed by the OOM killer.`

## Solutions

### A. Recommended: Lower Quantization
The most stable fix is to use a model version that fits within **Physical RAM - 8GB** (to leave room for the OS and context).
- Suggest changing from `Q8_0` to `Q4_K_M` or `Q5_K_M`.
- Command: `ollama run <model>:<tag>-q4_k_m`

### B. Forced: Large Swap File
If the user insists on running a model larger than RAM, use a massive Swap file on an SSD.
```bash
sudo swapoff -a
sudo dd if=/dev/zero of=/swapfile bs=1G count=80 status=progress
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```
*   **Warning:** Performance will be extremely slow (tokens per minute instead of per second) due to SSD latency vs. RAM.

### C. BIOS UMA Frame Buffer Configuration (AMD APU / Strix)
If OOM occurs despite sufficient total system RAM (e.g., 128GB RAM but Ollama crashes loading a 38GB model), the problem is usually memory fragmentation caused by incorrect BIOS settings, NOT GRUB limits.

**1. The Fix (BIOS):**
Instruct the user to reboot into BIOS/UEFI and change the **UMA Frame Buffer Size** (or UMA Allocation).
- **Correct Setting:** `Auto` or a very low fixed value (e.g., `512M` or `1G`).
- **Why:** On modern AMD APUs, setting a high fixed UMA buffer (like 16G or 32G) permanently "carves out" that memory at boot. This creates unaddressable gaps and fragmentation, preventing the `amdgpu` driver and ROCm from dynamically allocating large, contiguous blocks of system RAM via GTT for LLM weights.

**2. ⚠️ DANGER: Do NOT use `amdgpu.ttm.pages_limit` in GRUB:**
Past attempts to fix this by adding `amdgpu.ttm.pages_limit=33554432 amdgpu.page_pool_size=33554432` to GRUB resulted in catastrophic failure on a 128GB system:
- The kernel artificially constrained the system to only see 30GB of RAM.
- `rocm-smi` broke completely.
- XDNA SVA bind failed (`amdxdna_drm_open: SVA bind device failed, ret -95`).
- **Never attempt to manually hardcode TTM page limits in GRUB for high-memory APU systems.** Ensure `GRUB_CMDLINE_LINUX_DEFAULT` only contains standard options like `amd_iommu=on iommu=pt`.

### D. Environment Variables
Ensure ROCm is properly detected.
```bash
# Force specific GFX version if not detected
export HSA_OVERRIDE_GFX_VERSION=11.0.0
```

## Verification
- Run `cat /proc/cmdline` to verify GRUB parameters actually applied (look for `amdgpu.ttm.pages_limit`).
- Run `free -h` during model load to see RAM/Swap usage spikes.
- Check `/opt/rocm*/bin/rocm-smi` to confirm layers are offloaded to the iGPU.
