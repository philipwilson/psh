"""`declare -f` round-trip regression tests (reappraisal #15, D3).

The old ShellFormatter — a rotted duplicate of the maintained
FormatterVisitor — crashed on any function containing `case` and dropped
heredoc bodies, so the classic serialization idiom

    src=$(declare -f f); unset -f f; eval "$src"; f

failed (rc=127) for whole families of functions. `declare -f` / `type` /
`command -V` now all route through one chokepoint
(psh.visitor.format_function_definition); its output need not byte-match
bash's, but it must re-parse to the same program — which is what these
tests pin, per function shape.
"""

import subprocess
import sys

import pytest

ROUNDTRIP = 'src=$(declare -f f); unset -f f; eval "$src"'


def assert_roundtrip(shell, define, call):
    """Behavior of `call` must be identical before and after the round trip."""
    assert shell.run_command(define) == 0
    shell.clear_output()
    rc_direct = shell.run_command(call)
    direct_out = shell.get_stdout()
    shell.clear_output()

    assert shell.run_command(ROUNDTRIP) == 0, shell.get_stderr()
    shell.clear_output()
    rc_rt = shell.run_command(call)
    assert shell.get_stdout() == direct_out
    assert rc_rt == rc_direct


class TestDeclareFRoundTrip:
    @pytest.mark.parametrize("define, call", [
        # case arms (the D3 crash: '|'.join over CasePattern objects)
        ('f() { case $1 in a|b) echo AB;; *.txt) echo TXT;; *) echo O;; esac; }',
         'f a; f x.txt; f zz'),
        # heredoc bodies (the D3 drop)
        ('f() { x=world; cat <<EOF\nhello $x\nEOF\n}', 'f'),
        ("f() { cat <<'EOF'\nliteral $x `cmd` \\n\nEOF\n}", 'f'),
        ('f() { cat <<-EOF\n\tindented\n\tEOF\n}', 'f'),
        ('f() { cat <<EOF | tr a-z A-Z\nhello\nEOF\n}', 'f'),
        # heredoc inside a case arm
        ('f() { case $1 in h) cat <<EOF\narm body\nEOF\n;; *) echo no;; esac; }',
         'f h; f q'),
        # ANSI-C quoting must keep its $'...' form
        ("f() { printf '%s\\n' $'a\\tb'; }", 'f'),
        # escapes inside double quotes
        ('f() { v=V; echo "a\\$b \\"q\\" $v"; }', 'f'),
        # nested function definition (old formatter emitted a body sans braces)
        ('f() { g() { echo inner-g; }; g; }', 'f; g'),
        # `function` keyword form round-trips through the POSIX form
        ('function f { echo kw; }', 'f'),
        # control-flow nesting
        ('f() { for i in 1 2; do if [ "$i" = 1 ]; then echo one; '
         'else echo two; fi; done; }', 'f'),
        ('f() { [[ -n $1 && $1 == a* ]] && echo yes || echo no; }',
         'f abc; f zz'),
        ('f() { return 42; }', 'f; echo rc=$?'),
    ])
    def test_shape_survives_roundtrip(self, captured_shell, define, call):
        assert_roundtrip(captured_shell, define, call)

    def test_definition_attached_redirect(self, temp_dir):
        """f() { ...; } > file — the redirect fires at each call, and must
        survive the round trip (the old formatter dropped it). Subprocess:
        the attached redirect rebinds the shell's own stdout, which the
        in-process capture fixtures can't observe faithfully."""
        import os

        import psh as psh_pkg

        # Pin the subprocess to the same psh tree the test imports (an
        # editable install elsewhere would otherwise win over a worktree).
        repo_root = os.path.dirname(os.path.dirname(psh_pkg.__file__))
        env = {**os.environ, 'PYTHONPATH': repo_root}
        script = f'f() {{ echo hi; }} > rtout.txt; {ROUNDTRIP}; f'
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', script],
            cwd=temp_dir, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ''
        with open(os.path.join(temp_dir, 'rtout.txt')) as fh:
            assert fh.read() == 'hi\n'

    def test_multiple_names(self, captured_shell):
        shell = captured_shell
        shell.run_command('f() { echo one; }; g() { case $1 in a) echo A;; esac; }')
        assert shell.run_command(
            'src=$(declare -f f g); unset -f f g; eval "$src"') == 0
        shell.clear_output()
        assert shell.run_command('f; g a') == 0
        assert shell.get_stdout() == 'one\nA\n'
        assert shell.get_stderr() == ''


class TestFunctionPrintersDoNotCrash:
    """type / command -V / declare -F share the declare -f formatter path
    (the D3 crash hit all of them)."""

    DEFINE = 'f() { case $1 in a) echo A;; esac; cat <<EOF\nhd\nEOF\n}'

    def test_type(self, captured_shell):
        captured_shell.run_command(self.DEFINE)
        captured_shell.clear_output()
        assert captured_shell.run_command('type f') == 0
        out = captured_shell.get_stdout()
        assert 'f is a function' in out
        assert 'case' in out
        assert '\nhd\nEOF' in out
        assert captured_shell.get_stderr() == ''

    def test_command_v(self, captured_shell):
        captured_shell.run_command(self.DEFINE)
        captured_shell.clear_output()
        assert captured_shell.run_command('command -V f') == 0
        assert 'f is a function' in captured_shell.get_stdout()
        assert captured_shell.get_stderr() == ''

    def test_declare_capital_f_names_only(self, captured_shell):
        captured_shell.run_command(self.DEFINE)
        captured_shell.clear_output()
        assert captured_shell.run_command('declare -F') == 0
        assert captured_shell.get_stdout() == 'declare -f f\n'
