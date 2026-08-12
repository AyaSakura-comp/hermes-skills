import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SCRIPT = Path('/home/chihmin/.pi/agent/skills/create-image/scripts/anima_lllite.py')


def load_module():
    spec = importlib.util.spec_from_file_location('anima_lllite', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AnimaLLLiteTests(unittest.TestCase):
    def test_workflow_applies_lllite_before_sampling(self):
        mod = load_module()
        workflow = mod.build_lllite_workflow(
            prompt='same rabbit girl in a new scene',
            image_name='character-control.png',
            gen_w=1280,
            gen_h=720,
            seed=123,
            steps=30,
            strength=0.4,
            end_percent=0.5,
            loras=[('style.safetensors', 1.0)],
            trigger='anime, ',
        )

        self.assertEqual(workflow['6']['class_type'], 'ModelPatchLoader')
        self.assertEqual(
            workflow['6']['inputs']['name'],
            'anima-lllite-any-test-like-v2.safetensors',
        )
        self.assertEqual(workflow['8']['class_type'], 'AnimaLLLiteApply')
        self.assertEqual(workflow['8']['inputs']['image'], ['7', 0])
        self.assertEqual(workflow['8']['inputs']['strength'], 0.4)
        self.assertEqual(workflow['8']['inputs']['end_percent'], 0.5)
        self.assertEqual(workflow['12']['inputs']['model'], ['8', 0])
        self.assertEqual(workflow['12']['inputs']['steps'], 30)

    def test_control_image_is_grayscale_and_matches_generation_canvas(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'reference.png'
            Image.new('RGB', (1200, 800), (255, 0, 0)).save(path)

            control = mod.prepare_control_image(path, 1280, 720)

        self.assertEqual(control.mode, 'RGB')
        self.assertEqual(control.size, (1280, 720))
        red, green, blue = control.getpixel((640, 360))
        self.assertEqual(red, green)
        self.assertEqual(green, blue)

    def test_cli_defaults_match_verified_storyboard_settings(self):
        mod = load_module()
        args = mod.parse_args(['a storyboard shot', '--reference', '/tmp/ref.png'])

        self.assertEqual(args.steps, 30)
        self.assertEqual(args.strength, 0.4)
        self.assertEqual(args.end_percent, 0.5)
        self.assertEqual(args.aspect_ratio, '16:9')
        self.assertIsNone(args.output_size)

    def test_explicit_output_size_sets_exact_generation_canvas(self):
        mod = load_module()

        sizes = mod.resolve_output_sizes('864x480', '16:9', native=False)

        self.assertEqual(sizes, (864, 480, 864, 480, '864:480'))


if __name__ == '__main__':
    unittest.main()
