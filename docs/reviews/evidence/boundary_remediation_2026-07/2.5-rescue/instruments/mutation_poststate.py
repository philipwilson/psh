#!/usr/bin/env python3
"""HISTORICAL PROOF for the post-state rows (ruling R12-D-AMENDED).

The amendment's claim is specific and testable: "an `absent`-kind row over the
stale phrasing would have FAILED all three times where edit-presence greps
passed." A predicate that passes at HEAD proves nothing about that -- so this
harness runs each post-state predicate against the ACTUAL HISTORICAL TREES at
the tips those audits certified, and asserts it goes RED there.

That is the difference between a guard and a decoration, and it is the same
demonstration `mutation_certify.py` does for the `since` rule, pushed back
through the slot's own history rather than through synthetic rows.

Each predicate is also run at HEAD and asserted GREEN, so a predicate that is
simply broken (red everywhere) cannot masquerade as a working guard.

Worktrees are created detached, used read-only, and removed.

Usage: python3 tmp/r2-5-probes/mutation_poststate.py
"""
import importlib.util
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
MAIN = pathlib.Path("/Users/pwilson/src/psh-r2-5")

spec = importlib.util.spec_from_file_location("cert", HERE / "certify_ledger.py")
cert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cert)

# (sha, label, which predicates MUST be red there and why)
HISTORY = [
    ("abd98d50", "tip dissolved by round 5",
     {"session-step-numbers": "N13 had not landed at all",
      "oracle-scan-claim": "N9 had not landed at all",
      "latency-claims-scoped": "the unqualified latency claim was shipped"}),
    ("ec99b420", "tip dissolved by round 6 -- certified 40/40",
     {"session-step-numbers": "N13 still untouched; 'parse at step 4' present",
      "oracle-scan-claim": "open_heredoc_specs' docstring still stale",
      "latency-claims-scoped": "all three texts still over-claimed"}),
]


def run_at(root):
    """Run every postcheck with ROOT pointed at *root*."""
    saved = cert.ROOT
    cert.ROOT = pathlib.Path(root)
    try:
        return {name: fn(None) for name, fn in cert.POSTCHECKS.items()}
    finally:
        cert.ROOT = saved


def main():
    print(f"HISTORICAL POST-STATE PROOF — HEAD {cert.HEAD[:8]}\n")
    failures = 0

    print("--- at HEAD: every predicate must be GREEN ---")
    for name, (ok, detail) in sorted(run_at(MAIN).items()):
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:24} {detail[:70]}")
        if not ok:
            failures += 1

    for sha, label, expect_red in HISTORY:
        wt = f"/private/tmp/remv-poststate-{sha}"
        subprocess.run(["git", "worktree", "add", "--detach", wt, sha],
                       cwd=MAIN, capture_output=True, text=True)
        try:
            print(f"\n--- at {sha} ({label}) ---")
            results = run_at(wt)
            for name, why in sorted(expect_red.items()):
                ok, detail = results[name]
                good = not ok          # MUST be red here
                print(f"  [{'PASS' if good else 'FAIL'}] {name:24} "
                      f"{'RED as required' if good else 'GREEN — PROVES NOTHING'}")
                print(f"         expected red because: {why}")
                print(f"         predicate said: {detail[:76]}")
                if not good:
                    failures += 1
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", wt],
                           cwd=MAIN, capture_output=True, text=True)

    print(f"\nVERDICT: {'PASS — each post-state row would have caught its own false discharge' if not failures else f'FAIL ({failures})'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
