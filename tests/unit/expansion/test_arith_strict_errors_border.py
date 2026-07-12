"""Strict-errors border of the arithmetic evaluator (reappraisal #19, P6).

The evaluator's cant-happen dispatch branches (unknown node type / unary /
binary / assignment operator) raise ``RuntimeError("internal: ...")`` rather
than a bare ``ValueError``. Two directions must hold:

- **User-reachable ``ValueError`` → clean shell error.** ``int()`` on a literal
  past CPython's str→int digit limit (a huge integer reached through variable
  resolution) raises a real ``ValueError``; the evaluator KEEPS the
  ``except (ValueError, ...)`` catch that converts it to a
  ``ShellArithmeticError`` (a ``PshError``), so even with strict-errors ON it
  is a clean shell arithmetic error (rc 1), never a re-raised internal defect.

- **Injected internal ``RuntimeError`` → strict re-raise.** A cant-happen
  branch, forced to fire via monkeypatch, is a genuine internal defect: under
  strict-errors it PROPAGATES (so a real regression surfaces loudly), and with
  strict-errors OFF it is swallowed to the generic exit-1 diagnostic.
"""

import pytest

from psh.expansion.arithmetic.evaluator import ArithmeticEvaluator

# 5000 digits > CPython's default 4300-digit str->int limit, so int() on this
# STRING raises ValueError. (The digit-accumulating tokenizer path handles a
# bare literal without int(str); the ValueError is reached only through
# get_variable / _string_to_int, which int()-parse a stored plain-decimal.)
_HUGE_INT = "9" * 5000


# --- Direction A: user-reachable ValueError stays a clean shell error --------
#
# These pins must discriminate the PRIMARY catch from the FALLBACK: the kept
# ``except (ValueError, ...)`` in _evaluate_arithmetic_inner converts the
# huge-int ValueError to a ShellArithmeticError, which renders as
# ``psh: arithmetic error: ...``. If that catch were removed, the ValueError
# would instead escape to arithmetic_expansion_value's last-resort
# ``except (ValueError, TypeError)`` and render as
# ``psh: unexpected arithmetic error: ...`` — same rc 1, different shape. So
# the assertions anchor the EXACT primary prefix AND reject the fallback's
# "unexpected" marker; deleting ValueError from the kept catch turns these
# pins red (mutation M2, transcript archived in the P6 ledger).

def test_huge_int_via_variable_is_clean_error_under_strict(captured_shell):
    """A huge stored integer read into arithmetic is a clean arithmetic error
    (rc 1) through the PRIMARY ValueError catch — even with strict-errors ON."""
    captured_shell.state.options['strict-errors'] = True
    rc = captured_shell.run_command(f"x={_HUGE_INT}; echo $(( x ))")
    assert rc == 1
    stderr = captured_shell.get_stderr()
    assert "psh: arithmetic error:" in stderr
    assert "unexpected" not in stderr


def test_huge_int_array_subscript_is_clean_error_under_strict(captured_shell):
    """The same user-reachable ValueError via _string_to_int (array element /
    scalar-as-[0]) goes through the PRIMARY catch, not the fallback."""
    captured_shell.state.options['strict-errors'] = True
    rc = captured_shell.run_command(f"a=({_HUGE_INT}); echo $(( a[0] ))")
    assert rc == 1
    stderr = captured_shell.get_stderr()
    assert "psh: arithmetic error:" in stderr
    assert "unexpected" not in stderr


# --- Direction B: injected internal RuntimeError obeys the strict policy ------

@pytest.fixture
def _force_cant_happen_assignment(monkeypatch):
    """Empty the compound-assignment table so a real ``+=`` reaches the
    cant-happen ``raise RuntimeError('internal: unknown assignment operator')``
    branch. monkeypatch restores it after the test."""
    monkeypatch.setattr(ArithmeticEvaluator, "_COMPOUND_TO_BASE", {})


def test_injected_internal_defect_reraises_when_strict_on(
        captured_shell, _force_cant_happen_assignment):
    """Strict ON: the injected cant-happen RuntimeError PROPAGATES."""
    captured_shell.state.options['strict-errors'] = True
    with pytest.raises(RuntimeError,
                       match="internal: unknown assignment operator"):
        captured_shell.run_command("x=1; echo $(( x += 1 ))")


def test_injected_internal_defect_swallowed_when_strict_off(
        captured_shell, _force_cant_happen_assignment):
    """Strict OFF: the same defect is swallowed to the generic exit-1
    diagnostic (interactive shells stay alive)."""
    captured_shell.state.options['strict-errors'] = False
    rc = captured_shell.run_command("x=1; echo $(( x += 1 ))")
    assert rc == 1
    assert "internal: unknown assignment operator" in \
        captured_shell.get_stderr()


def test_dispatch_unknown_node_raises_runtime_error():
    """The dispatch cant-happen branch raises Runtime; a bare object is not a
    known ArithNode type, so _dispatch falls through to the internal raise.

    Direct unit-level proof that the branch is a RuntimeError (an internal
    defect the strict guard re-raises), not a ValueError (which the evaluator
    reserves for the user-reachable huge-int parse)."""
    ev = ArithmeticEvaluator(shell=None)
    with pytest.raises(RuntimeError, match="internal: unknown arithmetic node"):
        ev._dispatch(object())
