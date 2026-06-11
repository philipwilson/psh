"""Process substitution resource cleanup (fds and child reaping).

Pins the bash-verified lifecycle of process substitutions:
- the parent-side pipe fds are closed once the consuming command finishes;
- substitution children are reaped (no zombie accumulation across commands)
  WITHOUT the shell ever blocking on a child that outlives its command
  (bash returns immediately from `echo >(sleep 3)`);
- output correctness is unaffected (slow producers, write-side
  substitutions, function arguments, exec'd fds).

All tests run psh in a subprocess: they exercise fork/wait behavior of the
whole shell process, which must not touch the test runner's own fds.
"""

import subprocess
import sys
import time

import pytest


def run_psh(cmd: str, timeout: float = 15.0) -> subprocess.CompletedProcess:
    """Run a command in a fresh psh process."""
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', cmd],
        capture_output=True, text=True, timeout=timeout,
    )


class TestProcessSubReaping:
    """Substitution children must be reaped; no zombies across commands."""

    def test_no_zombie_accumulation_across_commands(self):
        """Several `cat <(echo x)` commands must not leave defunct children.

        Before the fix, each command leaked one zombie for the life of the
        session (bash leaves none).
        """
        # The ps probe must run INSIDE the psh session: the zombies are
        # children of the psh process and exist only while it is alive.
        cmd = (
            'cat <(echo a) >/dev/null; '
            'cat <(echo b) >/dev/null; '
            'cat <(echo c) >/dev/null; '
            'ps -axo pid,ppid,stat | awk -v me=$$ \'$2==me {print $3}\''
        )
        result = run_psh(cmd)
        assert result.returncode == 0, result.stderr
        # Remaining children are the ps/awk probe itself; none may be a
        # zombie (state starting with Z, shown as Z / Z+ / <defunct>).
        states = result.stdout.split()
        zombies = [s for s in states if s.startswith('Z')]
        assert zombies == [], (
            f"found zombie substitution children: {result.stdout!r}")

    def test_long_lived_write_substitution_does_not_block(self):
        """`echo >(sleep 2)` must return immediately, like bash.

        Before the fix, the shell blocked in waitpid() until the sleep
        finished (~2s); bash takes ~0s.

        Streams go to DEVNULL rather than capture pipes: the sleep child
        inherits the shell's stdout/stderr, so a capture pipe would not
        reach EOF until the sleep exits — that would measure pipe
        semantics (bash behaves identically), not shell blocking.
        """
        start = time.monotonic()
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', 'echo >(sleep 2) >/dev/null'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        elapsed = time.monotonic() - start
        assert result.returncode == 0
        assert elapsed < 1.5, (
            f"shell blocked {elapsed:.2f}s waiting for >(sleep 2)")

    def test_still_running_child_reaped_by_later_command(self):
        """A substitution child that outlives its command is reaped by a
        later command's cleanup poll (bash reaps opportunistically too)."""
        cmd = (
            'echo >(sleep 0.3) >/dev/null; '
            'sleep 0.5; '   # external command; child exits meanwhile
            'true; '        # any later command polls + reaps it
            'ps -axo pid,ppid,stat | awk -v me=$$ \'$2==me {print $3}\''
        )
        result = run_psh(cmd)
        assert result.returncode == 0, result.stderr
        states = result.stdout.split()
        zombies = [s for s in states if s.startswith('Z')]
        assert zombies == [], (
            f"substitution child never reaped: {result.stdout!r}")


class TestProcessSubFdRelease:
    """Parent-side pipe fds must be closed after the command finishes."""

    def test_parent_fds_released_after_commands(self):
        """After several substitution commands, the lowest free fd in the
        shell is back to 3 (each leaked parent fd would push it up).

        The probe child inherits psh's open fds (substitution fds have
        CLOEXEC cleared), so its first os.open() reveals the lowest slot
        still free in the shell. Before the fix this printed 6.
        """
        probe = (
            f'"{sys.executable}" -c '
            '"import os; print(os.open(\'/dev/null\', os.O_RDONLY))"'
        )
        cmd = (
            'cat <(echo a) >/dev/null; '
            'cat <(echo b) >/dev/null; '
            'cat <(echo c) >/dev/null; '
            + probe
        )
        result = run_psh(cmd)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == '3', (
            f"fd slots leaked: lowest free fd is {result.stdout.strip()}")


class TestProcessSubOutputCorrectness:
    """Cleanup must not close fds or kill children prematurely."""

    def test_read_substitution_basic(self):
        result = run_psh('cat <(echo hi)')
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'hi\n'

    def test_slow_producer_output_arrives(self):
        """Output written after a delay still arrives (the fd is not
        closed and the child is not killed before the consumer reads)."""
        result = run_psh('cat <(sleep 0.2; echo x)')
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'x\n'

    def test_diff_of_two_substitutions(self):
        result = run_psh('diff <(echo a) <(echo a)')
        assert result.returncode == 0, result.stderr
        assert result.stdout == ''

    def test_write_side_substitution_tee(self, tmp_path):
        """`tee >(cat > file)` — write-side substitution still works."""
        out = tmp_path / 'psub_out.txt'
        # The >(cat > file) child may finish slightly after tee; poll.
        result = run_psh(f'echo data | tee >(cat > {out}) >/dev/null')
        assert result.returncode == 0, result.stderr
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if out.exists() and out.read_text() == 'data\n':
                break
            time.sleep(0.05)
        assert out.read_text() == 'data\n'

    def test_substitution_as_function_argument(self):
        """A builtin inside the function must not close the caller's
        substitution fd (regression: the old blanket cleanup ran after
        every builtin and broke `f <(echo a)`)."""
        result = run_psh('f() { echo start; cat "$1"; }; f <(echo a)')
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'start\na\n'

    def test_compound_redirect_from_substitution(self):
        result = run_psh(
            'while read l; do echo "got:$l"; done < <(printf "1\\n2\\n")')
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'got:1\ngot:2\n'

    def test_exec_fd_from_substitution_persists(self):
        """`exec 3< <(cmd)` must keep fd 3 open past the exec command
        (the cleanup may not close a parent fd whose number became the
        permanent redirect target)."""
        result = run_psh(
            'exec 3< <(echo viafd3); read line <&3; echo "read:$line"')
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'read:viafd3\n'

    def test_exec_stdin_from_substitution_persists(self):
        result = run_psh(
            'exec < <(echo viastdin); read line; echo "read:$line"')
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'read:viastdin\n'

    def test_background_substitution_consumer(self):
        result = run_psh('cat <(echo bg) & wait $!; echo done')
        assert result.returncode == 0, result.stderr
        assert 'bg' in result.stdout and 'done' in result.stdout


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
