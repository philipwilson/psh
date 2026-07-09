"""Brace expansion resource budget (expansion Phase-1a F4).

The 10,000-item limit used to be checked only AFTER the intermediate lists were
built, so ``{1..1000000000}`` generated a billion strings before the guard
fired, and ``TokenBraceExpander`` then SILENTLY restored the literal token — so
``echo {1..20000}`` printed the 11-byte literal where bash prints 108,894 bytes.

Now the cardinality is computed BEFORE generating (O(1) fast-fail for a
pathological range), the limit is a generous 100,000 (``{1..20000}`` and even
``{1..100000}`` expand and match bash), and exceeding it raises a LOUD typed
error (a diagnostic on stderr and exit status 2) instead of a silent restore.

Keeping any limit is a DELIBERATE divergence from bash (which has none); it is a
resource guard, documented in docs/user_guide/17_differences_from_bash.md.
All in-budget expectations bash-5.2-verified.
"""
import os
import subprocess
import sys
import time

import pytest

from psh.expansion.brace_expansion import BraceExpander, BraceExpansionError


def _run_psh(script):
    """Run `script` through `psh -c` in a subprocess (faithful to the `-c`
    path, where an escaping error would pick up the top-level source-processor
    'unexpected error:' guard prefix). Returns (stdout, stderr, rc)."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("DISPLAY", "XAUTHORITY")}
    r = subprocess.run([sys.executable, "-m", "psh", "-c", script],
                       capture_output=True, text=True, env=env, timeout=30)
    return r.stdout, r.stderr, r.returncode


# `_OVER` overflows the 100,000-item budget in one range.
_OVER = "{1..200000}"


class TestBudgetOverflowConsistentAcrossContexts:
    """A brace-budget overflow is an EXPECTED shell error and must present
    IDENTICALLY in every field-producing context: a clean
    ``psh: brace expansion: N items exceeds the limit`` on stderr, status 1,
    empty stdout, shell continues — NEVER the top-level 'unexpected error:'
    internal-defect guard.

    Regression: for/select iterables expand OUTSIDE the SimpleCommand
    try/except, so the overflow escaped to the source-processor guard and
    printed ``psh: -c:1: unexpected error: brace expansion: ...`` (RED on tip
    0d631682). Simple-command, array-init, and redirect were already clean.
    """

    def _assert_clean_overflow(self, script):
        stdout, stderr, rc = _run_psh(script)
        assert rc == 1, f"{script!r}: rc={rc} stderr={stderr!r}"
        assert stdout == "", f"{script!r}: stdout={stdout!r}"
        assert "brace expansion:" in stderr and "exceeds the limit" in stderr
        assert "unexpected error" not in stderr, \
            f"{script!r}: leaked internal-defect guard: {stderr!r}"

    def test_simple_command(self):
        self._assert_clean_overflow(f"echo {_OVER}")

    def test_for_loop_iterable(self):
        # The RED case on 0d631682.
        self._assert_clean_overflow(f"for i in {_OVER}; do echo x; done")

    def test_select_loop_iterable(self):
        self._assert_clean_overflow(
            f"select i in {_OVER}; do echo x; done </dev/null")

    def test_array_init(self):
        self._assert_clean_overflow(f"a=({_OVER})")

    def test_redirect_target(self):
        self._assert_clean_overflow(f"echo hi > {_OVER}")

    def test_for_loop_overflow_shell_continues(self):
        # Status 1 for the loop, but the line continues (like the simple
        # command) — not a top-level abort.
        stdout, stderr, rc = _run_psh(
            f"for i in {_OVER}; do echo x; done; echo AFTER")
        assert stdout == "AFTER\n"
        assert rc == 0
        assert "unexpected error" not in stderr


class TestInBudgetMatchesBash:
    def test_large_range_expands(self, captured_shell):
        rc = captured_shell.run_command("set -- {1..20000}; echo $#")
        assert rc == 0
        assert captured_shell.get_stdout() == "20000\n"

    def test_at_limit_expands(self, captured_shell):
        rc = captured_shell.run_command("set -- {1..100000}; echo $#")
        assert rc == 0
        assert captured_shell.get_stdout() == "100000\n"

    def test_everyday_range_unaffected(self, captured_shell):
        rc = captured_shell.run_command("echo {1..3}")
        assert rc == 0
        assert captured_shell.get_stdout() == "1 2 3\n"

    def test_char_range_unaffected(self, captured_shell):
        rc = captured_shell.run_command("echo {a..e}")
        assert rc == 0
        assert captured_shell.get_stdout() == "a b c d e\n"


class TestOverBudgetIsLoud:
    # Brace expansion moved to the Word stage (v0.678): a budget overflow is
    # now a RUNTIME word-expansion error (exit 1), not the parse-time
    # syntax-error class (exit 2) it was when expansion ran at tokenize time.
    # bash has no limit here (deliberate psh divergence, no ground truth) — the
    # invariant that matters is that it fails LOUDLY, never silently restoring
    # the literal.
    def test_numeric_over_limit_exits_1_with_diagnostic(self, captured_shell):
        rc = captured_shell.run_command("echo {1..100001}")
        assert rc == 1
        assert "brace expansion: 100001 items exceeds the limit" in \
            captured_shell.get_stderr()
        # NOT silently restored to the literal, and nothing printed.
        assert captured_shell.get_stdout() == ""

    def test_product_over_limit_is_loud(self, captured_shell):
        rc = captured_shell.run_command("echo {a,b}{1..100000}")
        assert rc == 1
        assert "200000 items exceeds the limit" in captured_shell.get_stderr()
        assert captured_shell.get_stdout() == ""

    def test_nested_list_over_limit_is_loud(self, captured_shell):
        rc = captured_shell.run_command("echo {{1..60000},{1..60000}}")
        assert rc == 1
        assert "120000 items exceeds the limit" in captured_shell.get_stderr()


class TestPathologicalFailsFast:
    def test_billion_range_is_o1_not_generated(self, captured_shell):
        # The diagnostic reports the FULL cardinality (1e9) — proof it was
        # computed preemptively, not by generating a billion strings.
        start = time.time()
        rc = captured_shell.run_command("echo {1..1000000000}")
        elapsed = time.time() - start
        assert rc == 1
        assert "1000000000 items exceeds the limit" in \
            captured_shell.get_stderr()
        # Preemptive: an O(1) check, nowhere near the minutes a billion-item
        # generation would take. Generous bound to tolerate a slow CI host.
        assert elapsed < 5.0, f"took {elapsed:.1f}s — did it generate?"


class TestCoreBudget:
    """Unit-level checks on the core expander's preemptive budget."""

    def test_direct_numeric_over_limit_raises(self):
        expander = BraceExpander()
        with pytest.raises(BraceExpansionError) as exc:
            expander._expand_braces("{1..1000000000}")
        assert "1000000000" in str(exc.value)

    def test_direct_in_budget_ok(self):
        expander = BraceExpander()
        assert len(expander._expand_braces("{1..5}")) == 5
