"""Alias-argument injection conformance (Tier R8.6a interim fix).

THE BUG (command-injection class): the alias execution strategy expands an
alias at runtime by re-joining the ALREADY-EXPANDED argv into a source
string and re-lexing it. Because the args are already-expanded DATA (past
variable/command/glob expansion and quote removal), re-lexing reinterprets
any metacharacters they contain as SYNTAX. `alias e=echo; e 'a; echo PWNED'`
ran `echo PWNED` as a second command; `e '$(echo X)'` command-substituted;
`e '>zz'` created a file; `e 'a"b'` crashed with an unclosed-quote error.

THE FIX: shell-quote (shlex.quote) each appended arg before joining, so the
re-lexer treats each as a single literal word. The alias VALUE stays RAW —
an alias is meant to be parsed as shell (`alias ll='ls -l'`).

COMPARISON CONTRACT: each shell runs with the prelude IT needs to expand
aliases non-interactively — bash needs `shopt -s expand_aliases` plus the
alias on its own line; psh ALWAYS expands aliases (a documented divergence)
and emits a warning for `shopt -s expand_aliases`, so psh is given the bare
alias prelude. We compare stdout, exit code, and stderr-EMPTINESS (not text:
`psh:` vs `bash:` prefixes legitimately differ). This isolates the injection
behavior from the orthogonal always-expand and shopt-warning divergences.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTestFramework

_framework = ConformanceTestFramework()

# Alias definitions every case shares. Kept on their own lines so bash
# (with expand_aliases) expands them in a -c script.
_ALIASES = "alias e=echo\nalias ll='echo LL'\nalias g='echo G'\n"
_BASH_PRELUDE = "shopt -s expand_aliases\n" + _ALIASES
_PSH_PRELUDE = _ALIASES


def assert_alias_parity(invocation: str):
    """Run `invocation` after the alias prelude in each shell and assert
    parity on stdout, exit code, and stderr-emptiness."""
    psh = _framework.run_in_psh(_PSH_PRELUDE + invocation)
    bash = _framework.run_in_bash(_BASH_PRELUDE + invocation)
    assert psh.stdout == bash.stdout and psh.exit_code == bash.exit_code \
        and bool(psh.stderr) == bool(bash.stderr), (
        f"psh and bash differ for alias invocation: {invocation!r}\n"
        f"PSH:  stdout={psh.stdout!r} stderr={psh.stderr!r} exit={psh.exit_code}\n"
        f"Bash: stdout={bash.stdout!r} stderr={bash.stderr!r} exit={bash.exit_code}"
    )


class TestAliasArgumentInjection:
    """An already-expanded alias argument must stay literal DATA — never be
    re-interpreted as shell syntax."""

    def test_semicolon_is_not_a_command_separator(self):
        """e 'a; echo PWNED' -> literal arg, not a second command."""
        assert_alias_parity("e 'a; echo PWNED'")

    def test_command_substitution_in_arg_is_literal(self):
        """e '$(echo X)' -> literal $(echo X), no command substitution."""
        assert_alias_parity("e '$(echo X)'")

    def test_variable_in_arg_is_literal(self):
        """e '$FOO' -> literal $FOO, no variable expansion."""
        assert_alias_parity("e '$FOO'")

    def test_glob_in_arg_is_literal(self):
        """e '*.md' -> literal *.md, no pathname expansion."""
        assert_alias_parity("e '*.md'")

    def test_redirect_metachar_in_arg_is_literal(self):
        """e '>zz' -> literal >zz, no redirection (must NOT create a file)."""
        assert_alias_parity("e '>zz'")

    def test_pipe_metachar_in_arg_is_literal(self):
        """e '|cat' -> literal |cat, no pipe."""
        assert_alias_parity("e '|cat'")

    def test_ampersand_in_arg_is_literal(self):
        """e 'a & b' -> literal arg, no backgrounding / second command."""
        assert_alias_parity("e 'a & b'")

    def test_embedded_double_quote_does_not_crash(self):
        """e 'a\"b' -> literal a"b; previously a re-lex unclosed-quote crash."""
        assert_alias_parity("e 'a\"b'")

    def test_single_quoted_arg_stays_one_word(self):
        """e 'a b' -> one arg "a b", not split into two words."""
        assert_alias_parity("e 'a b'")

    def test_tab_in_arg_stays_one_word(self):
        """e $'a\\tb' -> one arg containing a tab, not split."""
        assert_alias_parity("e $'a\tb'")


class TestAliasValueStaysShell:
    """Regression pins: the alias VALUE is still parsed as shell source — the
    fix only quotes the appended args, not the value."""

    def test_value_with_two_commands(self):
        """alias value containing `;` still runs two commands."""
        assert_alias_parity("ll")  # uses _ALIASES' ll
        # Define-and-run a multi-command value inline (own-line def for bash):
        psh = _framework.run_in_psh("alias x='echo a; echo b'\nx")
        bash = _framework.run_in_bash(
            "shopt -s expand_aliases\nalias x='echo a; echo b'\nx")
        assert psh.stdout == bash.stdout == "a\nb\n"
        assert psh.exit_code == bash.exit_code == 0

    def test_value_with_pipe(self):
        """alias value containing a pipe still pipes."""
        psh = _framework.run_in_psh("alias x='echo hi | cat'\nx")
        bash = _framework.run_in_bash(
            "shopt -s expand_aliases\nalias x='echo hi | cat'\nx")
        assert psh.stdout == bash.stdout == "hi\n"
        assert psh.exit_code == bash.exit_code == 0

    def test_normal_args_pass_through(self):
        """A simple alias with simple (metachar-free) args is unchanged."""
        assert_alias_parity("g x y")
        assert_alias_parity("g one two three")
