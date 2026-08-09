#!/usr/bin/env python3
"""A4 — D-3.5-s2: per-LEG forcing for let_builtin.py:52
``except (ValueError, ArithmeticError)`` around ``evaluate_arithmetic``.

Question (Checkpoint R corrected the LEDGER's wording): the catch is ALREADY
the typed pair, so the residue is the 3.5 DEADNESS question — which of the two
legs can actually fire?

METHOD (deliberately NOT the method that produced the claim — D-3.5 joint
lesson). Rather than reading the evaluator and arguing, this drives a corpus of
user-reachable `let` expressions through the REAL production path in-process
and records, per cell, the EXACT exception type that reaches the handler. The
handler is not simulated: `evaluate_arithmetic` is called with the same
arguments `let` passes (`arith_source_quotes=False`) and the raised type is
captured verbatim, then classified against the two legs by real `isinstance`.

ROOT from argv[1] (CR-D5 portability); the resolved `psh` package path is
asserted in-process BEFORE measuring (the editable install resolves to MAIN
from any other cwd — see ledger preamble).
"""
import os
import sys

ROOT = os.path.abspath(sys.argv[1])
sys.path.insert(0, ROOT)

import psh  # noqa: E402

resolved = os.path.dirname(psh.__file__)
assert resolved == os.path.join(ROOT, "psh"), (
    f"DISCRIMINATOR FAILED: psh resolved to {resolved}, expected "
    f"{os.path.join(ROOT, 'psh')} — refusing to measure the wrong tree")
print(f"discriminator OK: psh -> {resolved}")

from psh.expansion.arithmetic import evaluate_arithmetic  # noqa: E402
from psh.shell import Shell  # noqa: E402

# The corpus: user-reachable `let` operands. Every cell is something a user can
# type at a psh prompt — no injected defects (those are the SEEDED arm below).
CORPUS = [
    # --- well-formed (control: no exception at all) ---
    ("ok/simple",            "1+1"),
    ("ok/zero",              "0"),
    ("ok/var",               "x=5"),
    ("ok/compound",          "x+=2"),
    # --- syntax errors ---
    ("syntax/bare-op",       "1+"),
    ("syntax/empty",         ""),
    ("syntax/junk",          "@@@"),
    ("syntax/unbalanced",    "(1+2"),
    ("syntax/double-op",     "1**/2"),
    ("syntax/bad-token",     "1 2"),
    ("syntax/lone-op",       "*"),
    ("syntax/trailing-comma", "1,"),
    # --- division / modulo by zero ---
    ("div/zero",             "1/0"),
    ("div/mod-zero",         "1%0"),
    ("div/assign-zero",      "x/=0"),
    ("div/nested-zero",      "(4+4)/(2-2)"),
    # --- exponent domain ---
    ("exp/negative",         "2**-1"),
    # --- non-numeric / bad values ---
    ("num/alpha-var",        "y=abc, y+1"),
    ("num/hex-bad",          "0xZZ"),
    ("num/base-bad",         "2#9"),
    ("num/base-zero",        "0#1"),
    ("num/octal-bad",        "099"),
    ("num/huge-base",        "99#1"),
    # --- subscript shapes (the 2.3/W2 surface) ---
    ("sub/bad-index",        "a[]"),
    ("sub/bad-index2",       "a[ ]"),
    ("sub/assoc-missing",    "a[nosuch]"),
    ("sub/nested",           "a[b[]]"),
    ("sub/negative",         "a[-1]"),
    # --- recursion / self reference ---
    ("rec/self",             "z=z+1"),
    ("rec/deep",             "((((((((((1))))))))))"),
    # --- unset / strictness surface ---
    ("unset/plain",          "nosuchvar+1"),
    ("unset/increment",      "nosuchvar++"),
    # --- overflow-ish ---
    ("big/shift",            "1<<10000"),
    ("big/pow",              "9**9**5"),
]


def classify(exc):
    """Which leg of ``except (ValueError, ArithmeticError)`` takes it."""
    legs = []
    if isinstance(exc, ValueError):
        legs.append("ValueError")
    if isinstance(exc, ArithmeticError):
        legs.append("ArithmeticError")
    return legs


