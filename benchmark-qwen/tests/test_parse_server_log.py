#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PARSER = SKILL / "scripts" / "parse_server_log.py"


class ParseServerLogTests(unittest.TestCase):
    def run_parser(self, text: str):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "server.log"
            log.write_text(text)
            return subprocess.run(
                [sys.executable, str(PARSER), str(log)],
                text=True,
                capture_output=True,
            )

    def test_parses_llama_server_prefill_decode_and_standard_tps(self):
        result = self.run_parser(
            """prompt eval time = 29886.10 ms / 28219 tokens (1.06 ms per token, 944.22 tokens per second)
       eval time = 19449.49 ms / 1186 tokens (19.64 ms per token, 60.98 tokens per second)
draft acceptance rate = 0.95948 (227 accepted / 242 generated)
"""
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["prompt_tokens"], 28219)
        self.assertEqual(data["prompt_tps"], 944.22)
        self.assertEqual(data["output_tokens"], 1186)
        self.assertEqual(data["server_decode_tps"], 60.98)
        self.assertAlmostEqual(data["standard_decode_tps_estimate"], 60.9270474, places=6)
        self.assertEqual(data["mtp_acceptance"], 0.95948)

    def test_rejects_agent_tool_followup_with_multiple_server_requests(self):
        request = """prompt eval time = 100.00 ms / 100 tokens (1.00 ms per token, 1000.00 tokens per second)
       eval time = 20.00 ms / 2 tokens (10.00 ms per token, 100.00 tokens per second)
draft acceptance rate = 1.00000 (1 accepted / 1 generated)
"""
        result = self.run_parser(request + request)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one request", result.stderr)

    def test_rejects_zero_or_one_output_token_for_decode_tps(self):
        result = self.run_parser(
            """prompt eval time = 100.00 ms / 100 tokens (1.00 ms per token, 1000.00 tokens per second)
       eval time = 10.00 ms / 1 tokens (10.00 ms per token, 100.00 tokens per second)
draft acceptance rate = 1.00000 (0 accepted / 0 generated)
"""
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at least 2 output tokens", result.stderr)

    def test_rejects_inconsistent_server_decode_tps(self):
        result = self.run_parser(
            """prompt eval time = 100.00 ms / 100 tokens (1.00 ms per token, 1000.00 tokens per second)
       eval time = 20.00 ms / 2 tokens (10.00 ms per token, 999.00 tokens per second)
draft acceptance rate = 1.00000 (1 accepted / 1 generated)
"""
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inconsistent decode TPS", result.stderr)


if __name__ == "__main__":
    unittest.main()
