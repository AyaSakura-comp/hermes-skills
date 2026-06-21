import importlib.util
import unittest
from argparse import Namespace
from pathlib import Path

SCRIPT = Path('/home/chihmin/.pi/agent/skills/create-image/scripts/create_image.py')


def load_module():
    spec = importlib.util.spec_from_file_location('create_image', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DaemonRoutingTests(unittest.TestCase):
    def test_uses_daemon_for_default_9b_request(self):
        mod = load_module()
        args = Namespace(no_daemon=False)
        self.assertTrue(mod.should_try_daemon(args, model_label='9b-kv'))

    def test_skips_daemon_for_fast_preview_4b_request(self):
        mod = load_module()
        args = Namespace(no_daemon=False)
        self.assertFalse(mod.should_try_daemon(args, model_label='4b'))

    def test_skips_daemon_when_disabled(self):
        mod = load_module()
        args = Namespace(no_daemon=True)
        self.assertFalse(mod.should_try_daemon(args, model_label='9b-kv'))

    def test_builds_daemon_payload_with_image_and_native_flags(self):
        mod = load_module()
        args = Namespace(
            prompt='hello', image='/tmp/ref.png', seed=123, steps=4, guidance_scale=1.0,
            native_1080p=True, no_auto_lora=False, lora_scale=0.8,
            out_dir='/tmp/out', prefix='abc', output_size=None,
        )
        payload = mod.build_daemon_payload(args, mode='edit-9b-kv-native-1080p')
        self.assertEqual(payload['prompt'], 'hello')
        self.assertEqual(payload['image'], '/tmp/ref.png')
        self.assertTrue(payload['native_1080p'])
        self.assertEqual(payload['mode'], 'edit-9b-kv-native-1080p')


if __name__ == '__main__':
    unittest.main()
