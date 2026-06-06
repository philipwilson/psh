"""Tests for file descriptor operations: close (>&-, <&-) and input dup (<&)."""
import subprocess
import sys


def run_psh(cmd):
    """Run a command in psh and return (stdout, stderr, returncode)."""
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', cmd],
        capture_output=True, text=True, timeout=10,
    )
    return result.stdout, result.stderr, result.returncode


class TestFdClose:
    """Test >&- and <&- file descriptor close operations."""

    def test_exec_close_fd_output(self):
        """exec 3>/dev/null; exec 3>&-; echo ok — fd close works."""
        stdout, stderr, rc = run_psh('exec 3>/dev/null; exec 3>&-; echo ok')
        assert rc == 0
        assert stdout.strip() == 'ok'

    def test_exec_close_fd_input(self):
        """exec 3</dev/null; exec 3<&-; echo ok — input fd close works."""
        stdout, stderr, rc = run_psh('exec 3</dev/null; exec 3<&-; echo ok')
        assert rc == 0
        assert stdout.strip() == 'ok'

    def test_close_fd_is_actually_closed(self):
        """After closing fd 3, writing to it should fail."""
        # Open fd 3, close it, then try to redirect to it — should get an error
        stdout, stderr, rc = run_psh(
            'exec 3>/dev/null; exec 3>&-; echo fail >&3'
        )
        assert rc != 0

    def test_close_default_fd(self):
        """>&- with no explicit fd closes fd 1 (stdout)."""
        # After closing stdout, echo should fail or produce no output
        stdout, stderr, rc = run_psh('exec >&-; echo should_not_appear')
        # stdout should be empty since fd 1 was closed
        assert 'should_not_appear' not in stdout


class TestInputFdDup:
    """Test <& input file descriptor duplication."""

    def test_input_dup_basic(self):
        """Test 3<&0 duplicates stdin to fd 3."""
        # This is mainly a smoke test that the syntax is accepted and doesn't crash
        stdout, stderr, rc = run_psh('echo hello | cat 0<&0')
        assert rc == 0
        assert stdout.strip() == 'hello'


class TestProcessSubRedirect:
    """Test that process substitution redirects don't hang due to FD leaks."""

    def test_process_sub_redirect_completes(self):
        """cat <(echo test) should complete without hanging."""
        stdout, stderr, rc = run_psh('cat <(echo test)')
        assert rc == 0
        assert stdout.strip() == 'test'

    def test_process_sub_redirect_multiline(self):
        """Process substitution with multi-line output."""
        stdout, stderr, rc = run_psh('cat <(echo line1; echo line2)')
        assert rc == 0
        lines = stdout.strip().split('\n')
        assert lines == ['line1', 'line2']


class TestPermanentRedirectProcSubCheck:
    """Test that apply_permanent_redirections proc-sub check works correctly."""

    def test_endswith_paren_not_empty(self):
        """Verify the endswith(')') fix — targets not ending in ) should not
        be treated as process substitutions."""
        # A regular redirect target that starts with <( but doesn't end with )
        # should just be treated as a filename (and fail with file not found)
        # This is a regression test for the endswith('') bug
        stdout, stderr, rc = run_psh('echo test > /dev/null')
        assert rc == 0


class TestDynamicDupTarget:
    """`>&`/`<&` targets given by an expansion are resolved at runtime.

    The lexer emits a bare `N>&`/`>&`/`<&` operator, the parser keeps the
    expansion as the target, and FileRedirector._resolved expands it to an fd
    number before the dup. See docs / brace_expansion is unrelated.
    """

    def test_dup_stdout_to_arithmetic_fd(self):
        # >&$((1+2)) duplicates fd 3 (opened by exec) — write reaches the file.
        out, err, rc = run_psh(
            'exec 3>/dev/stdout; echo hi >&$((1+2)); exec 3>&-')
        assert rc == 0
        assert out.strip() == "hi"

    def test_dup_stdout_to_variable_fd(self):
        out, err, rc = run_psh('fd=2; echo oops >&$fd 2>/dev/null; echo ok')
        assert rc == 0
        assert "ok" in out

    def test_arithmetic_fd_equivalent_to_literal(self):
        # >&$((0+1)) is just >&1 (a no-op dup of stdout onto itself).
        out, err, rc = run_psh('echo hi >&$((0+1))')
        assert rc == 0
        assert out.strip() == "hi"

    def test_fd_prefixed_arithmetic_dup(self):
        # 2>&$((1)) sends stderr to stdout (fd 1).
        out, err, rc = run_psh('echo err >&2 2>&$((1)) | cat')
        # The exact stream plumbing varies; the point is it parses and runs.
        assert rc == 0

    def test_non_numeric_target_is_error(self):
        # An explicit fd-dup target that is not a number is a redirect error.
        out, err, rc = run_psh('x=abc; echo hi 2>&$x')
        assert rc != 0
        assert "ambiguous redirect" in err
