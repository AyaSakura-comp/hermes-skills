#!/home/chihmin/src/Pixal3D/.venv/bin/python
"""Render an STL directly as a smoothly rotating GIF (10 seconds by default)."""
import argparse
import math
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image


def rotation_schedule(duration: float, fps: int, seed: int) -> list[tuple[float, float, float]]:
    """Return deterministic, loopable-looking XYZ Euler rotations without a duplicate end frame."""
    count = max(1, round(duration * fps))
    rng = np.random.default_rng(seed)
    pitch_phase, roll_phase = rng.uniform(0, 2 * math.pi, 2)
    pitch_amp = rng.uniform(math.radians(12), math.radians(28))
    roll_amp = rng.uniform(math.radians(4), math.radians(12))
    return [
        (
            pitch_amp * math.sin(2 * math.pi * i / count + pitch_phase),
            2 * math.pi * i / count,
            roll_amp * math.sin(4 * math.pi * i / count + roll_phase),
        )
        for i in range(count)
    ]


def resolve_render_source(path: Path) -> Path:
    """Use a sibling GLB when available because STL has no UVs or texture data."""
    sibling = path.with_suffix(".glb")
    return sibling if path.suffix.lower() == ".stl" and sibling.is_file() else path


def load_model(path: Path):
    loaded = trimesh.load(path, force="mesh", process=True)
    if not isinstance(loaded, trimesh.Trimesh) or loaded.is_empty or len(loaded.faces) == 0:
        raise ValueError(f"model contains no renderable triangles: {path}")
    vertices = np.asarray(loaded.vertices, dtype=np.float32).copy()
    vertices -= (vertices.min(0) + vertices.max(0)) / 2
    span = float(np.ptp(vertices, axis=0).max())
    if span <= 1e-9:
        raise ValueError(f"model has zero extent: {path}")
    vertices /= span
    uv = texture = None
    visual = loaded.visual
    if getattr(visual, "kind", None) == "texture" and getattr(visual, "uv", None) is not None:
        material = visual.material
        image = getattr(material, "baseColorTexture", None) or getattr(material, "image", None)
        if image is not None:
            uv = np.asarray(visual.uv, dtype=np.float32).copy()
            texture = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    return (vertices, np.asarray(loaded.faces, dtype=np.int32).copy(),
            np.asarray(loaded.vertex_normals, dtype=np.float32).copy(), uv, texture)


