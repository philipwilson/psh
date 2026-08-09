#!/usr/bin/env python3
"""A16 — can a RAW Python ArithmeticError escape evaluate_arithmetic?

D2 left the ShellArithmeticError-vs-ArithmeticError narrowing choice resting on
ABSENCE of evidence ("my corpus produced no such cell either way"). That is the
weakest kind of basis, so this measures it directly.

STATIC half (recorded in the ledger): `_apply_binary_op` (evaluator.py:472) is
the SINGLE door for raw arithmetic — plain binary ops reach it at :424 and
compound assignments at :454 via the DIVIDE_ASSIGN->DIVIDE map at :328. Count at
the one door (3.1/3.2/3.3 lesson). Inside it every raw op is guarded:
DIVIDE/MODULO check `right == 0`, POWER checks `right < 0`, shifts mask the
count `& 63`, and POWER uses modular pow so no huge intermediate is built. The
only bare `//` in the package (_trunc_div, :57) is reached only past the zero
guard.

FORCING half (this file): drive the OPERATOR axis — every divide/modulo/power/
shift spelling, PLAIN and COMPOUND — at the values that would raise a raw
ZeroDivisionError / OverflowError / ValueError if any guard were missing, and
record the escaping type. The claim is falsified by a single non-Shell
ArithmeticError.

ROOT from argv[1]; discriminator asserted before measuring.
"""
import os
import sys

ROOT = os.path.abspath(sys.argv[1])
sys.path.insert(0, ROOT)
import psh  # noqa: E402

assert os.path.dirname(psh.__file__) == os.path.join(ROOT, "psh"), "discriminator"
print(f"discriminator OK: {os.path.dirname(psh.__file__)}")

from psh.expansion.arithmetic import evaluate_arithmetic  # noqa: E402
from psh.expansion.arithmetic.errors import ShellArithmeticError  # noqa: E402
from psh.shell import Shell  # noqa: E402

# OPERATOR axis x FORM axis (plain / compound-assign) at the danger values.
CELLS = []
for label, plain, comp in [
    ("divide",  "{a}/{b}",  "v={a}, v/={b}"),
    ("modulo",  "{a}%{b}",  "v={a}, v%={b}"),
    ("power",   "{a}**{b}", "v={a}, v**={b}"),
    ("lshift",  "{a}<<{b}", "v={a}, v<<={b}"),
    ("rshift",  "{a}>>{b}", "v={a}, v>>={b}"),
]:
    for vlabel, a, b in [
        ("by-zero",        "1",  "0"),
        ("zero-by-zero",   "0",  "0"),
        ("neg-by-zero",    "-1", "0"),
        ("min64-by-neg1",  "-9223372036854775808", "-1"),   # C overflow shape
        ("neg-exponent",   "2",  "-1"),
        ("huge-exponent",  "9",  "9999999"),
        ("neg-shift",      "1",  "-1"),
        ("huge-shift",     "1",  "100000"),
        ("huge-by-huge",   "9" * 30, "9" * 30),
    ]:
        CELLS.append((f"{label}/plain/{vlabel}", plain.format(a=a, b=b)))
        CELLS.append((f"{label}/compound/{vlabel}", comp.format(a=a, b=b)))

shell = Shell(norc=True)
rows = []
try:
    for label, expr in CELLS:
        try:
            val = evaluate_arithmetic(expr, shell, arith_source_quotes=False)
            rows.append((label, expr, "(no exception)", f"={val}"))
        except BaseException as e:              # noqa: BLE001 - measuring
            rows.append((label, expr, type(e).__name__, str(e)[:44]))
finally:
    shell.close()

raised = [r for r in rows if r[2] != "(no exception)"]
shell_arith = [r for r in raised if r[2] == "ShellArithmeticError"]
raw_arith = [r for r in raised if r[2] != "ShellArithmeticError"]

print(f"\n{'CELL':34s} {'EXPR':30s} RAISED")
print("-" * 96)
for label, expr, tname, detail in rows:
    print(f"{label:34s} {expr[:28]:30s} {tname}  {detail}")

print(f"\ncells:                        {len(rows)}")
print(f"  no exception:               {len(rows) - len(raised)}")
print(f"  raised ShellArithmeticError:{len(shell_arith)}")
print(f"  raised ANYTHING ELSE:       {len(raw_arith)}")
if raw_arith:
    print("\n  !! a non-Shell error escaped — the narrowing claim is FALSIFIED:")
    for label, expr, tname, detail in raw_arith:
        print(f"       {label:34s} {expr[:28]:30s} {tname}: {detail}")
else:
    print("\n  every raised error is ShellArithmeticError (a PshError AND a "
          "builtins.ArithmeticError)")

# CONTROL: the instrument must be able to SEE a raw ArithmeticError.
print("\n--- SEEDED CONTROL (can this probe observe a raw ArithmeticError?) ---")
try:
    1 // 0
except BaseException as e:                      # noqa: BLE001
    is_shell = isinstance(e, ShellArithmeticError)
    print(f"  raw {type(e).__name__} observed; isinstance(ShellArithmeticError)"
          f"={is_shell}  (must be False, else the classifier is vacuous)")
