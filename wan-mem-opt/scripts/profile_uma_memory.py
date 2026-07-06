#!/usr/bin/env python3
"""Profile real UMA/system RAM pressure via /proc/meminfo while running a command.

Primary metric: baseline MemAvailable - minimum MemAvailable.
Also records process RSS and ROCm GTT/VRAM attribution when rocm-smi exists.
"""
import csv
import os
import re
import subprocess
import sys
import time

if len(sys.argv) < 4:
    print("usage: profile_uma_memory.py OUT_CSV PROCESS_PATTERN -- command [args...]", file=sys.stderr)
    sys.exit(2)

out = sys.argv[1]
patterns = sys.argv[2].split('|')
cmd = sys.argv[3:]
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

def meminfo():
    data = {}
    with open('/proc/meminfo', 'r', encoding='utf-8') as f:
        for line in f:
            k, v = line.split(':', 1)
            data[k] = int(v.strip().split()[0]) * 1024
    return data

def rss_sum():
    total = 0
    hits = []
    try:
        ps = subprocess.check_output(['ps', '-eo', 'pid=,rss=,args='], text=True)
    except Exception:
        return 0, ''
    for line in ps.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid, rss_kb, args = parts[0], int(parts[1]), parts[2]
        if any(p in args for p in patterns):
            total += rss_kb * 1024
            hits.append(f'{pid}:{rss_kb}KB:{args[:90]}')
    return total, '; '.join(hits[:8])

def rocm_mem():
    rocm = '/opt/rocm/bin/rocm-smi'
    if not os.path.exists(rocm):
        return 0, 0
    try:
        text = subprocess.check_output([rocm, '--showmeminfo', 'all'], text=True, stderr=subprocess.STDOUT, timeout=10)
    except Exception:
        return 0, 0
    def get(name):
        m = re.search(rf'{name} Total Used Memory \(B\):\s*(\d+)', text)
        return int(m.group(1)) if m else 0
    return get('GTT'), get('VRAM')

base = meminfo()
start = time.time()
proc = subprocess.Popen(cmd, stdout=open(out + '.stdout', 'w'), stderr=open(out + '.stderr', 'w'), preexec_fn=os.setsid)
rows = []
while True:
    mi = meminfo()
    rss, hits = rss_sum()
    gtt, vram = rocm_mem()
    rows.append([
        f'{time.time() - start:.3f}',
        mi.get('MemTotal', 0), mi.get('MemFree', 0), mi.get('MemAvailable', 0),
        mi.get('Buffers', 0), mi.get('Cached', 0), mi.get('SReclaimable', 0), mi.get('Shmem', 0),
        rss, gtt, vram, hits,
    ])
    if proc.poll() is not None:
        break
    time.sleep(1)
rc = proc.wait()
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['t_s','MemTotal_B','MemFree_B','MemAvailable_B','Buffers_B','Cached_B','SReclaimable_B','Shmem_B','rss_sum_B','rocm_gtt_used_B','rocm_vram_used_B','process_hits'])
    w.writerows(rows)
min_avail = min(int(r[3]) for r in rows) if rows else base.get('MemAvailable', 0)
max_rss = max(int(r[8]) for r in rows) if rows else 0
max_gtt = max(int(r[9]) for r in rows) if rows else 0
max_vram = max(int(r[10]) for r in rows) if rows else 0
summary = (
    f'exit={rc}\n'
    f'baseline_MemAvailable_GiB={base.get("MemAvailable", 0)/1024**3:.3f}\n'
    f'min_MemAvailable_GiB={min_avail/1024**3:.3f}\n'
    f'MemAvailable_drop_GiB={(base.get("MemAvailable", 0)-min_avail)/1024**3:.3f}\n'
    f'peak_rss_GiB={max_rss/1024**3:.3f}\n'
    f'peak_rocm_gtt_GiB={max_gtt/1024**3:.3f}\n'
    f'peak_rocm_vram_GiB={max_vram/1024**3:.3f}\n'
)
with open(out + '.summary', 'w', encoding='utf-8') as f:
    f.write(summary)
print(summary)
sys.exit(rc)
