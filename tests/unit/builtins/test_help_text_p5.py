"""P5 help-text pins for builtins the parse_flags oracle does NOT cover.

`declare`/`local`/`typeset`/`readonly` hand-roll their option walk (the `+attr`
removal syntax), so `test_builtin_help_sync.py` (which reads `parse_flags` specs)
cannot check them; `trap`/`exec`/`read` had help-BODY drift the oracle passes
because their synopsis property was already correct. These pins lock the P5
fixes for that remainder.
"""

from psh.version import __version__


def _help(shell, name):
    assert shell.run_command(f'help {name}') == 0
    return shell.get_stdout()


class TestNamerefFlagDocumented:
    """declare/typeset/local advertise -n (nameref), which they accept."""

    def test_declare_help_documents_n(self, captured_shell):
        out = _help(captured_shell, 'declare')
        assert '[-aAfFgilnprtux]' in out
        assert '\n      -n' in out

    def test_typeset_help_documents_n(self, captured_shell):
        out = _help(captured_shell, 'typeset')
        assert '[-aAfFgilnprtux]' in out
        assert '\n      -n' in out

    def test_local_help_documents_n(self, captured_shell):
        out = _help(captured_shell, 'local')
        assert '[-aAilnrux]' in out
        assert '\n      -n' in out


class TestHelpBodyDrift:
    def test_exec_help_documents_a_c_l(self, captured_shell):
        out = _help(captured_shell, 'exec')
        # First line is the full synopsis, and the options are documented.
        assert 'exec [-cl] [-a name]' in out
        assert '-a name' in out
        assert '\n      -c' in out
        assert '\n      -l' in out

    def test_read_help_documents_u(self, captured_shell):
        out = _help(captured_shell, 'read')
        assert '\n      -u fd' in out

    def test_trap_help_is_the_full_manpage(self, captured_shell):
        """trap's manpage-style text used to live in an unread `help_text`
        property; it is now `help`, so `help trap` renders it."""
        out = _help(captured_shell, 'trap')
        assert 'SYNOPSIS' in out
        assert 'CONDITIONS' in out
        assert 'EXAMPLES' in out


class TestHelpBannerVersion:
    def test_help_banner_uses_psh_version(self, captured_shell):
        """The banner version comes from psh.version (no hardcoded 0.54.0)."""
        shell = captured_shell
        assert shell.run_command('help') == 0
        out = shell.get_stdout()
        assert f'PSH Shell, version {__version__}' in out
        assert '0.54.0' not in out
