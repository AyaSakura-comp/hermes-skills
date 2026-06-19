#!/usr/bin/env python3
import argparse
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from ltx_core.model.video_vae import TilingConfig
from ltx_pipelines.utils.blocks import ImageConditioner, VideoDecoder
from ltx_pipelines.utils.media_io import load_image_and_preprocess


def tensor_to_pil(frame: torch.Tensor) -> Image.Image:
    # LTX decoder chunks are usually [F,H,W,C] or [H,W,C], in [0,1] or [-1,1].
    x = frame.detach().float().cpu()
    if x.ndim == 5:  # B,C,F,H,W
        x = x[0, :, 0].permute(1, 2, 0)
    elif x.ndim == 4:
        # F,H,W,C or C,F,H,W
        if x.shape[-1] == 3:
            x = x[0]
        elif x.shape[0] == 3:
            x = x[:, 0].permute(1, 2, 0)
        else:
            raise ValueError(f"Unsupported 4D frame shape: {tuple(x.shape)}")
    elif x.ndim == 3:
        if x.shape[0] == 3 and x.shape[-1] != 3:
            x = x.permute(1, 2, 0)
    else:
        raise ValueError(f"Unsupported frame shape: {tuple(x.shape)}")
    if x.min() < -0.1:
        x = (x + 1.0) / 2.0
    x = x.clamp(0, 1)
    return Image.fromarray((x.numpy() * 255.0 + 0.5).astype(np.uint8))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--checkpoint', required=True)
    p.add_argument('--image', required=True)
    p.add_argument('--height', type=int, required=True)
    p.add_argument('--width', type=int, required=True)
    p.add_argument('--crf', type=int, default=33)
    p.add_argument('--output', required=True)
    args = p.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    dtype = torch.bfloat16
    image_conditioner = ImageConditioner(args.checkpoint, dtype, device)
    decoder = VideoDecoder(args.checkpoint, dtype, device)

    def encode(enc):
        image = load_image_and_preprocess(args.image, args.height, args.width, dtype, device, crf=args.crf)
        return enc(image)

    latent = image_conditioner(encode)
    frames = list(decoder(latent, TilingConfig.default(), torch.Generator(device=device).manual_seed(0)))
    if not frames:
        raise RuntimeError('decoder returned no frames')
    out = tensor_to_pil(frames[0])
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out.save(args.output)
    print(f'saved {args.output} shape={out.size} latent={tuple(latent.shape)}')


if __name__ == '__main__':
    main()
