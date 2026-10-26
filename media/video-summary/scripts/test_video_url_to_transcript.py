import importlib.util
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("video-url-to-transcript.py")
spec = importlib.util.spec_from_file_location("video_url_to_transcript", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GlobalWhisperQueueTests(unittest.TestCase):
    def test_dispatches_jobs_fifo_and_waits_until_done(self):
        handled = []

        def handler(job):
            time.sleep(0.01)
            handled.append(job)

        jobs = module.GlobalWhisperQueue(handler, maxsize=2)
        jobs.start()
        for job in ("video-a/chunk-0", "video-b/chunk-0", "video-a/chunk-1"):
            jobs.submit(job)
        jobs.close()

        self.assertEqual(
            handled,
            ["video-a/chunk-0", "video-b/chunk-0", "video-a/chunk-1"],
        )

    def test_runs_only_one_handler_at_a_time(self):
        active = 0
        peak = 0

        def handler(_job):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            time.sleep(0.01)
            active -= 1

        jobs = module.GlobalWhisperQueue(handler)
        jobs.start()
        for index in range(4):
            jobs.submit(index)
        jobs.close()

        self.assertEqual(peak, 1)


if __name__ == "__main__":
    unittest.main()
