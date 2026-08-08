#!/usr/bin/env python3
"""Instrument 14 (slot 5B.2) — mutation proof for the instance-assignment arm.

Four arms. Each RED arm asserts the failure REASON, not merely that something
failed (5B.1 lesson 2: a wrong-reason arm nearly survived there), and every
subprocess runs with ``PYTHONDONTWRITEBYTECODE=1`` (lesson 1: same-length
edits defeat pyc mtime+size invalidation, and a transcript lied until chased).

  A  plant a smuggled store in a REAL scanned module -> ratchet must go RED,
     naming the planted def as an unrecorded full-Shell consumer
  B  plant a NARROWING in the same place            -> ratchet must stay GREEN
     (the control: the arm must not flag the migration it exists to encourage)
  C  neuter the arm, replant A's offender           -> ratchet must go GREEN
     again, proving arm A's red came FROM this arm and not from something else
  D  plant an underscore-spelled store              -> RED (the core/scope.py
     spelling, which a `self.shell`-only grammar would miss)

Files are restored from an in-memory backup, never with ``git checkout`` (that
is banned over uncommitted work).

Usage:  python 14_detector_arm_mutation.py <ROOT>
"""
import os
import pathlib
import subprocess
import sys

RATCHET = "tests/unit/tooling/test_shell_consumer_ratchet_q1.py"
VICTIM = "psh/expansion/procsub_render.py"      # scanned, and holds no shell today


def run_ratchet(root):
    r = subprocess.run(
        [sys.executable, "-m", "pytest", RATCHET, "-q",
         "-k", "no_unrecorded or only_shrinks or adds_no_allowlist"],
        cwd=str(root), capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(root),
             "PYTHONDONTWRITEBYTECODE": "1"})
    return r.returncode, r.stdout + r.stderr


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    print(f"ROOT={root}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    print()

    victim = root / VICTIM
    ratchet = root / RATCHET
    victim_backup = victim.read_text()
    ratchet_backup = ratchet.read_text()

    results = []
    try:
        # --- baseline -----------------------------------------------------
        rc, out = run_ratchet(root)
        print(f"BASELINE (unmutated): rc={rc}")
        assert rc == 0, "baseline is not green; mutation results would be noise"
        print()

        # --- ARM A: smuggled store in a real scanned module ---------------
        victim.write_text(victim_backup + (
            "\n\nclass _MutationProbe:\n"
            "    def wire(self, s):\n"
            "        self.shell = s\n"))
        rc, out = run_ratchet(root)
        reason_ok = ("New full-`Shell` consumer" in out
                     and "_MutationProbe.wire" in out)
        print(f"ARM A  plant smuggled store   : rc={rc}  "
              f"reason_named={reason_ok}")
        print(f"       expected RED naming the def -> "
              f"{'PASS' if rc != 0 and reason_ok else 'FAIL'}")
        results.append(("A", rc != 0 and reason_ok))
        victim.write_text(victim_backup)

        # --- ARM B: narrowing control -------------------------------------
        victim.write_text(victim_backup + (
            "\n\nclass _MutationProbe:\n"
            "    def wire(self, s):\n"
            "        self.mgr = s.expansion_manager\n"
            "        self.state = s.state\n"))
        rc, out = run_ratchet(root)
        print(f"ARM B  plant NARROWING        : rc={rc}")
        print(f"       expected GREEN (must not flag the fix) -> "
              f"{'PASS' if rc == 0 else 'FAIL'}")
        results.append(("B", rc == 0))
        victim.write_text(victim_backup)

        # --- ARM C: neuter the arm, replant A -----------------------------
        neutered = ratchet_backup.replace(
            "                ) or _stores_shell_by_assignment(child)",
            "                )")
        assert neutered != ratchet_backup, "arm-neutering edit did not apply"
        ratchet.write_text(neutered)
        victim.write_text(victim_backup + (
            "\n\nclass _MutationProbe:\n"
            "    def wire(self, s):\n"
            "        self.shell = s\n"))
        rc, out = run_ratchet(root)
        print(f"ARM C  arm neutered + offender: rc={rc}")
        print(f"       expected GREEN (proves A's red came from THIS arm) -> "
              f"{'PASS' if rc == 0 else 'FAIL'}")
        results.append(("C", rc == 0))
        ratchet.write_text(ratchet_backup)
        victim.write_text(victim_backup)

        # --- ARM D: underscore spelling -----------------------------------
        victim.write_text(victim_backup + (
            "\n\nclass _MutationProbe:\n"
            "    def set_shell(self, s):\n"
            "        self._shell = s\n"))
        rc, out = run_ratchet(root)
        reason_ok = ("New full-`Shell` consumer" in out
                     and "_MutationProbe.set_shell" in out)
        print(f"ARM D  underscore spelling    : rc={rc}  "
              f"reason_named={reason_ok}")
        print(f"       expected RED -> "
              f"{'PASS' if rc != 0 and reason_ok else 'FAIL'}")
        results.append(("D", rc != 0 and reason_ok))
        victim.write_text(victim_backup)

    finally:
        victim.write_text(victim_backup)
        ratchet.write_text(ratchet_backup)

    print()
    print("=" * 74)
    for name, ok in results:
        print(f"  ARM {name}: {'PASS' if ok else 'FAIL'}")
    print(f"  {sum(1 for _, ok in results if ok)}/{len(results)} arms as designed")
    print("=" * 74)
    print()
    # restoration proof
    print("RESTORED byte-identical:",
          victim.read_text() == victim_backup
          and ratchet.read_text() == ratchet_backup)
    rc, _ = run_ratchet(root)
    print(f"post-restore ratchet rc={rc} (must be 0)")


if __name__ == "__main__":
    main()