# AXIS: OPTION x SUBJECT — shapes whose escaping type depends on a shell
# OPTION or a variable attribute, not on the expression alone. These are the
# cells that can produce a PshError that is NEITHER leg (it would propagate
# past `let` entirely), so a deadness verdict that never varied the option
# would be quantifying over the wrong space.
OPTION_CORPUS = [
    ("opt/nounset-unset",     "set -u",            "nosuchvar+1"),
    ("opt/nounset-incr",      "set -u",            "nosuchvar++"),
    ("opt/nounset-subscript", "set -u",            "arr[nosuch]"),
    ("opt/readonly-assign",   "readonly r=1",      "r=2"),
    ("opt/readonly-incr",     "readonly r2=1",     "r2++"),
    ("opt/readonly-compound", "readonly r3=1",     "r3+=5"),
    ("opt/nameref-cycle",     "declare -n n1=n2; declare -n n2=n1", "n1+1"),
    ("opt/posix",             "set -o posix",      "1/0"),
]


def main():
    rows = []
    # Campaign F2 (process leases) forbids two simultaneously ACTIVE shells, so
    # every shell here is closed before the next is built. A shared shell would
    # also let one cell's `set -u`/readonly silently re-label every later row.
    shell = Shell(norc=True)
    try:
        for label, expr in CORPUS:
            try:
                val = evaluate_arithmetic(expr, shell,
                                          arith_source_quotes=False)
                rows.append((label, expr, "(no exception)", f"value={val}", []))
            except BaseException as e:           # noqa: BLE001 - measuring
                rows.append((label, expr, type(e).__name__,
                             type(e).__mro__[1].__name__, classify(e)))
    finally:
        shell.close()

    # OPTION axis: each cell gets a FRESH shell, built and closed in turn.
    for label, setup, expr in OPTION_CORPUS:
        s = Shell(norc=True)
        try:
            s.run_command(setup)
            try:
                val = evaluate_arithmetic(expr, s, arith_source_quotes=False)
                rows.append((label, expr, "(no exception)", f"value={val}", []))
            except BaseException as e:           # noqa: BLE001 - measuring
                rows.append((label, expr, type(e).__name__,
                             type(e).__mro__[1].__name__, classify(e)))
        finally:
            s.close()

    print(f"\n{'CELL':22s} {'EXPR':22s} {'RAISED':28s} LEGS")
    print("-" * 100)
    for label, expr, tname, _base, legs in rows:
        if tname == "(no exception)":
            verdict = "n/a (no exception raised)"
        elif legs:
            verdict = "+".join(legs)
        else:
            verdict = "ESCAPES BOTH LEGS"
        print(f"{label:22s} {expr[:20]:22s} {tname:28s} {verdict}")

    # --- Aggregates -------------------------------------------------------
    raised = [r for r in rows if r[2] != "(no exception)"]
    ve_only = [r for r in raised if r[4] == ["ValueError"]]
    ae_only = [r for r in raised if r[4] == ["ArithmeticError"]]
    both = [r for r in raised if len(r[4]) == 2]
    neither = [r for r in raised if not r[4]]

    print(f"\ncorpus cells:                 {len(rows)}")
    print(f"  no exception (control):     {len(rows) - len(raised)}")
    print(f"  raised:                     {len(raised)}")
    print(f"    -> ValueError leg ONLY:   {len(ve_only)}")
    print(f"    -> ArithmeticError ONLY:  {len(ae_only)}")
    print(f"    -> BOTH legs match:       {len(both)}")
    print(f"    -> ESCAPES both legs:     {len(neither)}")
    if neither:
        print("\n  !! cells that escape the handler entirely (propagate past `let`):")
        for label, expr, tname, _b, _l in neither:
            print(f"       {label:22s} {expr[:20]:22s} {tname}")
    if ve_only:
        print("\n  !! cells taken by the ValueError leg ALONE (leg is ALIVE):")
        for label, expr, tname, _b, _l in ve_only:
            print(f"       {label:22s} {expr[:20]:22s} {tname}")

    print("\nDistinct raised types: "
          + ", ".join(sorted({r[2] for r in raised})))

    # --- SEEDED arm: prove the ValueError leg CAN fire when something -------
    #     actually raises a bare VE, so a "dead" verdict is a measurement of
    #     the production path, not of an inert instrument (D-3.4 lesson 7).
    import psh.builtins.let_builtin as lb  # noqa: E402

    real = lb.__dict__.get("evaluate_arithmetic")
    print("\n--- SEEDED CONTROL (instrument must be able to see a live VE) ---")
    try:
        raise ValueError("seeded bare ValueError")
    except (ValueError, ArithmeticError) as e:
        print(f"  handler shape catches a bare VE: {type(e).__name__}: {e}")
    print(f"  (let_builtin imports evaluate_arithmetic lazily: "
          f"module-level binding present = {real is not None})")


if __name__ == "__main__":
    main()
