"""Help-surface pins for the debug/parse-tree/signals builtins (P5).

These outputs CHANGE BY DESIGN in the P5 help-oracle pass:

* ``parse-tree -h`` and ``signals -h`` used to print a useless ``__doc__``
  one-liner; they now print the builtin's full ``help`` text.
* The ``debug`` builtin's option map is derived from the option registry's
  DEBUG category, so its help no longer advertises the phantom ``parser`` row
  and its ``debug OPTION`` parsing and help stay in lockstep.
"""

from psh.builtins.debug_control import _derive_debug_option_map
from psh.core.option_registry import DEBUG_OPTION_NAMES


class TestDashHShowsHelp:
    def test_parse_tree_dash_h_prints_help(self, captured_shell):
        shell = captured_shell
        assert shell.run_command('parse-tree -h') == 0
        out = shell.get_stdout()
        # The real help (synopsis + options), NOT the "Execute the parse-tree
        # builtin." execute-docstring one-liner it used to print.
        assert 'parse-tree [-f FORMAT] [-p] COMMAND' in out
        assert '-f FORMAT' in out
        assert out.strip() != 'Execute the parse-tree builtin.'

    def test_signals_dash_h_prints_help(self, captured_shell):
        shell = captured_shell
        assert shell.run_command('signals -h') == 0
        out = shell.get_stdout()
        assert 'signals [-v]' in out
        assert out.strip() != 'Show signal handler state and history.'


class TestDebugOptionMapDerived:
    def test_no_phantom_parser_row(self, captured_shell):
        """The former help advertised a `parser` option the builtin never had."""
        shell = captured_shell
        assert shell.run_command('help debug') == 0
        assert 'parser' not in shell.get_stdout()

    def test_debug_listing_matches_derived_map(self, captured_shell):
        shell = captured_shell
        assert shell.run_command('debug') == 0
        out = shell.get_stdout()
        for short in _derive_debug_option_map():
            assert short in out
        assert 'parser' not in out

    def test_derived_map_excludes_sub_variants(self):
        """The single-word toggles are exposed; detail/fork variants are not."""
        m = _derive_debug_option_map()
        assert set(m) == {'ast', 'tokens', 'scopes', 'expansion', 'exec'}
        # Every exposed short name maps to a real registry option key.
        for key in m.values():
            assert key in DEBUG_OPTION_NAMES
        # The internal sub-variants stay out of the user-facing map.
        assert 'debug-expansion-detail' not in m.values()
        assert 'debug-exec-fork' not in m.values()

    def test_unknown_debug_option_rejected(self, captured_shell):
        """`debug parser` (the phantom name) is now an error."""
        shell = captured_shell
        assert shell.run_command('debug parser') == 1
