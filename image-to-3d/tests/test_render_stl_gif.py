import importlib.util
from pathlib import Path

import numpy as np
import trimesh


SCRIPT = Path(__file__).parents[1] / "scripts" / "render_stl_gif.py"


def load_module():
    spec = importlib.util.spec_from_file_location("render_stl_gif", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rotation_schedule_fills_requested_duration_without_duplicate_loop_frame():
    module = load_module()

    schedule = module.rotation_schedule(duration=10.0, fps=12, seed=7)

    assert len(schedule) == 120
    assert schedule[0] != schedule[-1]
    assert all(len(rotation) == 3 for rotation in schedule)


def test_prefers_sibling_glb_to_load_texture_for_stl(tmp_path):
    module = load_module()
    stl = tmp_path / "model.stl"
    glb = tmp_path / "model.glb"
    stl.touch()
    glb.touch()

    assert module.resolve_render_source(stl) == glb


def test_keeps_stl_when_no_sibling_glb_exists(tmp_path):
    module = load_module()
    stl = tmp_path / "model.stl"
    stl.touch()

    assert module.resolve_render_source(stl) == stl


def test_studio_lighting_preserves_texture_brightness_from_every_direction():
    module = load_module()
    normals = np.array([
        [1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]
    ], dtype=np.float32)

    shade = module.studio_shading_numpy(normals)

    assert shade.min() >= 0.86
    assert shade.max() <= 1.10
    assert np.ptp(shade) <= 0.22


def test_load_stl_centers_and_scales_longest_axis(tmp_path):
    module = load_module()
    source = tmp_path / "box.stl"
    trimesh.creation.box(extents=(2.0, 4.0, 8.0)).export(source)

    vertices, faces, normals = module.load_stl(source)

    assert vertices.dtype == np.float32
    assert faces.dtype == np.int32
    assert normals.dtype == np.float32
    assert np.allclose((vertices.min(0) + vertices.max(0)) / 2, 0, atol=1e-6)
    assert np.isclose(np.ptp(vertices, axis=0).max(), 1.0)
    assert len(normals) == len(vertices)
