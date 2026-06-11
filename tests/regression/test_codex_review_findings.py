"""
Regression tests for bugs identified in codex_recommendations.md.

These tests document 5 bugs that were confirmed during the codex review
and have since been fixed. The tests originally carried xfail markers;
the markers were removed as each bug was fixed, so the tests now guard
the corrected behavior against regressions.

Findings (all fixed):
  1. High   — Quoted variable names treated as assignments
  2. Medium — Lone $ expands to empty string instead of literal $
  3. Medium — "$@" splitting missing in composite (mixed-quote) words
  4. Medium — Tilde expansion suppressed by any backslash in first part
  5. Low    — FormatterVisitor loses quotes in composite words
"""

import os

from psh.lexer import tokenize
from psh.parser import Parser, ParserConfig
from psh.visitor.formatter_visitor import FormatterVisitor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(cmd: str):
    """Parse a command string and return the AST."""
    tokens = tokenize(cmd)
    return Parser(tokens, config=ParserConfig()).parse()


def _first_simple_command(ast):
    """Extract the first SimpleCommand from a parsed AST."""
    return ast.statements[0].pipelines[0].commands[0]


# ===========================================================================
# Finding 1 — Quoted variable names treated as assignments
# ===========================================================================

class TestQuotedAssignmentDetection:
    """Quoted variable names must NOT be treated as assignments.

    In bash, `"FOO"=bar` is a command word (not an assignment) because
    the variable-name portion is quoted.  PSH incorrectly strips quotes
    via node.args and then passes the bare name to is_valid_assignment().
    """

    def test_double_quoted_var_name_is_not_assignment(self, captured_shell):
        """'\"FOO\"=bar' should be treated as a command, not an assignment."""
        shell = captured_shell
        shell.clear_output()

        result = shell.run_command('"FOO"=bar')

        # Bash produces "FOO=bar: command not found" (exit 127).
        # PSH currently silently sets FOO=bar (exit 0).
        assert result != 0, "Quoted variable name should not create an assignment"

    def test_single_quoted_var_name_is_not_assignment(self, captured_shell):
        """\"'FOO'=bar\" should be treated as a command, not an assignment."""
        shell = captured_shell
        shell.clear_output()

        result = shell.run_command("'FOO'=bar")

        assert result != 0, "Single-quoted variable name should not create an assignment"

    def test_partial_quoted_var_name_is_not_assignment(self, captured_shell):
        """'F\"OO\"=bar' should not be an assignment (partial quoting)."""
        shell = captured_shell
        shell.clear_output()

        result = shell.run_command('F"OO"=bar')

        assert result != 0, "Partially quoted variable name should not create an assignment"

    def test_unquoted_assignment_still_works(self, captured_shell):
        """Sanity check: unquoted FOO=bar must still work."""
        shell = captured_shell
        shell.clear_output()

        result = shell.run_command('FOO=bar; echo "$FOO"')

        assert result == 0
        assert shell.get_stdout() == "bar\n"


# ===========================================================================
# Finding 2 — Lone $ expands to empty string
# ===========================================================================

class TestLoneDollarSign:
    """A bare $ not followed by a valid variable name should be literal.

    In bash, `echo $` outputs `$`.  PSH creates VariableExpansion("")
    which resolves to an empty string.
    """

    def test_lone_dollar_at_end_of_input(self, captured_shell):
        """'echo $' should print a literal $ (works: EOF after $ is literal)."""
        shell = captured_shell
        shell.clear_output()

        result = shell.run_command('echo $')

        assert result == 0
        assert shell.get_stdout() == "$\n"

    def test_dollar_before_space(self, captured_shell):
        """'echo $ end' should print '$ end'."""
        shell = captured_shell
        shell.clear_output()

        result = shell.run_command('echo $ end')

        assert result == 0
        assert shell.get_stdout() == "$ end\n"

    def test_dollar_before_semicolon(self, captured_shell):
        """'echo $;' — the $ before ; should be literal."""
        shell = captured_shell
        shell.clear_output()

        result = shell.run_command('echo $;')

        assert result == 0
        assert shell.get_stdout() == "$\n"

    def test_dollar_in_double_quotes(self, captured_shell):
        """'echo \"$\"' — lone $ inside double quotes should be literal.

        This case already works in PSH because the $ is the last char
        before the closing quote.
        """
        shell = captured_shell
        shell.clear_output()

        result = shell.run_command('echo "$"')

        assert result == 0
        assert shell.get_stdout() == "$\n"


# ===========================================================================
# Finding 3 — "$@" splitting missing in composite words
# ===========================================================================

