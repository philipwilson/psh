"""Top-level control structures parse through the ordinary statement path.

Before v0.507.0, `Parser._parse_top_level_item()` special-cased top-level
control structures and hand-built `Pipeline`/`AndOrList` wrappers when one was
followed by `|`/`&&`/`||`/`&` — a second grammar path for the same syntax. It
also grouped statements differently depending on order:

    echo a; while ...; done   ->  one CommandList
    while ...; done; echo a   ->  TopLevel[WhileLoop, CommandList]   (asymmetric)

Now the whole top level goes through `parse_command_list`, so a control
structure is just a pipeline component like any other. `_simplify_result`
restores the historical `TopLevel`-rooted shape for a program that is a single
bare compound / function definition, so existing callers and tests keep their
root shape.

These tests pin the resulting AST shapes (Phase 0) and guard against the
duplicate path being reintroduced (Phase 5).
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from psh.ast_nodes import (
    AndOrList,
    CommandList,
    FunctionDef,
    Pipeline,
    SimpleCommand,
    TopLevel,
    WhileLoop,
)
from psh.lexer import tokenize
from psh.parser import parse

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _parse(src):
    return parse(tokenize(src))


def _root_items(ast):
    """The top-level items, whether the root is TopLevel or a CommandList."""
    if isinstance(ast, TopLevel):
        return ast.items
    return ast.statements


def _only(ast):
    items = _root_items(ast)
    assert len(items) == 1, f"expected one top-level item, got {len(items)}"
    return items[0]


# ---------------------------------------------------------------------------
# Phase 0: root-shape characterization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("src,node_name", [
    ("while false; do :; done", "WhileLoop"),
    ("until false; do :; done", "UntilLoop"),
    ("for x in a; do echo \"$x\"; done", "ForLoop"),
    ("for ((i=0; i<1; i++)); do :; done", "CStyleForLoop"),
    ("if true; then echo y; fi", "IfConditional"),
    ("case x in x) echo x ;; esac", "CaseConditional"),
    ("[[ -n x ]]", "EnhancedTestStatement"),
    ("(( 1 ))", "ArithmeticEvaluation"),
])
def test_bare_compound_keeps_toplevel_root(src, node_name):
    """A program that is one bare compound keeps the historical TopLevel root."""
    ast = _parse(src)
    assert isinstance(ast, TopLevel)
    assert type(_only(ast)).__name__ == node_name


def test_bare_function_def_keeps_toplevel_root():
    ast = _parse("f() { echo hi; }")
    assert isinstance(ast, TopLevel)
    assert isinstance(_only(ast), FunctionDef)


@pytest.mark.parametrize("src", [
    "( echo hi )",       # subshell group: always CommandList-wrapped
    "{ echo hi; }",      # brace group: always CommandList-wrapped
    "echo hi",           # simple command
])
def test_non_bare_forms_stay_command_list(src):
    ast = _parse(src)
    assert isinstance(ast, CommandList)


# ---------------------------------------------------------------------------
# Phase 0: operator forms route through the normal and-or / pipeline machinery
# ---------------------------------------------------------------------------

def test_control_in_pipeline_is_a_pipeline_component():
    """`while ...; done | cat` nests the loop exactly like a simple command."""
    ast = _parse("while false; do :; done | cat")
    and_or = _only(ast)
    assert isinstance(and_or, AndOrList)
    assert len(and_or.pipelines) == 1
    pipeline = and_or.pipelines[0]
    assert isinstance(pipeline, Pipeline)
    assert len(pipeline.commands) == 2
    assert isinstance(pipeline.commands[0], WhileLoop)
    assert isinstance(pipeline.commands[1], SimpleCommand)


@pytest.mark.parametrize("src,op", [
    ("while false; do :; done && echo ok", "&&"),
    ("while false; do :; done || echo no", "||"),
])
def test_control_in_and_or_list(src, op):
    and_or = _only(_parse(src))
    assert isinstance(and_or, AndOrList)
    assert and_or.operators == [op]
    assert len(and_or.pipelines) == 2
    assert isinstance(and_or.pipelines[0].commands[0], WhileLoop)


@pytest.mark.parametrize("src", [
    "while false; do :; done &",
    "for x in a; do echo \"$x\"; done &",
    "case x in x) echo x ;; esac &",
])
def test_control_backgrounded(src):
    """A backgrounded control structure marks the and-or list background."""
    and_or = _only(_parse(src))
    assert isinstance(and_or, AndOrList)
    assert and_or.background is True


def test_double_ampersand_after_background_is_error():
    with pytest.raises(Exception):
        _parse("while false; do :; done & && echo x")


# ---------------------------------------------------------------------------
# Phase 0: the order-asymmetry regression — both orders group identically
# ---------------------------------------------------------------------------

def test_order_independent_grouping():
    a = _parse("echo a; while false; do :; done")
    b = _parse("while false; do :; done; echo a")
    for ast in (a, b):
        items = _root_items(ast)
        assert len(items) == 2
        assert all(isinstance(s, AndOrList) for s in items)
    # The compound is wrapped as a pipeline component in both orders.
    a_kinds = [type(s.pipelines[0].commands[0]).__name__ for s in _root_items(a)]
    b_kinds = [type(s.pipelines[0].commands[0]).__name__ for s in _root_items(b)]
    assert sorted(a_kinds) == sorted(b_kinds) == ["SimpleCommand", "WhileLoop"]


# ---------------------------------------------------------------------------
# Phase 0: execution-level behavior is preserved
# ---------------------------------------------------------------------------

def _run(script):
    return subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
    )


@pytest.mark.parametrize("script,expected_out", [
    ("for x in 1 2 3; do echo $x; done | tr '\\n' ','", "1,2,3,"),
    ("if true; then echo yes; fi && echo after", "yes\nafter\n"),
    # The if-body fails, so the if exits non-zero and `||` fires (a bare
    # `if false; then ...; fi` exits 0, like bash, and would NOT fire `||`).
    ("if true; then false; fi || echo fallback", "fallback\n"),
    ("while false; do echo loop; done; echo done", "done\n"),
])
def test_execution_preserved(script, expected_out):
    result = _run(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected_out


def test_backgrounded_control_returns_and_wait_observes():
    result = _run("while false; do :; done & wait; echo reaped")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "reaped\n"


def test_redirection_on_compound_applies(tmp_path):
    out = tmp_path / "o.txt"
    result = _run(f"for x in a b c; do echo $x; done > {out}")
    assert result.returncode == 0, result.stderr
    assert out.read_text() == "a\nb\nc\n"


# ---------------------------------------------------------------------------
# Phase 5: guardrails against reintroducing the duplicate path
# ---------------------------------------------------------------------------

PARSER_PY = PROJECT_ROOT / "psh/parser/recursive_descent/parser.py"


def test_parser_does_not_hand_build_pipeline_or_andorlist():
    """parser.py must not manually construct Pipeline()/AndOrList() — those are
    assembled by the shared statement/command machinery, not the top level."""
    src = PARSER_PY.read_text()
    assert not re.search(r"\bPipeline\s*\(", src), "parser.py constructs Pipeline()"
    assert not re.search(r"\bAndOrList\s*\(", src), "parser.py constructs AndOrList()"


def test_special_pipeline_helper_is_gone():
    from psh.parser.recursive_descent.parsers.commands import CommandParser
    assert not hasattr(CommandParser, "parse_pipeline_with_initial_component")


def test_control_and_simple_command_share_pipeline_shape():
    """`<control> | cat` and `<simple> | cat` produce the same nesting."""
    control = _only(_parse("while false; do :; done | cat"))
    simple = _only(_parse("false | cat"))
    for and_or in (control, simple):
        assert isinstance(and_or, AndOrList)
        assert len(and_or.pipelines) == 1
        assert len(and_or.pipelines[0].commands) == 2
    # Only the first component's type differs (compound vs simple).
    assert isinstance(control.pipelines[0].commands[0], WhileLoop)
    assert isinstance(simple.pipelines[0].commands[0], SimpleCommand)
