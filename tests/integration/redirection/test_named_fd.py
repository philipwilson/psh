"""Named file descriptors: ``{varname}>file`` (appraisal Tier 3, M2).

bash allocates a free fd >= 10, performs the redirect onto it, and stores
the number in ``varname``. The allocation is PERMANENT (not auto-closed
after the command) and parent-side for non-forked commands (builtins,
functions, exec, compound groups); ``{varname}>&-`` closes the fd named by
the variable. For a forked command (external program, subshell) the fd is
allocated in the child, so the parent's variable stays unset.

All probes are bash-pinned. Tests run psh in a subprocess because they
exercise the whole shell's fd lifecycle across commands.
"""

import subprocess
import sys

import pytest


def run_psh(script: str, cwd=None, timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True, timeout=timeout, cwd=cwd,
    )


class TestNamedFdAllocation:
    def test_exec_open_write_via_named_fd(self, tmp_path):
        f = tmp_path / 'out.txt'
        r = run_psh(f'exec {{fd}}>{f}; echo A >&$fd; echo "fd=$fd"', cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert r.stdout == 'fd=10\n'
        assert f.read_text() == 'A\n'

    def test_named_fd_is_at_least_10(self, tmp_path):
        r = run_psh('exec {fd}>/dev/null; echo "$fd"')
        assert r.returncode == 0, r.stderr
        assert int(r.stdout.strip()) >= 10

    def test_two_named_fds_allocate_sequentially(self, tmp_path):
        r = run_psh('exec {a}>/dev/null {b}>/dev/null; echo "$a $b"')
        assert r.returncode == 0, r.stderr
        a, b = (int(x) for x in r.stdout.split())
        assert a >= 10 and b >= 10 and a != b

    def test_input_named_fd(self, tmp_path):
        f = tmp_path / 'in.txt'
        f.write_text('hello\n')
        r = run_psh(f'exec {{fd}}<{f}; read line <&$fd; echo "got=$line"', cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert r.stdout == 'got=hello\n'

    def test_append_named_fd(self, tmp_path):
        f = tmp_path / 'app.txt'
        r = run_psh(f'exec {{fd}}>>{f}; echo a >&$fd; echo b >&$fd', cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert f.read_text() == 'a\nb\n'

    def test_close_named_fd(self, tmp_path):
        f = tmp_path / 'c.txt'
        # After {fd}>&- the fd is closed; the variable keeps its old value.
        r = run_psh(
            f'exec {{fd}}>{f}; echo X >&$fd; exec {{fd}}>&-; echo "v=$fd"; '
            f'echo Y >&$fd 2>/dev/null || echo closed',
            cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert r.stdout == 'v=10\nclosed\n'
        assert f.read_text() == 'X\n'

    def test_dup_named_fd(self, tmp_path):
        f = tmp_path / 'd.txt'
        r = run_psh(
            f'exec {{a}}>{f}; exec {{b}}>&$a; echo viaB >&$b; '
            f'echo "b>=10:$([ $b -ge 10 ] && echo yes)"',
            cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert r.stdout == 'b>=10:yes\n'
        assert f.read_text() == 'viaB\n'


class TestNamedFdPersistenceScope:
    def test_builtin_persists_in_parent(self):
        r = run_psh('true {fd}>/dev/null; echo "[$fd]"')
        assert r.stdout == '[10]\n', r.stderr

    def test_function_persists_in_parent(self):
        r = run_psh('f(){ :; }; f {fd}>/dev/null; echo "[$fd]"')
        assert r.stdout == '[10]\n', r.stderr

    def test_compound_group_persists_in_parent(self, tmp_path):
        f = tmp_path / 'g.txt'
        r = run_psh(f'{{ echo body >&$v; }} {{v}}>{f}; echo "v=$v"', cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert r.stdout == 'v=10\n'
        assert f.read_text() == 'body\n'

    def test_external_command_does_not_set_parent_var(self):
        # External (forked) command: the fd is allocated in the child, so the
        # parent's variable stays unset (bash).
        r = run_psh('cat </dev/null {fd}>/dev/null; echo "[$fd]"')
        assert r.stdout == '[]\n', r.stderr

    def test_subshell_does_not_set_parent_var(self):
        r = run_psh('( : ) {fd}>/dev/null; echo "[$fd]"')
        assert r.stdout == '[]\n', r.stderr


class TestNamedFdDisambiguation:
    """`{NAME}>` is a named fd only at word-start with a valid identifier and
    no spaces; otherwise normal brace group / expansion / literal."""

    def test_brace_group_unaffected(self):
        r = run_psh('{ echo grp; }')
        assert r.stdout == 'grp\n', r.stderr

    def test_brace_expansion_unaffected(self):
        r = run_psh('echo {a,b}')
        assert r.stdout == 'a b\n', r.stderr

    def test_lone_brace_word_unaffected(self):
        r = run_psh('echo {fd}')
        assert r.stdout == '{fd}\n', r.stderr

    def test_invalid_identifier_not_named_fd(self, tmp_path):
        # {1fd} is not a valid name → `{1fd}` is a literal command word and
        # `>file` a normal stdout redirect (bash: command not found).
        f = tmp_path / 'x.txt'
        r = run_psh(f'{{1fd}}>{f} 2>/dev/null; echo "v=$1fd"', cwd=tmp_path)
        assert r.stdout == 'v=fd\n', (r.stdout, r.stderr)

    def test_prefix_char_not_named_fd(self, tmp_path):
        # A char before `{` means it is not a named-fd prefix (bash: literal).
        f = tmp_path / 'p.txt'
        r = run_psh(f'echo a{{fd}}>{f}; echo "[$fd]"', cwd=tmp_path)
        assert r.stdout.endswith('[]\n'), (r.stdout, r.stderr)
        assert f.read_text() == 'a{fd}\n'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
