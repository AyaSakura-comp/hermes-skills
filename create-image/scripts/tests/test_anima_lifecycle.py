import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import anima


class _Process:
    def __init__(self):
        self.terminated = False
        self.killed = False
        self.waited = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout):
        self.waited = True

    def kill(self):
        self.killed = True


class ComfyLifecycleTests(unittest.TestCase):
    def test_on_demand_comfy_is_returned_as_owned_and_stopped_after_generation(self):
        process = _Process()
        with patch.object(anima, "_server_up", side_effect=[False, True]), \
             patch.object(anima.subprocess, "Popen", return_value=process):
            ready, owned_process = anima.ensure_comfy(wait_seconds=1)

        self.assertTrue(ready)
        self.assertIs(owned_process, process)
        anima.stop_comfy(owned_process)
        self.assertTrue(process.terminated)
        self.assertTrue(process.waited)

    def test_existing_comfy_is_not_claimed_or_stopped(self):
        with patch.object(anima, "_server_up", return_value=True):
            ready, owned_process = anima.ensure_comfy()

        self.assertTrue(ready)
        self.assertIsNone(owned_process)
        anima.stop_comfy(owned_process)


if __name__ == "__main__":
    unittest.main()
