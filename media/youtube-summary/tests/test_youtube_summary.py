import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).parents[1] / "scripts" / "youtube-summary.py"
spec = importlib.util.spec_from_file_location("youtube_summary", SCRIPT)
youtube_summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(youtube_summary)


class DownloadTests(unittest.TestCase):
    def test_finds_the_actual_downloaded_video_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "video.mp4").touch()

            self.assertEqual(
                youtube_summary.find_downloaded_video(directory),
                str(Path(directory, "video.mp4")),
            )


class WhisperBackendTests(unittest.TestCase):
    def test_whisper_command_uses_breeze_compatible_worker(self):
        command = youtube_summary.build_whisper_command(
            "/tmp/audio.ogg", "/tmp/audio.json",
            python_path="/opt/rocm-python/bin/python",
        )

        self.assertEqual(command[:2], ["/opt/rocm-python/bin/python", str(SCRIPT)])
        self.assertIn("--whisper-worker", command)
        self.assertEqual(command[command.index("--worker-audio") + 1], "/tmp/audio.ogg")
        self.assertEqual(command[command.index("--worker-output") + 1], "/tmp/audio.json")

    def test_whisper_environment_includes_strix_halo_rocm_settings(self):
        environment = youtube_summary.whisper_environment({"PATH": "/usr/bin"})

        self.assertEqual(environment["HSA_OVERRIDE_GFX_VERSION"], "11.5.1")
        self.assertEqual(environment["PYTORCH_HIP_ALLOC_CONF"], "expandable_segments:True")
        self.assertEqual(environment["TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL"], "1")

    def test_normalize_segments_discards_empty_text_and_repairs_reversed_timestamps(self):
        segments = youtube_summary.normalize_whisper_segments([
            {"timestamp": [1.0, 2.0], "text": " hello "},
            {"timestamp": [3.0, 2.0], "text": " broken "},
            {"timestamp": [4.0, 5.0], "text": "   "},
        ])

        self.assertEqual(segments, [(1.0, 2.0, "hello"), (3.0, 3.01, "broken")])


class ParseArgsTests(unittest.TestCase):
    def test_defaults_to_whisper_turbo_for_non_taigi_video(self):
        options = youtube_summary.parse_args(["https://youtu.be/example", "English video"])

        self.assertEqual(options.url, "https://youtu.be/example")
        self.assertEqual(options.title, "English video")
        self.assertEqual(options.asr, "whisper")

    def test_allows_breeze_for_taigi_video(self):
        options = youtube_summary.parse_args(["--asr", "breeze", "https://youtu.be/example"])

        self.assertEqual(options.asr, "breeze")
        self.assertEqual(options.url, "https://youtu.be/example")


if __name__ == "__main__":
    unittest.main()
