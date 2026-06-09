"""
Tests for the shared Builtin base helpers (v0.259.0).

write()/write_line() replace the in_forked_child/os.write dance that was
copied into each builtin; parse_flags() replaces ad-hoc option loops.
"""

import subprocess
import sys

from psh.builtins.base import Builtin


class _Fake(Builtin):
    name = "fake"

    @property
    def synopsis(self):
        return "fake [-ab] [-d delim] [args...]"

    def execute(self, args, shell):
        return 0


class _Shell:
    """Minimal stand-in with state + stderr for parse_flags errors."""
    class _State:
        in_forked_child = False
    state = _State()

    def __init__(self):
        import io
        self.stderr = io.StringIO()
        self.stdout = io.StringIO()


class TestParseFlags:
    def setup_method(self):
        self.b = _Fake()
        self.sh = _Shell()

    def test_bool_flags_and_operands(self):
        opts, rest = self.b.parse_flags(['fake', '-a', 'x', 'y'], self.sh, flags='ab')
        assert opts == {'a': True, 'b': False}
        assert rest == ['x', 'y']

    def test_clustered_flags(self):
        opts, rest = self.b.parse_flags(['fake', '-ab', 'x'], self.sh, flags='ab')
        assert opts['a'] and opts['b']
        assert rest == ['x']

    def test_value_flag_separate(self):
        opts, rest = self.b.parse_flags(['fake', '-d', ':', 'x'], self.sh,
                                        flags='ab', value_flags='d')
        assert opts['d'] == ':'
        assert rest == ['x']

    def test_value_flag_attached(self):
        opts, rest = self.b.parse_flags(['fake', '-d:', 'x'], self.sh,
                                        value_flags='d')
        assert opts['d'] == ':'
        assert rest == ['x']

    def test_cluster_then_value(self):
        opts, rest = self.b.parse_flags(['fake', '-ad', ':', 'x'], self.sh,
                                        flags='ab', value_flags='d')
        assert opts['a'] and opts['d'] == ':'
        assert rest == ['x']

    def test_double_dash_ends_options(self):
        opts, rest = self.b.parse_flags(['fake', '--', '-a'], self.sh, flags='a')
        assert opts['a'] is False
        assert rest == ['-a']

    def test_invalid_flag_returns_none(self):
        opts, rest = self.b.parse_flags(['fake', '-q'], self.sh, flags='ab')
        assert opts is None
        assert 'invalid option' in self.sh.stderr.getvalue()

    def test_missing_value_returns_none(self):
        opts, rest = self.b.parse_flags(['fake', '-d'], self.sh, value_flags='d')
        assert opts is None
        assert 'requires an argument' in self.sh.stderr.getvalue()

    def test_first_operand_stops_parsing(self):
        opts, rest = self.b.parse_flags(['fake', 'x', '-a'], self.sh, flags='a')
        assert opts['a'] is False
        assert rest == ['x', '-a']


class TestWriteHelpers:
    def test_write_uses_shell_stdout(self):
        b, sh = _Fake(), _Shell()
        b.write_line('hello', sh)
        assert sh.stdout.getvalue() == 'hello\n'

    def test_error_uses_shell_stderr_with_prefix(self):
        b, sh = _Fake(), _Shell()
        b.error('boom', sh)
        assert sh.stderr.getvalue() == 'fake: boom\n'

    def test_forked_child_paths_via_pipeline(self):
        """End to end: builtins in pipelines write at the fd level."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo via-echo | cat; pwd >/dev/null && echo ok; set -o | head -1 | wc -l'],
            capture_output=True, text=True)
        lines = result.stdout.split()
        assert lines[0] == 'via-echo'
        assert lines[1] == 'ok'
        assert lines[2] == '1'
