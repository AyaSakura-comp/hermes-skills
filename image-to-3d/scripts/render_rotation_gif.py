#!/home/chihmin/src/Pixal3D/.venv/bin/python
"""Render a 36-frame rotating-view GIF from a GLB file."""
import argparse
import math
import os
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image
import trimesh
import trimesh.transformations as tf
import trimesh.viewer  # triggers GL context init


def render_rotation_glb(glb_path: Path, output_gif: Path, resolution: int = 512, num_frames: int = 36) -> Path:
    """Load GLB, rotate it 360° in N frames, and save an animated GIF."""
    model = trimesh.load(str(glb_path), force="mesh")
    scene = trimesh.Scene(model)
    scene.camera.fov = [60, 45]

    frames: list[Image.Image] = []
    for i in range(num_frames):
        angle = math.radians(i * (360 / num_frames))
        rot_matrix = tf.rotation_matrix(angle, [0, 1, 0])
        mesh = model.copy()
        mesh.apply_transform(rot_matrix)
        rotated_scene = trimesh.Scene(mesh)
        rotated_scene.camera.fov = scene.camera.fov
        frame_bytes = trimesh.viewer.render_scene(rotated_scene, resolution=(resolution, resolution))
        frames.append(Image.open(BytesIO(frame_bytes)))

    frames[0].save(
        str(output_gif),
        save_all=True,
        append_images=frames[1:],
        duration=50,
        loop=0,
        optimize=True,
    )
    return output_gif


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("glb", type=Path, help="Path to model.glb")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output GIF path")
    parser.add_argument("--resolution", "-r", type=int, default=512)
    parser.add_argument("--frames", "-n", type=int, default=36)
    args = parser.parse_args()

    glb = args.glb.resolve()
    if not glb.is_file():
        parser.error(f"GLB not found: {glb}")

    output_gif = args.output.resolve()
    output_gif.parent.mkdir(parents=True, exist_ok=True)

    # Set headless display before importing trimesh
    os.environ.setdefault("DISPLAY", ":99")
    xvfb_auth = Path("/tmp/xvfb-run.CUriyG/Xauthority")
    if xvfb_auth.is_file():
        os.environ["XAUTHORITY"] = str(xvfb_auth)

    render_rotation_glb(glb, output_gif, args.resolution, args.frames)
    print(output_gif)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