def load_stl(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    vertices, faces, normals, _, _ = load_model(path)
    return vertices, faces, normals


def rotation_matrix(x: float, y: float, z: float) -> np.ndarray:
    sx, cx, sy, cy, sz, cz = math.sin(x), math.cos(x), math.sin(y), math.cos(y), math.sin(z), math.cos(z)
    rx = np.array(((1, 0, 0), (0, cx, -sx), (0, sx, cx)), np.float32)
    ry = np.array(((cy, 0, sy), (0, 1, 0), (-sy, 0, cy)), np.float32)
    rz = np.array(((cz, -sz, 0), (sz, cz, 0), (0, 0, 1)), np.float32)
    return rz @ ry @ rx


def frame_durations(duration: float, count: int) -> list[int]:
    total_ms = round(duration * 1000)
    boundaries = [round(i * total_ms / count) for i in range(count + 1)]
    return [boundaries[i + 1] - boundaries[i] for i in range(count)]


def studio_shading_numpy(normals: np.ndarray) -> np.ndarray:
    """Soft studio light that preserves albedo instead of visibly dimming textures."""
    key = np.array([-.35, .45, .82], np.float32); key /= np.linalg.norm(key)
    fill = np.array([.55, -.35, .68], np.float32); fill /= np.linalg.norm(fill)
    key_light = np.maximum(normals @ key, 0)
    fill_light = np.maximum(normals @ fill, 0)
    top = .5 + .5 * np.clip(normals[:, 2], -1, 1)
    return .86 + .10 * key_light + .07 * fill_light + .04 * top


def render(vertices: np.ndarray, faces: np.ndarray, normals: np.ndarray,
           schedule: list[tuple[float, float, float]], size: int,
           uv: np.ndarray | None = None, texture: np.ndarray | None = None) -> list[Image.Image]:
    import torch
    import nvdiffrast.torch as dr

    device = torch.device("cuda")
    verts = torch.from_numpy(vertices).to(device)
    nrms = torch.from_numpy(normals).to(device)
    tris = torch.from_numpy(faces).to(device)
    context = dr.RasterizeCudaContext(device=device)
    key = torch.nn.functional.normalize(torch.tensor([-.35, .45, .82], device=device), dim=0)
    fill = torch.nn.functional.normalize(torch.tensor([.55, -.35, .68], device=device), dim=0)
    base_color = torch.tensor([.38, .68, .88], device=device).view(1, 1, 1, 3)
    uv_tensor = torch.from_numpy(uv).to(device) if uv is not None else None
    texture_tensor = torch.from_numpy(texture).to(device).flip(0)[None] if texture is not None else None
    bg = torch.tensor([.965, .972, .98], device=device).view(1, 1, 1, 3)
    images = []
    for angles in schedule:
        matrix = torch.from_numpy(rotation_matrix(*angles)).to(device)
        points = verts @ matrix.T
        rotated_normals = nrms @ matrix.T
        clip = torch.cat((points[:, :2] / .72, points[:, 2:3], torch.ones_like(points[:, :1])), dim=1)[None]
        rast, _ = dr.rasterize(context, clip, tris, (size, size))
        interpolated, _ = dr.interpolate(rotated_normals[None].contiguous(), rast, tris)
        interpolated = torch.nn.functional.normalize(interpolated, dim=-1)
        key_light = torch.clamp((interpolated * key).sum(-1, keepdim=True), 0, 1)
        fill_light = torch.clamp((interpolated * fill).sum(-1, keepdim=True), 0, 1)
        hemisphere = .5 + .5 * torch.clamp(interpolated[..., 2:3], -1, 1)
        # Texture values are already display-referred sRGB. Keep the albedo near
        # its authored brightness and use lights only for gentle shape cues.
        shade = .86 + .10 * key_light + .07 * fill_light + .04 * hemisphere
        if uv_tensor is not None and texture_tensor is not None:
            sampled_uv, _ = dr.interpolate(uv_tensor[None].contiguous(), rast, tris)
            base = dr.texture(texture_tensor.contiguous(), sampled_uv, filter_mode="linear")
        else:
            base = base_color
        rgb = torch.where(rast[..., 3:4] > 0, base * shade, bg).clamp(0, 1)[0].flip(0)
        images.append(Image.fromarray((rgb.cpu().numpy() * 255).astype(np.uint8), "RGB"))
    return images


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stl", type=Path, help="input STL path")
    parser.add_argument("--output", type=Path, help="output GIF (default: beside STL)")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--seed", type=int, default=42, help="controls the secondary pitch/roll motion")
    args = parser.parse_args()
    source = args.stl.expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".stl":
        parser.error(f"input must be an existing STL: {source}")
    if not 0 < args.duration <= 60 or not 1 <= args.fps <= 30 or not 128 <= args.size <= 1024:
        parser.error("duration must be 0–60s, fps 1–30, and size 128–1024")
    output = (args.output or source.with_name(f"{source.stem}-rotation.gif")).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    render_source = resolve_render_source(source)
    vertices, faces, normals, uv, texture = load_model(render_source)
    if render_source != source:
        print(f"Loading texture from sibling GLB: {render_source}")
    elif texture is None:
        print("No texture data found; rendering with an evenly lit material")
    schedule = rotation_schedule(args.duration, args.fps, args.seed)
    frames = render(vertices, faces, normals, schedule, args.size, uv, texture)
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=frame_durations(args.duration, len(frames)), loop=0, optimize=False, disposal=2)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