class TestDollarAtCompositeWords:
    """\"$@\" inside composite (mixed-quote) words must split.

    In bash, `printf '<%s>\\n' pre"$@"post` with params (a, b, c)
    produces <prea>, <b>, <cpost> — three separate arguments.
    PSH collapses them into a single argument because the composite-word
    expansion path lacks $@ splitting logic.

    Note: the uniformly double-quoted case ("x$@y") is handled correctly
    and tested separately in test_potential_bugs.py.
    """

    def test_composite_dollar_at_splits_into_separate_args(self, captured_shell):
        """pre\"$@\"post with 3 params should produce 3 arguments."""
        shell = captured_shell
        shell.state.positional_params = list(["a", "b", "c"])
        shell.clear_output()

        result = shell.run_command('printf "<%s>\\n" pre"$@"post')

        assert result == 0
        assert shell.get_stdout() == "<prea>\n<b>\n<cpost>\n"

    def test_composite_dollar_at_single_param(self, captured_shell):
        """pre\"$@\"post with 1 param should produce 1 argument (no split needed)."""
        shell = captured_shell
        shell.state.positional_params = list(["only"])
        shell.clear_output()

        result = shell.run_command('printf "<%s>\\n" pre"$@"post')

        assert result == 0
        assert shell.get_stdout() == "<preonlypost>\n"

    def test_composite_dollar_at_no_params(self, captured_shell):
        """pre\"$@\"post with 0 params should produce 'prepost'."""
        shell = captured_shell
        shell.state.positional_params = list([])
        shell.clear_output()

        # With no params, "$@" contributes nothing but the surrounding
        # unquoted text still produces a word: "prepost".
        result = shell.run_command('printf "<%s>\\n" pre"$@"post')

        assert result == 0
        assert shell.get_stdout() == "<prepost>\n"

    def test_composite_dollar_at_two_params(self, captured_shell):
        """pre\"$@\"post with 2 params should produce 2 arguments."""
        shell = captured_shell
        shell.state.positional_params = list(["x", "y"])
        shell.clear_output()

        result = shell.run_command('printf "<%s>\\n" pre"$@"post')

        assert result == 0
        assert shell.get_stdout() == "<prex>\n<ypost>\n"


# ===========================================================================
# Finding 4 — Tilde expansion suppressed by any backslash
# ===========================================================================

class TestTildeWithBackslash:
    """Tilde expansion should only be suppressed when the ~ itself is escaped.

    In bash, `~/\\foo` expands the tilde because the backslash escapes
    a later character, not the tilde.  PSH sets a coarse `had_escapes`
    flag for the entire literal part and skips tilde expansion.
    """

    def test_tilde_slash_backslash(self, captured_shell):
        r"""'echo ~/\foo' should expand ~ to home directory."""
        shell = captured_shell
        shell.clear_output()

        result = shell.run_command('echo ~/\\foo')

        assert result == 0
        home = os.path.expanduser('~')
        assert shell.get_stdout() == f"{home}/foo\n"

    def test_tilde_slash_backslash_in_middle(self, captured_shell):
        r"""'echo ~/a\b' should expand ~ to home directory."""
        shell = captured_shell
        shell.clear_output()

        result = shell.run_command('echo ~/a\\b')

        assert result == 0
        home = os.path.expanduser('~')
        assert shell.get_stdout() == f"{home}/ab\n"

    def test_escaped_tilde_not_expanded(self, captured_shell):
        r"""'echo \~' should NOT expand tilde (the ~ itself is escaped)."""
        shell = captured_shell
        shell.clear_output()

        result = shell.run_command('echo \\~')

        assert result == 0
        assert shell.get_stdout() == "~\n"

    def test_plain_tilde_still_works(self, captured_shell):
        """Sanity check: plain ~ still expands."""
        shell = captured_shell
        shell.clear_output()

        result = shell.run_command('echo ~')

        assert result == 0
        home = os.path.expanduser('~')
        assert shell.get_stdout() == f"{home}\n"


# ===========================================================================
# Finding 5 — FormatterVisitor loses quotes in composite words
# ===========================================================================

class TestFormatterCompositeQuotes:
    """FormatterVisitor must preserve per-part quoting in composite words.

    The formatter only re-adds quotes for wholly-quoted words
    (word.is_quoted == True).  Composite words like foo"bar"baz have
    is_quoted == False, so their quoted sections are lost in the
    formatted output.
    """

    def test_composite_double_quoted_preserved(self):
        """Formatting 'echo foo\"bar\"baz' should preserve the quotes."""
        ast = _parse('echo foo"bar"baz')
        formatter = FormatterVisitor()
        formatted = formatter.visit(ast)

        # The formatted output must contain the double quotes around "bar"
        # to preserve the original semantics (glob suppression, etc.)
        assert '"bar"' in formatted or "foo\"bar\"baz" in formatted

    def test_composite_single_quoted_preserved(self):
        """Formatting \"echo foo'bar'baz\" should preserve the quotes."""
        ast = _parse("echo foo'bar'baz")
        formatter = FormatterVisitor()
        formatted = formatter.visit(ast)

        assert "'bar'" in formatted or "foo'bar'baz" in formatted

    def test_wholly_quoted_word_preserved(self):
        """Sanity check: wholly quoted words should keep their quotes."""
        ast = _parse('echo "hello world"')
        formatter = FormatterVisitor()
        formatted = formatter.visit(ast)

        assert '"hello world"' in formatted
