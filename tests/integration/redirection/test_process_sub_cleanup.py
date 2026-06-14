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

import glob
import os
import subprocess
import sys
import tempfile
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


class TestProcessSubRepeatedUse:
    """Repeated substitution use (a loop) must not accumulate fds or
    zombies — the per-command cleanup runs every iteration, not just once.
    """

    def test_no_fd_leak_across_loop_iterations(self):
        """20 iterations of `cat <(echo i)` then probe the lowest free fd.

        Each leaked parent-side pipe fd would push the lowest free slot
        up; after a clean run it is back to 3 regardless of iteration
        count. This is the loop analogue of the 3-command fd test below.
        """
        probe = (
            f'"{sys.executable}" -c '
            '"import os; print(os.open(\'/dev/null\', os.O_RDONLY))"'
        )
        cmd = (
            'i=0; while [ $i -lt 20 ]; do '
            '  cat <(echo $i) >/dev/null; '
            '  i=$((i+1)); '
            'done; '
            + probe
        )
        result = run_psh(cmd)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == '3', (
            f"fd slots leaked across loop: lowest free fd is "
            f"{result.stdout.strip()}")

    def test_no_zombie_accumulation_across_loop(self):
        """20 read-substitution iterations leave no defunct children."""
        cmd = (
            'i=0; while [ $i -lt 20 ]; do '
            '  cat <(echo $i) >/dev/null; '
            '  i=$((i+1)); '
            'done; '
            'ps -axo pid,ppid,stat | awk -v me=$$ \'$2==me {print $3}\''
        )
        result = run_psh(cmd)
        assert result.returncode == 0, result.stderr
        zombies = [s for s in result.stdout.split() if s.startswith('Z')]
        assert zombies == [], (
            f"zombies accumulated across loop: {result.stdout!r}")

    def test_write_side_substitution_child_reaped(self, tmp_path):
        """A `>(...)` write-side substitution child is reaped after the
        command, not left defunct (the cleanup reaps both read- and
        write-side children)."""
        out = tmp_path / 'wside.txt'
        cmd = (
            f'echo data | tee >(cat > {out}) >/dev/null; '
            'sleep 0.2; true; '   # let the write child finish; a later
                                  # command polls + reaps it
            'ps -axo pid,ppid,stat | awk -v me=$$ \'$2==me {print $3}\''
        )
        result = run_psh(cmd, timeout=20)
        assert result.returncode == 0, result.stderr
        zombies = [s for s in result.stdout.split() if s.startswith('Z')]
        assert zombies == [], (
            f"write-side substitution child not reaped: {result.stdout!r}")


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

    def test_parent_fd_released_when_later_redirect_fails(self):
        """A process-substitution fd must be closed even if a later redirect
        in the same command fails and rolls back the redirection set."""
        probe = (
            f'"{sys.executable}" -c '
            '"import os; print(os.open(\'/dev/null\', os.O_RDONLY))"'
        )
        cmd = (
            'cat < <(echo data) > /nonexistent_zz/out; '
            + probe
        )
        result = run_psh(cmd)
        assert result.stdout.strip() == '3', (
            f"fd leaked after failed redirect: lowest free fd is "
            f"{result.stdout.strip()!r}; stderr={result.stderr!r}")

    def test_permanent_procsub_fd_released_when_later_redirect_fails(self):
        """The permanent exec path must also release proc-sub fds on failure."""
        probe = (
            f'"{sys.executable}" -c '
            '"import os; print(os.open(\'/dev/null\', os.O_RDONLY))"'
        )
        cmd = (
            'exec < <(echo data) > /nonexistent_zz/out; '
            + probe
        )
        result = run_psh(cmd)
        assert result.stdout.strip() == '3', (
            f"fd leaked after failed exec redirect: lowest free fd is "
            f"{result.stdout.strip()!r}; stderr={result.stderr!r}")


def _psub_fifo_dirs() -> set:
    """The set of write-side `>(...)` FIFO temp dirs currently on disk."""
    return set(glob.glob(os.path.join(tempfile.gettempdir(), 'psh-psub-*')))


class TestWriteSideFifoFilesystemLeak:
    """Write-side `>(...)` FIFO temp dirs must not orphan on disk.

    A write-side `>(cmd)` creates a `$TMPDIR/psh-psub-XXXX/pipe` named FIFO.
    Inside a PIPELINE the consuming command (e.g. `tee`) runs in a forked
    pipeline child that execs the external binary, so the parent's
    process_sub_scope() finally never runs there — before the fix the FIFO
    dir orphaned, one per invocation. The substitution child now unlinks its
    own FIFO dir once it has opened the read end (robust to os._exit/exec).
    """

    def test_pipeline_write_substitution_no_fifo_dir_leak(self):
        """`echo data | tee >(...) >/dev/null` must leave no psh-psub dir."""
        before = _psub_fifo_dirs()
        for _ in range(3):
            result = run_psh('echo data | tee >(cat >/dev/null) >/dev/null')
            assert result.returncode == 0, result.stderr
        # Give any still-shutting-down child a moment to unlink.
        time.sleep(0.3)
        leaked = _psub_fifo_dirs() - before
        assert leaked == set(), f"pipeline >() leaked FIFO dirs: {leaked!r}"

    def test_non_pipeline_write_substitution_no_fifo_dir_leak(self):
        """The non-pipeline form must also leave no psh-psub dir."""
        before = _psub_fifo_dirs()
        for _ in range(3):
            result = run_psh('tee >(cat >/dev/null) </dev/null')
            assert result.returncode == 0, result.stderr
        time.sleep(0.3)
        leaked = _psub_fifo_dirs() - before
        assert leaked == set(), f"non-pipeline >() leaked FIFO dirs: {leaked!r}"

    def test_multiple_write_substitutions_no_fifo_dir_leak(self):
        """Two `>(...)` in one pipeline command leave no psh-psub dir."""
        before = _psub_fifo_dirs()
        result = run_psh(
            'echo data | tee >(cat >/dev/null) >(cat >/dev/null) >/dev/null')
        assert result.returncode == 0, result.stderr
        time.sleep(0.3)
        leaked = _psub_fifo_dirs() - before
        assert leaked == set(), f"multi >() leaked FIFO dirs: {leaked!r}"

    def test_pipeline_write_substitution_still_delivers_data(self, tmp_path):
        """The FIFO cleanup must not break delivery to the consumer."""
        out = tmp_path / 'got.txt'
        result = run_psh(f'echo hi | tee >(cat > {out}) >/dev/null')
        assert result.returncode == 0, result.stderr
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if out.exists() and out.read_text() == 'hi\n':
                break
            time.sleep(0.05)
        assert out.read_text() == 'hi\n'


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
