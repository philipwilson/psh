"""Tests for FormatterVisitor (the AST formatter behind `psh --format`).

Regression for the bug where subshell and brace-group nodes fell through to
generic_visit and emitted ``# Unknown node: ...`` instead of valid shell.
"""

import pytest

from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import FormatterVisitor


def _fmt(src):
    return FormatterVisitor().visit(parse(tokenize(src)))


@pytest.mark.parametrize("src", [
    "( echo a; echo b )",
    "{ ls; echo done; }",
    "[[ -n $x ]]",
    "( cd /tmp && ls ) > out",
    "{ echo y; } &",
    "if [[ -f f ]]; then ( echo y ); fi",
    "echo a; ( echo b )",
])
def test_no_unknown_node(src):
    """No real node type should produce the '# Unknown node' fallback."""
    assert "# Unknown node" not in _fmt(src)


@pytest.mark.parametrize("src", [
    "( echo a; echo b )",
    "{ ls; echo done; }",
    "( cd /tmp && ls ) > out",
    "{ echo y; } &",
])
def test_group_round_trip_stable(src):
    """Formatting a group is idempotent and re-parseable."""
    once = _fmt(src)
    twice = FormatterVisitor().visit(parse(tokenize(once)))
    assert once == twice
    assert "# Unknown node" not in once


@pytest.mark.parametrize("src", [
    "echo a & echo b",
    "echo a & echo b &",
    "echo a & echo b; echo c",
    "( echo a ) & echo b",
    "echo a & echo b & echo c",
])
def test_backgrounded_top_level_is_idempotent(src):
    """A top-level `&` yields a background statement in the Program; joining
    statements with a blank line would be non-idempotent because re-parsing
    collapses it (reappraisal #16 Tier-2). The formatter joins every statement
    with a single newline, so format(format(x)) must equal format(x)."""
    once = _fmt(src)
    twice = FormatterVisitor().visit(parse(tokenize(once)))
    assert once == twice
    # The backgrounded item and its successor are one newline apart, not a
    # blank line.
    assert "\n\n" not in once


def test_subshell_uses_parens():
    out = _fmt("( echo hi )")
    assert out.startswith("(")
    assert out.rstrip().endswith(")")
    assert "echo hi" in out


def test_brace_group_uses_braces():
    out = _fmt("{ echo hi; }")
    assert out.startswith("{")
    assert out.rstrip().endswith("}")
    assert "echo hi" in out


class TestCStyleForAndLoopControl:
    """Ported from the deleted ShellFormatter tests (R12.B): the formatter
    behind `declare -f` must render C-style for headers and break/continue
    levels from the real AST field names (init_expr/condition_expr/
    update_expr, .level)."""

    def test_c_style_for_formats_without_error(self):
        out = _fmt("for ((i=0; i<3; i++)); do echo $i; done")
        assert "for ((i=0; i<3; i++))" in out
        assert "# Unknown node" not in out

    def test_c_style_for_empty_sections(self):
        out = _fmt("for ((;;)); do echo x; done")
        assert "for ((; ; ))" in out

    def test_break_with_level(self):
        assert "break 2" in _fmt("while true; do break 2; done")

    def test_continue_with_level(self):
        assert "continue 3" in _fmt("while true; do continue 3; done")


class TestFormatFunctionDefinition:
    """format_function_definition() is the chokepoint behind declare -f /
    type / command -V (R15 D3: the rotted duplicate ShellFormatter crashed
    on case arms and dropped heredoc bodies)."""

    @staticmethod
    def _via_shell(src, name='f'):
        from psh.shell import Shell
        from psh.visitor import format_function_definition
        sh = Shell()
        assert sh.run_command(src) == 0
        return format_function_definition(
            name, sh.function_manager.get_function(name))

    def test_case_arm_renders_patterns(self):
        out = self._via_shell(
            'f() { case $1 in a|b) echo AB;; *) echo O;; esac; }')
        assert 'a | b)' in out
        assert 'esac' in out

    def test_heredoc_body_and_delimiter_survive(self):
        out = self._via_shell('f() { cat <<EOF\nhello $x\nEOF\n}')
        # Body and delimiter at column 0 so the text re-parses.
        assert '\nhello $x\nEOF' in out

    def test_definition_attached_redirect_survives(self):
        out = self._via_shell('f() { echo hi; } > out.txt')
        assert out.rstrip().endswith('>out.txt')

    def test_output_reparses(self):
        out = self._via_shell(
            'f() { case $1 in a) echo A;; esac; g() { echo inner; }; }')
        assert parse(tokenize(out)) is not None


class TestProgramFormatting:
    """The formatter derives layout from the Program's statements and their
    background flags, not from a root container class (visit_Program joins
    every statement with a single newline)."""

    IDEMPOTENCE_CORPUS = [
        "echo hi",
        "echo a; echo b",
        "echo a\necho b\necho c",
        "echo a | cat | rev",
        "true && echo x || echo y",
        "while false; do echo x; done",
        "if true; then echo a; elif b; then c; else d; fi",
        "for i in 1 2 3; do echo $i; done",
        "case $x in a|b) echo AB;; *) echo O;; esac",
        "f() { echo hi; }",
        "( echo a; echo b )",
        "{ ls; echo done; }",
        "while false; do echo x; done\necho after",
        "echo before\nwhile false; do echo x; done",
        "echo a & echo b",
        "echo a & echo b & echo c",
        "echo a; echo b & echo c",
        "cat <<EOF\nhello\nEOF",
        "cat <<EOF && echo x\nbody\nEOF",
    ]

    @pytest.mark.parametrize("src", IDEMPOTENCE_CORPUS)
    def test_format_is_idempotent(self, src):
        once = _fmt(src)
        twice = FormatterVisitor().visit(parse(tokenize(once)))
        assert once == twice

    @pytest.mark.parametrize("src", [
        "while false; do echo x; done\necho after",
        "echo before\nwhile false; do echo x; done",
        "if true; then echo a; fi\necho b",
        "echo a\nfor i in 1 2; do echo $i; done",
    ])
    def test_compound_simple_order_no_blank_line(self, src):
        """Adjacent compound/simple statements are one newline apart in both
        orders — the container shape carries no blank-line policy."""
        out = _fmt(src)
        assert "\n\n" not in out

    @pytest.mark.parametrize("src", [
        "echo a & echo b",
        "echo a & echo b &",
        "( echo a ) & echo b",
        "a && b &",
        "echo a; echo b & echo c",
    ])
    def test_background_list_reparses_to_equivalent_program(self, src):
        """Formatting a background list and reparsing yields an equivalent
        Program (same AST, background flags preserved)."""
        from psh.ast_nodes import Program
        original = parse(tokenize(src))
        reparsed = parse(tokenize(_fmt(src)))
        assert isinstance(original, Program) and isinstance(reparsed, Program)
        assert reparsed == original
