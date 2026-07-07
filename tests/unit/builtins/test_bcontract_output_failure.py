"""Output-failure propagation (builtins contracts cluster, finding 12).

A builtin whose write fails must reflect that in its exit status. echo/printf/
declare-p already propagate a bad/closed descriptor (rc 1); the gap was the
zsh-style `print` builtin, which reported `-u99` but returned 0.

Subprocess-based (bad/closed fds must not touch the test runner's own fds).
"""
import subprocess
import sys

PSH = [sys.executable, "-m", "psh"]


def run(script):
    p = subprocess.run(PSH + ["-c", script], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=30)
    return p.returncode, p.stdout, p.stderr


class TestPrintOutputFailure:
    def test_print_bad_fd_returns_1(self):
        rc, out, err = run('print -u99 hi; echo "rc=$?"')
        assert "rc=1" in out
        assert "Bad file descriptor" in err

    def test_print_f_bad_fd_returns_1(self):
        rc, out, err = run('print -f "%s\\n" -u99 hi; echo "rc=$?"')
        assert "rc=1" in out

    def test_print_closed_fd_returns_1(self):
        rc, out, err = run('print hi >&-; echo "rc=$?"')
        assert "rc=1" in out

    def test_print_good_fd_still_zero(self):
        rc, out, err = run('print -u2 hi; echo "rc=$?"')
        assert out == "rc=0\n"
        assert "hi" in err

    def test_print_normal_unaffected(self):
        rc, out, err = run('print hello; echo "rc=$?"')
        assert out == "hello\nrc=0\n"


class TestCoreBuiltinOutputFailure:
    """These already worked; guard them so the write-all change keeps them."""

    def test_echo_bad_fd(self):
        rc, out, err = run('echo hi >&99; echo "rc=$?"')
        assert out == "rc=1\n"

    def test_printf_closed_fd(self):
        rc, out, err = run('printf "%s\\n" hi >&-; echo "rc=$?"')
        assert out == "rc=1\n"

    def test_declare_p_bad_fd(self):
        rc, out, err = run('x=1; declare -p x >&99; echo "rc=$?"')
        assert out == "rc=1\n"
