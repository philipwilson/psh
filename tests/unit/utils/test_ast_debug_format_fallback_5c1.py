"""The ``ast_debug`` unknown-format path, pinned (remediation 5C.1, BL-3).

`print_ast_debug` used to wrap its whole formatter chain in
``except (ValueError, TypeError, AttributeError)``, which downgraded a defect in
ANY renderer to a warning plus a silent fallback. 5C.1 narrowed it — but not by
deleting the handler, because unlike the slot's other maskers this one's
``ValueError`` leg was ALIVE: it was catching this module's own
``raise ValueError("unknown AST format ...")``, a path a user really can reach.
So the raise was TYPED (``UnknownASTFormat``) and the catch narrowed to it.

That design rests on a claim about user-visible behaviour — *the unknown-format
warning and fallback are unchanged* — and the verify round found the claim TRUE
but UNPINNED: the only greps for it were the comments asserting it. This file
is the missing pin, and it is deliberately two-axis, matching what the brief
requires of every narrowed masker:

* **AXIS 1 (regression)** — the user-reachable unknown-format path still emits
  its exact warning line and still falls back to ``DebugASTVisitor``;
* **AXIS 2 (reclassification)** — a defect inside the SELECTED formatter, which
  the old net downgraded to that very same warning, now propagates.

Axis 2 is the one that matters for reading the design. At base, a broken
renderer and a mistyped format name produced *identical* user-visible output,
so the shell could not tell you which had happened. Separating them is the
point of typing the raise.

**The driving route is the only one that works, and that is worth stating**
because two plausible-looking routes do not (verify-round nits N-14/N-25):
``print_ast_debug`` reads ``PSH_AST_FORMAT`` through
``shell.state.scope_manager.get_variable``, so it must be set as a SHELL
variable in-session; a process environment variable is never consulted, and
``--debug-ast=bogus`` is rejected by the invocation parser's closed vocabulary
before this module is reached. A probe using either silently exercises the
default ``tree`` format and passes while testing nothing.
"""

import io
import sys

import pytest

from psh.lexer import tokenize
from psh.parser import parse
from psh.utils.ast_debug import UnknownASTFormat, print_ast_debug

WARNING = "Warning: AST formatting failed (unknown AST format 'bogus'), using default format"


@pytest.fixture
def ast_and_shell(shell):
    return parse(tokenize("echo hi")), shell


def _render(shell, ast, fmt):
    """Run print_ast_debug with *fmt* as the in-session shell variable.

    Returns captured stderr, or re-raises whatever escaped.
    """
    shell.state.scope_manager.set_variable("PSH_AST_FORMAT", fmt)
    err = io.StringIO()
    real, sys.stderr = sys.stderr, err
    try:
        print_ast_debug(ast, None, shell)
    finally:
        sys.stderr = real
    return err.getvalue()


# --- AXIS 1: the user-reachable unknown-format path is unchanged -------------

def test_unknown_format_warns_and_falls_back(ast_and_shell):
    ast, shell = ast_and_shell
    out = _render(shell, ast, "bogus")
    assert WARNING in out, (
        "the unknown-format warning changed; this is the user-visible line the "
        f"narrowing promised to leave byte-identical. Got:\n{out}")
    assert "Program" in out, (
        "the DebugASTVisitor fallback did not render after the warning")


def test_the_raise_is_typed_not_a_bare_valueerror():
    """The narrowing's whole basis: the handler catches THIS type, so a
    ValueError from anywhere else in the formatter chain is no longer swallowed.
    """
    assert issubclass(UnknownASTFormat, ValueError), (
        "UnknownASTFormat must stay a ValueError subclass — psh.utils is the "
        "runtime leaf layer and cannot import PshError from psh.core")
    assert UnknownASTFormat is not ValueError


@pytest.mark.parametrize("fmt", ["pretty", "tree", "compact", "sexp"])
def test_known_formats_do_not_warn(ast_and_shell, fmt):
    """CONTROL. Without this, a handler that warned on EVERY format would pass
    the axis-1 cell above while having broken every real render."""
    ast, shell = ast_and_shell
    out = _render(shell, ast, fmt)
    assert "AST formatting failed" not in out, (
        f"format {fmt!r} should render without the fallback warning:\n{out}")


# --- AXIS 2: a formatter defect now propagates ------------------------------

def test_a_formatter_defect_is_no_longer_masked(ast_and_shell, monkeypatch):
    """The reclassification axis.

    At base this seeded TypeError produced the SAME warning line as a bad
    format name — defect and user error were indistinguishable in the output.
    It must now escape.
    """
    ast, shell = ast_and_shell
    from psh.parser.visualization import ASTPrettyPrinter

    def boom(self, node):
        raise TypeError("seeded defect inside ASTPrettyPrinter.visit")

    monkeypatch.setattr(ASTPrettyPrinter, "visit", boom)
    with pytest.raises(TypeError, match="seeded defect"):
        _render(shell, ast, "pretty")


def test_a_formatter_attributeerror_is_no_longer_masked(ast_and_shell,
                                                        monkeypatch):
    """The other leg the old net swallowed."""
    ast, shell = ast_and_shell
    from psh.parser.visualization import AsciiTreeRenderer

    def boom(*a, **k):
        raise AttributeError("seeded defect inside AsciiTreeRenderer.render")

    monkeypatch.setattr(AsciiTreeRenderer, "render", boom)
    with pytest.raises(AttributeError, match="seeded defect"):
        _render(shell, ast, "tree")


# --- the route itself, pinned so a future probe cannot repeat my mistake -----

def test_the_environment_variable_route_does_NOT_reach_the_format(
        ast_and_shell, monkeypatch):
    """N-25, as an executable warning.

    ``print_ast_debug`` resolves PSH_AST_FORMAT through the SHELL's variable
    scope, never ``os.environ``. A probe that exports it instead silently
    renders the default ``tree`` and passes while testing nothing — which is
    exactly what my first Phase B probe did for one round. Pinning the negative
    keeps the next person from losing the same time.
    """
    ast, shell = ast_and_shell
    monkeypatch.setenv("PSH_AST_FORMAT", "bogus")
    shell.state.scope_manager.set_variable("PSH_AST_FORMAT", "")
    err = io.StringIO()
    real, sys.stderr = sys.stderr, err
    try:
        print_ast_debug(ast, None, shell)
    finally:
        sys.stderr = real
    assert "AST formatting failed" not in err.getvalue(), (
        "the process environment reached the format selector — if that is now "
        "intended, this pin and the UnknownASTFormat docstring both need "
        "updating")
