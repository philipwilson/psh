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
  That catch is the reason every OUTER ``except ValueError`` leg guarding
  ``evaluate_arithmetic`` was dead and could be removed in remediation 3.5 —
  it is exhaustive for the user-reachable class, so nothing bare escapes.

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
# These pins anchor the PRIMARY catch: the kept ``except (ValueError, ...)`` in
# _evaluate_arithmetic_inner converts the huge-int ValueError to a
# ShellArithmeticError, which renders as ``psh: arithmetic error: ...``.
# Deleting ValueError from that catch turns these pins red (mutation M2,
# transcript archived in the P6 ledger).
#
# UPDATED by remediation 3.5 (MEDIUM-12b): there is no longer a FALLBACK to
# discriminate against. arithmetic_expansion_value's last-resort
# ``except (ValueError, TypeError)`` — which rendered as
# ``psh: unexpected arithmetic error: ...`` at the same rc 1 — has been DELETED
# as an internal-defect masker (its VE leg was dead precisely BECAUSE the
# primary catch below is exhaustive for user-reachable VEs, and its TE leg
# fired only for psh bugs). So removing the primary catch now makes the
# ValueError PROPAGATE as an internal defect under strict-errors rather than
# re-render in a second shape. The ``"unexpected" not in stderr`` assertions
# are kept: they still fail if any such fallback is re-introduced, which is
# exactly what tests/unit/tooling/test_typed_expansion_error_m8_locks.py locks.

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


# --- The PS4 sibling: same border, the OTHER net remediation 3.5 narrowed ----
#
# ``manager.py#expand_ps4`` fell back to the RAW PS4 text on
# ``except Exception``, swallowing a genuine internal defect on the trace path
# in BOTH modes — invisible even under strict-errors, which is the whole
# complaint. Narrowed to ``except PshError``, so a defect now propagates and is
# classified.
#
# DECLARED DEFAULT-MODE DELTA (slot 3.5, R5-B7): this changes the DEFAULT-mode
# consequence class for an INJECTED defect — base emitted the trace with the
# raw PS4 text and continued (rc 0), tip aborts the command (rc 1). Measured
# both ways in ``tmp/obs-3-5/ps4_default_mode.py``. No user-reachable route
# exists (a PS4 expansion failing for a SHELL reason still falls back — the
# third pin below), so the delta is injection-only. These pins LOCK the
# declared model in both modes rather than leaving it described in prose.

@pytest.fixture
def _force_ps4_internal_defect(monkeypatch):
    """Make the PS4 expansion path raise a genuine internal defect, and ONLY
    that path: the wrapper delegates unless the text carries the sentinel, so
    ordinary expansion in the same shell is untouched."""
    from psh.expansion.manager import ExpansionManager
    real = ExpansionManager.expand_string_variables

    def wrapper(self, text, *a, **k):
        if 'FORCEDEFECT' in text:
            raise TypeError('FORCED-INTERNAL-DEFECT')
        return real(self, text, *a, **k)

    monkeypatch.setattr(ExpansionManager, "expand_string_variables", wrapper)


def test_ps4_internal_defect_is_not_swallowed_when_strict_off(
        captured_shell, _force_ps4_internal_defect):
    """Strict OFF: the defect reaches the last-resort guard and the command
    fails (rc 1) instead of degrading to an untraced prompt. Before the
    narrowing this returned 0 with the raw PS4 emitted and the command run —
    the masking this slot removed."""
    captured_shell.state.options['strict-errors'] = False
    rc = captured_shell.run_command("set -x; PS4='FORCEDEFECT$x '; echo hi")
    assert rc == 1
    assert "hi" not in captured_shell.get_stdout()


def test_ps4_internal_defect_reraises_when_strict_on(
        captured_shell, _force_ps4_internal_defect):
    """Strict ON: the same defect PROPAGATES, so a real regression on the trace
    path surfaces loudly instead of silently untracing."""
    captured_shell.state.options['strict-errors'] = True
    with pytest.raises(TypeError, match="FORCED-INTERNAL-DEFECT"):
        captured_shell.run_command("set -x; PS4='FORCEDEFECT$x '; echo hi")


def test_ps4_shell_error_still_falls_back_in_both_modes(captured_shell):
    """COUNTER-PIN: a PS4 expansion failing for a SHELL reason (a PshError)
    must STILL fall back to the raw text and let the command run — bash-parity,
    and exactly what the narrowing had to preserve. Without this row the two
    pins above would be satisfied by simply deleting the fallback."""
    for strict in (False, True):
        captured_shell.clear_output()
        captured_shell.state.options['strict-errors'] = strict
        rc = captured_shell.run_command("set -x; PS4='$((1/0)) '; echo hi")
        assert rc == 0, f"strict={strict}"
        assert "hi" in captured_shell.get_stdout(), f"strict={strict}"
