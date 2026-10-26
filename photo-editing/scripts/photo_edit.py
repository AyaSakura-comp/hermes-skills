#!/usr/bin/env python3
"""Qwen Image 2.1 photo-edit CLI using the existing ComfyUI API."""
import argparse
import json
import mimetypes
import time
import urllib.request
import urllib.error
import urllib.parse
import uuid
from pathlib import Path


def node(kind, **inputs):
    return {'class_type':kind,'inputs':inputs}


def workflow(image, prompt, seed, steps, resolution):
    return {
        '1':node('UNETLoader',unet_name='qwen_image_2.1_int8_convrot.safetensors',weight_dtype='default'),
        '2':node('CLIPLoader',clip_name='qwen3vl_8b_int8_convrot.safetensors',type='qwen_image',device='default'),
        '3':node('VAELoader',vae_name='qwen_image_2.1_vae_bf16.safetensors'),
        '4':node('TextEncodeQwenImage21',**{'clip':['2',0],'vae':['3',0],'prompt':prompt,'negative_prompt':'','resolution':resolution,'images.image_1':['9',0]}),
        '6':node('KSampler',model=['1',0],positive=['4',0],negative=['4',1],latent_image=['4',2],seed=seed,steps=steps,cfg=1.0,sampler_name='euler',scheduler='simple',denoise=1.0),
        '7':node('VAEDecode',samples=['6',0],vae=['3',0]),
        '8':node('SaveImage',images=['7',0],filename_prefix='photo_edit_'+uuid.uuid4().hex),
        '9':node('LoadImage',image=image),
    }


def submitted(response):
    if not response.get('prompt_id') or response.get('error') or response.get('node_errors'):
        raise RuntimeError('Submission rejected: '+json.dumps(response))
    return response['prompt_id']


def completed_images(entry):
    status=entry.get('status',{})
    if status.get('status_str')=='error':
        raise RuntimeError('ComfyUI execution failed: '+json.dumps(status))
    return [im for out in entry.get('outputs',{}).values() for im in out.get('images',[])]


def request(url, data=None, content_type=None):
    headers={'Content-Type':content_type} if content_type else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=headers),timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'HTTP {e.code}: '+e.read().decode(errors='replace')) from e


def prepare_image(source, target, max_side):
    from PIL import Image, ImageOps
    with Image.open(source) as raw:
        im=ImageOps.exif_transpose(raw)
        original=im.size
        if max_side > 0 and max(im.size) > max_side:
            scale=max_side/max(im.size)
            size=tuple(max(1,round(v*scale)) for v in im.size)
            im=im.resize(size,Image.Resampling.LANCZOS)
        im.save(target,format='PNG')
        return {'source_size':list(original),'prepared_size':list(im.size),'prepared_path':str(target)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('prompt');p.add_argument('--image',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seed',type=int,default=2003);p.add_argument('--steps',type=int,default=25)
    p.add_argument('--resolution',type=int,default=0);p.add_argument('--timeout',type=float,default=600)
    p.add_argument('--max-side',type=int,default=1080,help='Pre-resize longest edge without upscaling; 0 keeps original size')
    p.add_argument('--comfy-url',default='http://127.0.0.1:8188')
    p.add_argument('--resume',help='Poll an already submitted prompt ID; does not resubmit')
    a=p.parse_args();base=a.comfy_url.rstrip('/')
    if a.output.resolve()==a.image.resolve():p.error('Output must not overwrite the reference image')
    if not a.image.is_file():p.error('Input image does not exist')
    if a.steps<1 or a.resolution<0 or a.timeout<=0 or a.max_side<0:p.error('Invalid steps/resolution/timeout/max-side')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    meta={}
    if a.resume:
        pid=a.resume
        job_path=a.output.with_suffix('.job.json')
        if job_path.exists():meta=json.loads(job_path.read_text())
    else:
        info=json.loads(request(base+'/object_info'))
        needed={v['class_type'] for v in workflow('x',a.prompt,a.seed,a.steps,a.resolution).values()}
        if needed-set(info):raise RuntimeError('Missing nodes: '+str(sorted(needed-set(info))))
        boundary='pi'+uuid.uuid4().hex
        prepared=a.output.with_suffix('.input.png')
        if prepared.resolve()==a.image.resolve():p.error('Prepared image would overwrite reference')
        meta=prepare_image(a.image,prepared,a.max_side)
        print('Prepared '+json.dumps(meta),flush=True)
        name=uuid.uuid4().hex+'.png'
        mime='image/png'
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: {mime}\r\n\r\n'.encode()+prepared.read_bytes()+f'\r\n--{boundary}--\r\n'.encode())
        up=json.loads(request(base+'/upload/image',body,'multipart/form-data; boundary='+boundary))
        image='/'.join(x for x in [up.get('subfolder',''),up['name']] if x)
        wf=workflow(image,a.prompt,a.seed,a.steps,a.resolution)
        a.output.with_suffix('.workflow.json').write_text(json.dumps(wf,indent=2))
        pid=submitted(json.loads(request(base+'/prompt',json.dumps({'prompt':wf,'client_id':uuid.uuid4().hex}).encode(),'application/json')))
    a.output.with_suffix('.job.json').write_text(json.dumps({**meta,'prompt_id':pid,'source':str(a.image),'seed':a.seed,'steps':a.steps,'max_side':a.max_side}))
    print('Submitted '+pid,flush=True)
    deadline=time.monotonic()+a.timeout
    while time.monotonic()<deadline:
        hist=json.loads(request(base+'/history/'+pid))
        images=completed_images(hist.get(pid,{}))
        if images:
            im=images[0]
            query=urllib.parse.urlencode({'filename':im['filename'],'subfolder':im.get('subfolder',''),'type':im.get('type','output')})
            a.output.write_bytes(request(base+'/view?'+query))
            from PIL import Image
            with Image.open(a.output) as result: output_size=list(result.size)
            summary={**meta,'final_path':str(a.output.resolve()),'prompt_id':pid,'output_size':output_size,'elapsed_seconds':round(time.monotonic()-started,2)}
            a.output.with_suffix('.result.json').write_text(json.dumps(summary,indent=2))
            print(json.dumps(summary),flush=True)
            return
        time.sleep(2)
    raise TimeoutError(f'No completed output after {a.timeout}s; job {pid} may still be running. Use --resume {pid}; do not submit duplicate jobs.')


if __name__=='__main__':main()
