"""Background function execution: `f &` forks a subshell (bash) — v0.268.0.

Previously psh rejected this with "functions cannot be run in background".
Forked children write at the fd level, so these run psh in a subprocess.
"""

import subprocess
import sys


def run_psh(script):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True, timeout=15)


class TestBackgroundFunctions:
    def test_function_runs_in_background(self):
        r = run_psh('f() { echo in_func; }; f & wait; echo done')
        assert r.returncode == 0
        assert r.stdout == "in_func\ndone\n"
        assert "cannot be run in background" not in r.stderr

    def test_background_function_is_asynchronous(self):
        r = run_psh('f() { sleep 0.1; echo bg_done; }; f & echo fg_first; wait')
        assert r.stdout == "fg_first\nbg_done\n"

    def test_background_function_receives_arguments(self):
        r = run_psh('f() { echo "args:$@"; }; f a b & wait')
        assert r.stdout == "args:a b\n"

    def test_background_function_exit_status_via_wait(self):
        r = run_psh('f() { return 7; }; f & wait %1; echo "rc=$?"')
        assert r.stdout == "rc=7\n"

    def test_background_function_state_is_isolated(self):
        # The function runs in a subshell: parent variables are untouched
        r = run_psh('x=1; f() { x=2; }; f & wait; echo "x=$x"')
        assert r.stdout == "x=1\n"

    def test_background_function_with_redirect(self, tmp_path):
        out = tmp_path / "bg_out.txt"
        r = run_psh(f'f() {{ echo redirected; }}; f > {out} & wait')
        assert r.returncode == 0
        assert out.read_text() == "redirected\n"
