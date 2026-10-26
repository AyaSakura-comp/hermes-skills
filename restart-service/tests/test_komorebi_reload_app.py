import os
from pathlib import Path
import subprocess

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/restart-komorebi.sh'


def test_reload_app_preserves_npu_profile_and_never_restarts_models(tmp_path):
    log = tmp_path / 'calls'
    commands = {
        'systemctl': 'printf "systemctl %s\\n" "$*" >> "$CALL_LOG"\nexit 0\n',
        'docker': 'printf "docker %s\\n" "$*" >> "$CALL_LOG"\nexit 0\n',
        'curl': 'exit 0\n',
        'sudo': 'echo "Forbidden sudo" >&2\nexit 99\n',
    }
    for name, body in commands.items():
        path = tmp_path / name
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755)
    env = dict(os.environ, PATH=f'{tmp_path}:{os.environ["PATH"]}', CALL_LOG=str(log))
    env.pop('KOMOREBI_UNIT', None)
    run = subprocess.run(['bash', str(SCRIPT), 'reload-app'], env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    calls = log.read_text()
    assert 'komorebi-npu-only.compose.yaml up -d --no-build --no-deps app' in calls
    assert 'systemctl restart' not in calls and 'systemctl start' not in calls and 'systemctl stop' not in calls
