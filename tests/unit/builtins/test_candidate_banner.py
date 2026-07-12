"""T3c: ONE candidate banner renderer shared by `type` and `command -V`.

Characterization pins for all six CandidateKind banners, through BOTH
builtins. bash 5.2 prints identical wording for the two (probe
tmp/r19-ledgers/T3-probes/t3c-banner-base.txt), so the shared
`type_builtin.render_candidate_banner` has no per-builtin style knob.
"""
import pytest

from psh.builtins.type_builtin import render_candidate_banner


def _out(shell, cmd):
    shell.clear_output()
    rc = shell.run_command(cmd)
    return rc, shell.get_stdout()


# Each case: (setup command or None, name, expected stdout)
_CASES = [
    (None, 'while', 'while is a shell keyword\n'),
    (None, 'cd', 'cd is a shell builtin\n'),
    ("alias ll='ls -l'", 'll', "ll is aliased to `ls -l'\n"),
    ('hash -p /bin/ls ls', 'ls', 'ls is hashed (/bin/ls)\n'),
]


class TestBannerParity:
    """The same six banners, byte-identical through both builtins."""

    @pytest.mark.parametrize('setup,name,expected', _CASES)
    def test_simple_kinds_both_builtins(self, captured_shell, setup, name,
                                        expected):
        if setup:
            captured_shell.run_command(setup)
        rc_t, out_t = _out(captured_shell, f'type {name}')
        rc_v, out_v = _out(captured_shell, f'command -V {name}')
        assert rc_t == rc_v == 0
        assert out_t == expected
        assert out_v == expected

    def test_function_banner_both_builtins(self, captured_shell):
        captured_shell.run_command('f() { echo hi; }')
        _, out_t = _out(captured_shell, 'type f')
        _, out_v = _out(captured_shell, 'command -V f')
        assert out_t.startswith('f is a function\n')
        assert 'echo hi' in out_t
        assert out_v == out_t  # byte-identical through the shared renderer

    def test_external_banner_both_builtins(self, captured_shell):
        # A disk command psh does not shadow with a builtin.
        rc, out_t = _out(captured_shell, 'type awk')
        assert rc == 0
        assert out_t.startswith('awk is /')
        assert out_t.rstrip('\n').endswith('/awk')
        _, out_v = _out(captured_shell, 'command -V awk')
        assert out_v == out_t


class TestRendererUnit:
    def test_multiline_function_banner_is_one_string(self, captured_shell):
        captured_shell.run_command('g() { echo one; }')
        cand = captured_shell.command_resolver.resolve('g').first
        banner = render_candidate_banner('g', cand)
        lines = banner.split('\n')
        assert lines[0] == 'g is a function'
        assert any('echo one' in ln for ln in lines[1:])
