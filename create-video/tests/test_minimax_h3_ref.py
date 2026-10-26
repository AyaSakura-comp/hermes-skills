import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path.home() / "src/ComfyUI/scripts/minimax_h3_ref_generate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("minimax_h3_ref_generate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MiniMaxH3ReferenceGraphTests(unittest.TestCase):
    def test_graph_connects_storyboard_and_audio_to_reference_node(self):
        module = load_module()
        graph = module.graph(
            prompt="Use <Picture 1> for style and <Audio 1> for rhythm",
            width=864,
            height=480,
            seconds=3.75,
            steps=20,
            seed=42,
            prefix="video/test",
            image_filename="minimax_h3_cli/board.png",
            audio_filename="minimax_h3_cli/song.wav",
        )
        self.assertEqual(
            graph["1"]["inputs"]["unet_name"],
            "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        )
        self.assertEqual(graph["5"]["class_type"], "MiniMaxH3ReferenceToVideo")
        self.assertEqual(graph["5"]["inputs"]["ref_images.ref_image_0"], ["17", 0])
        self.assertEqual(graph["5"]["inputs"]["ref_audios.ref_audio_0"], ["18", 0])
        self.assertEqual(graph["17"]["class_type"], "LoadImage")
        self.assertEqual(graph["18"], {
            "class_type": "LoadAudio",
            "inputs": {"audio": "minimax_h3_cli/song.wav"},
        })
        self.assertEqual(graph["9"]["inputs"]["steps"], 20)

    def test_prompt_must_name_both_reference_tags(self):
        module = load_module()
        with self.assertRaisesRegex(ValueError, "<Picture 1>.*<Audio 1>"):
            module.graph(
                prompt="A dancer moves to music",
                width=864,
                height=480,
                seconds=3.75,
                steps=20,
                seed=42,
                prefix="video/test",
                image_filename="board.png",
                audio_filename="song.wav",
            )


if __name__ == "__main__":
    unittest.main()
