#!/usr/bin/env python3
"""Instrument 21 (slot 5B.2, R3 RN-2) — RED demonstration for the zero-slack cell.

The new `test_every_cap_equals_its_modules_actual_count` asserts a property the
old ratchet could not see: a cap sitting ABOVE its module's actual count. A
green cell proves nothing on its own, so this drives it RED in a scratch copy
and checks the failure names the RIGHT module and the RIGHT amount (5B.1 lesson
2 — a RED arm asserts its REASON, not merely its outcome).

Three arms:

  A  raise ONE cap by 3            -> RED, message names that module + "slack 3"
  B  add a cap entry for a module
     that defers nothing            -> RED, message names it as DEAD
  C  unmodified                     -> GREEN (control: the cell is not
                                      permanently red for unrelated reasons)

The scratch copy is a full tree copy so nothing in the worktree is touched, and
the discriminator is asserted in-process before any assertion is trusted.
`PYTHONDONTWRITEBYTECODE=1` throughout (lesson 1).

Usage:  python 21_zero_slack_cell_red_demo.py <ROOT> <SCRATCH>
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys

CELL = ("tests/unit/tooling/test_import_layering.py::"
        "test_every_cap_equals_its_modules_actual_count")


def run_cell(tree):
    r = subprocess.run(
        [sys.executable, "-m", "pytest", CELL, "-q", "--no-header", "-x"],
        cwd=str(tree), capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(tree),
             "PYTHONDONTWRITEBYTECODE": "1"})
    return r.returncode, r.stdout + r.stderr


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    scratch = pathlib.Path(sys.argv[2]).resolve()
    print(f"ROOT={root}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    print()

    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    for item in ("psh", "tests", "pyproject.toml", "conftest.py", "tools"):
        src = root / item
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, scratch / item,
                            ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, scratch / item)

    guard = scratch / "tests/unit/tooling/test_import_layering.py"
    pristine = guard.read_text()

    results = []

    # --- ARM C first: the control -----------------------------------------
    rc, out = run_cell(scratch)
    ok = rc == 0
    print(f"ARM C  unmodified control      : rc={rc} -> "
          f"{'PASS (green)' if ok else 'FAIL'}")
    results.append(("C", ok))

    # --- ARM A: raise one cap by 3 ----------------------------------------
    # 'psh.utils.ast_debug': 6 is a stable, unambiguous entry to perturb.
    victim = "psh.utils.ast_debug"
    bumped = pristine.replace(f"    '{victim}': 6,", f"    '{victim}': 9,")
    assert bumped != pristine, "cap-bump edit did not apply"
    guard.write_text(bumped)
    rc, out = run_cell(scratch)
    names_module = victim in out
    names_amount = "slack 3" in out
    says_slack = "cap 9 > actual 6" in out
    ok = rc != 0 and names_module and names_amount and says_slack
    print(f"ARM A  cap {victim} 6->9 : rc={rc}")
    print(f"       names module={names_module} names 'slack 3'={names_amount} "
          f"states 'cap 9 > actual 6'={says_slack}")
    print(f"       expected RED naming the module + amount -> "
          f"{'PASS' if ok else 'FAIL'}")
    results.append(("A", ok))
    guard.write_text(pristine)

    # --- ARM B: a DEAD entry (cap for a module that defers nothing) --------
    dead_mod = "psh.protocols"          # a true leaf: defers nothing, ever
    # count=1 and the leading newline anchor are both load-bearing: the file
    # also contains `print("FUNC_IMPORT_CAPS = {")` inside its regeneration
    # block, and an unanchored replace corrupted that string literal into a
    # SyntaxError — which pytest reports as rc=4 (collection error), NOT as the
    # assertion failure this arm is looking for. Caught by this arm asserting
    # its REASON rather than just a non-zero exit.
    seeded = pristine.replace("\nFUNC_IMPORT_CAPS = {\n",
                              f"\nFUNC_IMPORT_CAPS = {{\n    '{dead_mod}': 2,\n",
                              1)
    assert seeded != pristine, "dead-entry seed did not apply"
    guard.write_text(seeded)
    rc, out = run_cell(scratch)
    names_module = dead_mod in out
    says_dead = "defers NOTHING" in out
    ok = rc != 0 and names_module and says_dead
    print(f"ARM B  dead entry {dead_mod} : rc={rc}")
    print(f"       names module={names_module} says 'defers NOTHING'={says_dead}")
    print(f"       expected RED naming it DEAD -> {'PASS' if ok else 'FAIL'}")
    results.append(("B", ok))
    guard.write_text(pristine)

    # --- restoration + control replay -------------------------------------
    rc, _ = run_cell(scratch)
    restored = guard.read_text() == pristine
    print()
    print(f"restored byte-identical: {restored}   post-restore rc={rc}")
    print()
    print("=" * 70)
    for name, ok in results:
        print(f"  ARM {name}: {'PASS' if ok else 'FAIL'}")
    print(f"  {sum(1 for _, o in results if o)}/{len(results)} arms as designed")
    print("=" * 70)
    print()
    print("NOTE: the worktree was never edited — all arms ran in the scratch")
    print(f"copy at {scratch}.")


if __name__ == "__main__":
    main()
