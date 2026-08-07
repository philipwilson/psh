#!/usr/bin/env python3
"""4A.2 M8 mutation locks: each load-bearing arm fails for its OWN reason.

A pin suite that dies wholesale under every mutation has not localised
anything.  This applies one mutation at a time to the FIXED `psh/shell.py`
inside a throwaway checkout, runs the slot's pin file there, and prints the set
of tests each mutation kills.  A mutation that kills NOTHING is an unpinned
arm; two mutations that kill the SAME set are not independently pinned.

Runs entirely inside `tmp/m8-probe` (a detached worktree this script creates
and removes), never in the live worktree.

    python tmp/w4a2-probes/mutate_m8.py
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "tmp" / "m8-probe"
PIN = "tests/unit/core/test_shutdown_phases_4a2.py"
SEAM_PIN = ("tests/conformance/bash/"
            "test_exit_trap_status_precedence_conformance.py")

#: (id, description, (pattern, replacement)) applied to psh/shell.py
MUTATIONS = [
    ("M8-a", "drop the history phase from the phase list",
     ("                            ('history', self._shutdown_save_history),\n", "")),
    ("M8-b", "drop the job-disposition phase from the phase list",
     ("('jobs', self._shutdown_dispose_jobs)", "('jobs', lambda reason: None)")),
    ("M8-c", "stop HOLDING: let a phase exception propagate (the base defect)",
     ("            except BaseException as exc:  # noqa: BLE001 - held, then re-raised",
      "            except _NeverRaised as exc:  # MUTANT: nothing is held")),
    ("M8-d", "hold only SystemExit, so a phase FAILURE still cancels the rest",
     ("            except BaseException as exc:  # noqa: BLE001 - held, then re-raised",
      "            except SystemExit as exc:  # MUTANT: narrowed")),
    ("M8-e", "re-raise the held signal OUTSIDE the close() finally",
     ("        try:\n            held = self._run_shutdown_phases(reason)\n"
      "            if held is not None:\n                raise held\n"
      "        finally:\n            self.close()\n",
      "        held = self._run_shutdown_phases(reason)\n"
      "        self.close()\n"
      "        if held is not None:\n            raise held\n")),
    ("M8-f", "drop the second-failure note",
     ("                    held.add_note(f\"shutdown phase {name!r} also failed: \"\n"
      "                                  f\"{detail}\")",
      "                    pass  # MUTANT: second failure vanishes")),
    ("M8-g", "make history save on EVERY route (drop the route gate)",
     ("        if reason not in self._HISTORY_SAVING_SHUTDOWNS:\n            return\n",
      "        pass  # MUTANT: route gate dropped\n")),
    # M8-h models the PRE-FIX narrowed shape in FULL: close() only after the
    # phase loop returns AND an unguarded note render. Reverting only the
    # finally leaves the defensive note in place, and then nothing escapes --
    # so a one-half mutation kills nothing and would wrongly read as an
    # unpinned arm. The two halves are one defense; the mutation is too.
    ("M8-h", "restore the narrowed close() shape AND the unguarded note",
     ("                    try:\n                        detail = f\"{type(exc).__name__}: {exc}\"\n"
      "                    except BaseException:  # noqa: BLE001 - unrenderable\n"
      "                        detail = f\"{type(exc).__name__} (unrenderable)\"\n",
      "                    detail = f\"{type(exc).__name__}: {exc}\"  # MUTANT\n")),
]

#: Mutations on the R4 scope extension (the bare-exit-in-EXIT-trap seam).
SEAM_MUTATIONS = [
    ("M8-i", "psh/builtins/core.py", "bare exit ignores the trap-entry status",
     ("        entry_status = shell.trap_manager.exit_trap_entry_status\n"
      "        if entry_status is not None:\n"
      "            exit_code = entry_status\n",
      "        pass  # MUTANT: entry status ignored\n")),
    ("M8-j", "psh/core/trap_manager.py",
     "GENERALIZE the saved status to every trap (the ruled-out design)",
     ("            self._exit_trap_entry_status = (\n"
      "                saved_exit_code if signal_name == 'EXIT' else None)",
      "            self._exit_trap_entry_status = saved_exit_code  # MUTANT")),
]

PRELUDE = "class _NeverRaised(BaseException):\n    pass\n\n\n"


def run_pins(pin=PIN) -> set:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", pin, "-q", "--no-header", "-p",
         "no:randomly"],
        cwd=PROBE, capture_output=True, text=True, timeout=600)
    # Capture the FULL node id, brackets included: `(\w+)` stops at the
    # `[` of a parametrized id, which collapsed 21 failing rows into one
    # name and made a seam mutation read as "kills 1".
    return set(re.findall(r"^FAILED [^:]+::(\S+)", proc.stdout, re.M)), proc


def main() -> int:
    if PROBE.exists():
        subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force",
                        str(PROBE)], capture_output=True)
    subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach",
                    str(PROBE), "HEAD"], check=True, capture_output=True)
    try:
        # Install the FIXED tree's files (they are uncommitted in the live
        # worktree, so the checkout alone would not carry them).
        for rel in ("psh/shell.py", "psh/builtins/core.py",
                    "psh/core/trap_manager.py", PIN, SEAM_PIN,
                    "tests/conftest.py"):
            shutil.copy2(ROOT / rel, PROBE / rel)
        pristine = (PROBE / "psh/shell.py").read_text()

        baseline, proc = run_pins()
        print(f"# unmutated pin run: failures={sorted(baseline) or 'none'}")
        if baseline:
            print(proc.stdout[-2000:])
            return 1
        print()

        seen = {}
        rc = 0
        for mid, desc, (pattern, repl) in MUTATIONS:
            if pattern not in pristine:
                print(f"{mid}  !! PATTERN NOT FOUND — mutation never applied")
                rc = 1
                continue
            mutated = pristine.replace(pattern, repl, 1)
            if mid == "M8-h":
                mutated = mutated.replace(
                    "        try:\n            held = self._run_shutdown_phases(reason)\n"
                    "            if held is not None:\n                raise held\n"
                    "        finally:\n            self.close()\n",
                    "        held = self._run_shutdown_phases(reason)\n"
                    "        if held is not None:\n"
                    "            try:\n                raise held\n"
                    "            finally:\n                self.close()\n"
                    "        self.close()\n", 1)
            if mid == "M8-c":
                mutated = mutated.replace("class Shell", PRELUDE + "class Shell", 1)
            (PROBE / "psh/shell.py").write_text(mutated)
            killed, _ = run_pins()
            (PROBE / "psh/shell.py").write_text(pristine)
            if not killed:
                print(f"{mid}  !! KILLED NOTHING ({desc}) — arm is UNPINNED")
                rc = 1
                continue
            dup = [other for other, s in seen.items() if s == killed]
            seen[mid] = killed
            note = f"  <-- SAME SET AS {dup}" if dup else ""
            print(f"{mid}  {desc}")
            print(f"       kills ({len(killed)}): {', '.join(sorted(killed))}{note}")
            if dup:
                rc = 1

        # --- the R4 seam (bare exit in an EXIT trap) -----------------------
        print()
        seam_pristine = {rel: (PROBE / rel).read_text()
                         for _, rel, _, _ in SEAM_MUTATIONS}
        base_seam, _ = run_pins(SEAM_PIN)
        print(f"# unmutated seam pin run: failures={sorted(base_seam) or 'none'}")
        if base_seam:
            return 1
        for mid, rel, desc, (pattern, repl) in SEAM_MUTATIONS:
            src = seam_pristine[rel]
            if pattern not in src:
                print(f"{mid}  !! PATTERN NOT FOUND in {rel}")
                rc = 1
                continue
            (PROBE / rel).write_text(src.replace(pattern, repl, 1))
            killed, _ = run_pins(SEAM_PIN)
            collateral, _ = run_pins(PIN)
            (PROBE / rel).write_text(src)
            if not killed:
                print(f"{mid}  !! KILLED NOTHING ({desc}) — seam UNPINNED")
                rc = 1
                continue
            print(f"{mid}  {desc}  [{rel}]")
            print(f"       kills {len(killed)} precedence pin(s); "
                  f"collateral in the phase battery: {len(collateral)}")
        return rc
    finally:
        subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force",
                        str(PROBE)], capture_output=True)


if __name__ == "__main__":
    sys.exit(main())
