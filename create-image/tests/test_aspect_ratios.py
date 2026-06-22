import importlib.util
import unittest
from pathlib import Path

CREATE_IMAGE_SCRIPT = Path('/home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py')
ANIMA_SCRIPT = Path('/home/chihmin/.pi/agent/skills/create-image/scripts/anima.py')


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AspectRatioTests(unittest.TestCase):
    def test_anime_defaults_to_2x3_upscaled_portrait(self):
        mod = load_module(ANIMA_SCRIPT, 'anima')
        self.assertEqual(
            mod.resolve_anime_sizes(None, native=False),
            (768, 1152, 1184, 1776, '2:3'),
        )

    def test_anime_can_select_3x2_upscaled_landscape(self):
        mod = load_module(ANIMA_SCRIPT, 'anima')
        self.assertEqual(
            mod.resolve_anime_sizes('3:2', native=False),
            (1152, 768, 1776, 1184, '3:2'),
        )

    def test_flux_can_select_2x3_with_9b_equivalent_pixel_bucket(self):
        mod = load_module(CREATE_IMAGE_SCRIPT, 'create_image')
        self.assertEqual(
            mod.resolve_flux_sizes('9b-kv', '2:3', native=False),
            (832, 1248, 1184, 1776, '2:3'),
        )

    def test_flux_keeps_legacy_16x9_bucket_until_benchmarked(self):
        mod = load_module(CREATE_IMAGE_SCRIPT, 'create_image')
        self.assertEqual(
            mod.resolve_flux_sizes('9b-kv', None, native=False),
            (1360, 768, 1920, 1080, '16:9'),
        )


if __name__ == '__main__':
    unittest.main()
