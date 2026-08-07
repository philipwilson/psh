#!/usr/bin/env python3
"""M8 mutation locks for slot 4B.1 — each lock fails for its OWN reason.

For every mutation class in ``m8_plugin.py`` this runs the pin suite with the
mutant injected and records WHICH cells go red. A lock is only useful if it
discriminates, so each mutation declares both a MUST-GO-RED set and a
MUST-STAY-GREEN set; a mutation that reddens everything proves nothing about
which pin catches what.

The discrimination row that carries the most weight is M8-4: re-introducing
fresh-per-miss allocation must leave the POISONING pins green. If they went red
there, they would be testing allocation rather than immutability — which is
exactly how a poisoning pin could pass for the wrong reason.

A control run with no mutation must be fully green, otherwise every comparison
below is measured against a broken baseline.
"""
from __future__ import annotations

import os
import subprocess
import sys

WORKTREE = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
PIN_FILE = "tests/unit/core/test_variable_lookup_immutability.py"
PLUGIN_DIR = os.path.join(WORKTREE, "tmp", "4b1-instruments")

# Declared expectations. Substrings matched against the cell id.
EXPECT = {
    "M8-1": {
        "red": ["test_assignment_rejected", "test_deletion_rejected",
                "test_mutating_a_miss_raises", "test_poisoning_attempt",
                "test_mutating_a_declared_unset_result"],
        "green": ["test_result_exposes_no_binding",
                  "test_present_unset_is_a_shared_singleton",
                  "test_missing_is_a_shared_singleton",
                  "test_no_instance_dict"],
    },
    "M8-2": {
        "red": ["test_present_unset_is_a_shared_singleton"],
        "green": ["test_assignment_rejected", "test_deletion_rejected",
                  "test_mutating_a_miss_raises", "test_poisoning_attempt",
                  "test_missing_is_a_shared_singleton"],
    },
    "M8-3": {
        "red": ["test_result_exposes_no_binding",
                "test_of_value_takes_no_binding_argument",
                "test_present_unset_takes_no_binding_argument"],
        "green": ["test_assignment_rejected", "test_deletion_rejected",
                  "test_missing_is_a_shared_singleton"],
    },
    "M8-4": {
        "red": ["test_missing_is_a_shared_singleton"],
        # THE discrimination row: poisoning pins must NOT notice allocation.
        "green": ["test_mutating_a_miss_raises", "test_poisoning_attempt",
                  "test_assignment_rejected", "test_deletion_rejected",
                  "test_present_unset_is_a_shared_singleton"],
    },
    "M8-5": {
        "red": ["test_equality_is_status_and_value",
                "test_all_declared_unset_results_are_equal"],
        "green": ["test_assignment_rejected", "test_deletion_rejected",
                  "test_poisoning_attempt", "test_result_exposes_no_binding"],
    },
}


def run(mutation: str) -> tuple[set[str], set[str], int]:
    """Run the pin suite under one mutation. Returns (red, green, rc)."""
    env = dict(os.environ, PYTHONPATH=f"{WORKTREE}:{PLUGIN_DIR}",
               M8_MUTATION=mutation)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", PIN_FILE, "-p", "m8_plugin",
         "-q", "--no-header", "-p", "no:cacheprovider", "--tb=no", "-rf"],
        cwd=WORKTREE, capture_output=True, text=True, env=env)
    red = set()
    for line in proc.stdout.splitlines():
        if line.startswith("FAILED "):
            cell = line.split(" ", 1)[1].split(" - ")[0].strip()
            red.add(cell.split("::", 1)[1] if "::" in cell else cell)
    collected = 0
    for line in proc.stdout.splitlines():
        if " passed" in line or " failed" in line:
            collected = 1
    return red, set(), proc.returncode if collected else -1


def main() -> int:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WORKTREE,
                         capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=WORKTREE,
                           capture_output=True, text=True).stdout.strip()
    print("M8 mutation locks — slot 4B.1")
    print(f"SHA: {sha}")
    print(f"worktree dirty: {'YES' if dirty else 'no'}")
    if dirty:
        for line in dirty.splitlines():
            print(f"    {line}")
    print(f"python: {sys.version.split()[0]}")
    print("=" * 82)

    print("\n--- CONTROL: no mutation (must be fully green) ---")
    red, _g, rc = run("NONE")
    print(f"    rc={rc}  red cells={len(red)}")
    if red or rc != 0:
        print("    CONTROL FAILED — every comparison below is unsound.")
        for cell in sorted(red):
            print(f"      {cell}")
        return 1
    print("    control clean")

    verdicts = []
    for key in sorted(EXPECT):
        from m8_plugin import MUTATIONS
        label = MUTATIONS[key][0]
        red, _g, rc = run(key)
        exp = EXPECT[key]

        missing_red = [pat for pat in exp["red"]
                       if not any(pat in cell for cell in red)]
        wrongly_red = [pat for pat in exp["green"]
                       if any(pat in cell for cell in red)]
        ok = not missing_red and not wrongly_red and red

        print(f"\n--- {key}: {label} ---")
        print(f"    red cells: {len(red)}")
        for cell in sorted(red)[:8]:
            print(f"      RED  {cell}")
        if len(red) > 8:
            print(f"      ... and {len(red) - 8} more")
        if missing_red:
            print(f"    EXPECTED-RED BUT GREEN: {missing_red}")
        if wrongly_red:
            print(f"    EXPECTED-GREEN BUT RED (lock does not discriminate): "
                  f"{wrongly_red}")
        print(f"    VERDICT: {'LOCK HOLDS' if ok else 'LOCK FAILED'}")
        verdicts.append((key, ok, len(red)))

    print("\n" + "=" * 82)
    print(f"{'lock':8s} {'red cells':>10s}  verdict")
    for key, ok, n in verdicts:
        print(f"{key:8s} {n:10d}  {'HOLDS' if ok else 'FAILED'}")
    held = sum(1 for _k, ok, _n in verdicts if ok)
    print(f"\n{held}/{len(verdicts)} locks hold")
    return 0 if held == len(verdicts) else 1


if __name__ == "__main__":
    sys.path.insert(0, PLUGIN_DIR)
    raise SystemExit(main())
