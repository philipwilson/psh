"""Arithmetic-parser explicit nesting-depth guard (reappraisal #17 Tier 2).

"expression too deeply nested" used to be a blanket RecursionError catch in
``evaluate_arithmetic`` — so whenever the SHELL exhausted the interpreter
stack (runaway function recursion) with arithmetic on top, the error was
mislabeled as an arithmetic problem. ``ArithParser`` now guards expression
nesting EXPLICITLY (``MAX_DEPTH`` = 1024, counted in parse_ternary and in
parse_unary's self-recursion), the blanket catch is gone, and a genuine
RecursionError propagates to the function-call boundary where it is reported
as function nesting (see tests/integration/functions/test_recursion_depth.py).
"""

import subprocess
import sys

import pytest

from psh.expansion.arithmetic.parser import ArithParser


def _nested_parens(n, val="1"):
    return "(" * n + val + ")" * n


def test_deep_parens_within_limit(captured_shell):
    rc = captured_shell.run_command(f"echo $(( {_nested_parens(64)} ))")
    assert rc == 0
    assert captured_shell.get_stdout() == "1\n"


def test_guard_fires_deterministically(monkeypatch, captured_shell):
    """The guard is an explicit counter, not a stack-headroom accident."""
    monkeypatch.setattr(ArithParser, 'MAX_DEPTH', 16)
    rc = captured_shell.run_command(f"echo $(( {_nested_parens(15)} ))")
    assert rc == 0
    assert captured_shell.get_stdout() == "1\n"
    captured_shell.clear_output()
    rc = captured_shell.run_command(f"echo $(( {_nested_parens(20)} ))")
    assert rc == 1
    assert "expression too deeply nested" in captured_shell.get_stderr()


def test_unary_chain_guarded(monkeypatch, captured_shell):
    """`- - - …x` recurses through parse_unary directly (bypassing
    parse_ternary) — it carries its own guard on the same counter."""
    monkeypatch.setattr(ArithParser, 'MAX_DEPTH', 16)
    rc = captured_shell.run_command("echo $(( " + "- " * 10 + "1 ))")
    assert rc == 0
    assert captured_shell.get_stdout() == "1\n"
    captured_shell.clear_output()
    rc = captured_shell.run_command("echo $(( " + "- " * 40 + "1 ))")
    assert rc == 1
    assert "expression too deeply nested" in captured_shell.get_stderr()


def test_real_threshold_over_limit_clean_error():
    """1500 nested parens exceeds MAX_DEPTH (1024): clean arithmetic error,
    no traceback, shell continues (documented divergence: bash parses this,
    limited only by its C stack)."""
    expr = f"echo $(( {_nested_parens(1500)} )); echo next=$?"
    r = subprocess.run([sys.executable, '-m', 'psh', '-c', expr],
                       capture_output=True, text=True, timeout=120)
    assert "expression too deeply nested" in r.stderr
    assert "Traceback" not in r.stderr
    assert "RecursionError" not in r.stderr


@pytest.mark.parametrize("n", [256, 1023])
def test_real_threshold_within_limit(n):
    """Up to MAX_DEPTH-1 nested parens parse and evaluate fine (the outermost
    expression is itself depth 1; needs the interpreter headroom a psh
    process sets up, hence subprocess)."""
    r = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', f"echo $(( {_nested_parens(n)} ))"],
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0
    assert r.stdout == "1\n"
