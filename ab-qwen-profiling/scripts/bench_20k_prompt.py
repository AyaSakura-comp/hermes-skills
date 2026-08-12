#!/usr/bin/env python3
import json, math, re, statistics, sys, threading, time
from pathlib import Path
import requests

mode=sys.argv[1]
if mode == 'calibrate':
    port=int(sys.argv[2]); model=sys.argv[3]; outfile=Path(sys.argv[4])
    # Varied technical prose, repeated only to provide enough source material.
    paths=[Path('/home/chihmin/atomic-llama-cpp-turboquant/README.md'),Path('/home/chihmin/atomic-llama-cpp-turboquant/MTP.md'),Path('/home/chihmin/atomic-llama-cpp-turboquant/docs/speculative.md'),Path('/home/chihmin/atomic-llama-cpp-turboquant/docs/build.md')]
    corpus='\n\n'.join(p.read_text(errors='replace') for p in paths)
    corpus=(corpus+'\n\n')*4
    base=f'http://127.0.0.1:{port}'
    toks=requests.post(base+'/tokenize',json={'content':corpus,'add_special':False},timeout=120).json()['tokens']
    n=19970
    for _ in range(4):
        content=requests.post(base+'/detokenize',json={'tokens':toks[:n]},timeout=120).json()['content']
        payload={'model':model,'messages':[{'role':'user','content':content}],'max_tokens':1,'temperature':0,'cache_prompt':False}
        d=requests.post(base+'/v1/chat/completions',json=payload,timeout=300).json()
        actual=d['usage']['prompt_tokens']; print(f'calibration model={model} content_tokens={n} prompt_tokens={actual}',flush=True)
        if actual == 20000: break
        n += 20000-actual
    if actual != 20000: raise SystemExit(f'failed to calibrate: {actual}')
    outfile.write_text(content)
    print(json.dumps({'model':model,'content_tokens':n,'prompt_tokens':actual,'chars':len(content),'file':str(outfile)}))

elif mode == 'run':
    label=sys.argv[2];port=int(sys.argv[3]);model=sys.argv[4];prompt_file=Path(sys.argv[5]);log=Path(sys.argv[6]);outfile=Path(sys.argv[7]); pid=int(sys.argv[8]); ntok=int(sys.argv[9]) if len(sys.argv)>9 else 1024
    prompt=prompt_file.read_text(); logoff=log.stat().st_size if log.exists() else 0
    samples=[];stop=threading.Event();start_ref=[None];first_ref=[None]
    def ticks():
        s=Path(f'/proc/{pid}/stat').read_text().split();return int(s[13])+int(s[14])
    def sampler():
        hz=100;last_t=time.monotonic();last_ticks=ticks()
        while not stop.wait(.2):
            now=time.monotonic();tk=ticks()
            try:
                samples.append({'t':now,'power':int(Path('/sys/class/hwmon/hwmon9/power1_input').read_text())/1e6,'gpu':int(Path('/sys/class/drm/card1/device/gpu_busy_percent').read_text()),'cpu_cores':(tk-last_ticks)/hz/(now-last_t)})
            except:pass
            last_t,last_ticks=now,tk
    th=threading.Thread(target=sampler);th.start()
    payload={'model':model,'messages':[{'role':'user','content':prompt}],'max_tokens':ntok,'temperature':0,'seed':42,'cache_prompt':False,'stream':True,'stream_options':{'include_usage':True}}
    start=time.monotonic();start_ref[0]=start;first=None;usage={};finish=None
    with requests.post(f'http://127.0.0.1:{port}/v1/chat/completions',json=payload,stream=True,timeout=(30,600)) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line or line==b'data: [DONE]':continue
            d=json.loads(line.removeprefix(b'data: '))
            if d.get('usage'):usage=d['usage']
            for c in d.get('choices',[]):
                x=c.get('delta') or {}
                if first is None and (x.get('content') or x.get('reasoning_content')):first=time.monotonic();first_ref[0]=first
                if c.get('finish_reason'):finish=c['finish_reason']
    end=time.monotonic();stop.set();th.join();time.sleep(1)
    text=''
    if log.exists():
        with log.open('rb') as f:f.seek(min(logoff,log.stat().st_size));text=f.read().decode(errors='replace')
    def lm(pat):
        m=re.findall(pat,text,re.M);return m[-1] if m else None
    pe=lm(r'prompt eval time =\s+([0-9.]+) ms /\s+(\d+) tokens.*?([0-9.]+) tokens per second')
    ev=lm(r'(?<!prompt )eval time =\s+([0-9.]+) ms /\s+(\d+) tokens.*?([0-9.]+) tokens per second')
    ac=lm(r'draft acceptance rate =\s+([0-9.]+).*?([0-9]+) accepted /\s*([0-9]+) generated')
    pre=[x for x in samples if first and x['t']<=first];dec=[x for x in samples if first and x['t']>first]
    def seg(xs):
        return {'samples':len(xs),'power_avg_w':statistics.mean(x['power'] for x in xs),'power_max_w':max(x['power'] for x in xs),'gpu_avg':statistics.mean(x['gpu'] for x in xs),'cpu_cores_avg':statistics.mean(x['cpu_cores'] for x in xs)} if xs else None
    result={'label':label,'model':model,'prompt_tokens':usage.get('prompt_tokens'),'completion_tokens':usage.get('completion_tokens'),'finish_reason':finish,'ttft_s':first-start,'elapsed_s':end-start,'external_decode_tps':usage.get('completion_tokens',0)/(end-first),'server_prefill_ms':float(pe[0]) if pe else None,'server_prefill_tokens':int(pe[1]) if pe else None,'server_prefill_tps':float(pe[2]) if pe else None,'server_decode_ms':float(ev[0]) if ev else None,'server_decode_tokens':int(ev[1]) if ev else None,'server_decode_tps':float(ev[2]) if ev else None,'mtp_acceptance':float(ac[0]) if ac else None,'mtp_accepted':int(ac[1]) if ac else None,'mtp_generated':int(ac[2]) if ac else None,'prefill':seg(pre),'decode':seg(dec)}
    outfile.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
else: raise SystemExit('mode')
