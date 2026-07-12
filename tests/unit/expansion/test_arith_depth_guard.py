"""Arithmetic explicit depth guards (reappraisal #17 Tier 2; #19 T9).

"expression too deeply nested" used to be a blanket RecursionError catch in
``evaluate_arithmetic`` — so whenever the SHELL exhausted the interpreter
stack (runaway function recursion) with arithmetic on top, the error was
mislabeled as an arithmetic problem. The depth is now guarded EXPLICITLY at
every arithmetic recursion path, so the blanket catch is gone and a genuine
RecursionError propagates to the function-call boundary where it is reported
as function nesting (see tests/integration/functions/test_recursion_depth.py
and ``test_function_recursion_not_mislabeled`` below):

* ``ArithParser.MAX_DEPTH`` (= 1024) bounds parse-side stack growth, counted
  in the rules that recurse DIRECTLY — parse_ternary (parens + ternary arms),
  parse_unary (unary chains), and parse_power (right-associative ``**`` chains).
* ``ArithmeticEvaluator.MAX_EVAL_DEPTH`` (= 1024) bounds evaluation width: a
  flat chain (``0+1+1+...``) is parsed ITERATIVELY (no parser recursion) into a
  deep tree the evaluator then recurses over.

(#19 T9 added the parse_power and MAX_EVAL_DEPTH guards; before them a wide
flat chain or a long ``**`` chain leaked a raw RecursionError.)
"""

import subprocess
import sys

import pytest

from psh.expansion.arithmetic.evaluator import ArithmeticEvaluator
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


def test_power_chain_guarded(monkeypatch, captured_shell):
    """A right-associative `**` chain recurses through parse_power directly
    (bypassing parse_ternary), so parse_power carries the same MAX_DEPTH guard.
    #19 T9: before this guard the chain leaked a raw RecursionError."""
    monkeypatch.setattr(ArithParser, 'MAX_DEPTH', 16)
    rc = captured_shell.run_command("echo $(( " + "**".join(["1"] * 10) + " ))")
    assert rc == 0
    assert captured_shell.get_stdout() == "1\n"
    captured_shell.clear_output()
    rc = captured_shell.run_command("echo $(( " + "**".join(["1"] * 40) + " ))")
    assert rc == 1
    assert "expression too deeply nested" in captured_shell.get_stderr()


def test_flat_chain_evaluation_guarded(monkeypatch, captured_shell):
    """A wide flat chain (`0+1+1+...`) is parsed ITERATIVELY (no parser
    recursion), then recursed over by the evaluator — so it is bounded by
    ArithmeticEvaluator.MAX_EVAL_DEPTH, NOT ArithParser.MAX_DEPTH. An explicit
    counter, not a stack-headroom accident. #19 T9: before this guard the
    chain leaked a raw RecursionError."""
    monkeypatch.setattr(ArithmeticEvaluator, 'MAX_EVAL_DEPTH', 16)
    rc = captured_shell.run_command("echo $(( 0" + "+1" * 8 + " ))")
    assert rc == 0
    assert captured_shell.get_stdout() == "8\n"
    captured_shell.clear_output()
    rc = captured_shell.run_command("echo $(( 0" + "+1" * 40 + " ))")
    assert rc == 1
    assert "expression too deeply nested" in captured_shell.get_stderr()


def test_flat_chain_over_limit_clean_error():
    """A 25,000-term flat chain exceeds MAX_EVAL_DEPTH (1024): clean arithmetic
    error, no traceback, shell continues. Documented divergence — bash computes
    it (prints 25000)."""
    chain = "0" + "+1" * 25000
    expr = f"echo $(( {chain} )); echo next=$?"
    r = subprocess.run([sys.executable, '-m', 'psh', '-c', expr],
                       capture_output=True, text=True, timeout=120)
    assert "expression too deeply nested" in r.stderr
    assert "Traceback" not in r.stderr
    assert "RecursionError" not in r.stderr


def test_function_recursion_not_mislabeled(tmp_path):
    """Regression guard (#19 T9): runaway function recursion whose body
    evaluates SHALLOW arithmetic must still trip FUNCNEST at the function-call
    boundary — NOT be mislabeled 'expression too deeply nested'. A blanket
    RecursionError catch in the arithmetic evaluator would swallow the
    surrounding-shell stack exhaustion; the explicit depth guards leave a
    genuine RecursionError to reach executor/function.py."""
    script = 'f() { local n=$((1+1)); f; }; f'
    r = subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                       capture_output=True, text=True, timeout=120)
    assert "maximum function nesting level exceeded" in r.stderr
    assert "expression too deeply nested" not in r.stderr
    assert "Traceback" not in r.stderr


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
