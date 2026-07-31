#!/usr/bin/env python3
"""MUTATION PROOF for the certification instrument itself (ruling R12-D).

A certification script is only worth its green tally if a FALSE row makes it
red. Version 1 of certify_ledger.py was mutation-proved against four synthetic
false-row classes (bad grep / bad absent / missing test / stale anchor) and
still certified two false rows 40/40, because the mutations tested the
CHECKING and the defect was in the ANCHORING. So this harness replays those
four classes AND the two that actually escaped:

  MUT-E is the retired N13 row VERBATIM -- grep `seeded from LEXER EVENTS` in
  psh/parser/session.py -- which certified an ordered comment fix with a
  pattern that predated it. Under the `since` rule it must now go red.

  MUT-I is the same defect in testid form: a pin row naming a test that
  already existed at `since`.

  MUT-G/MUT-H are the N18 class, caught by self_check() before any row is
  evaluated: a claim about test code answered by production text, and a
  tree-change row with no `since` SHA at all.

Every mutation asserts the SPECIFIC failure reason, not merely non-zero exit:
a mutation that fails for the wrong reason proves nothing.

Usage: python3 tmp/r2-5-probes/mutation_certify.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("cert", HERE / "certify_ledger.py")
cert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cert)

R, BASE, R6TIP = cert.R, cert.BASE, cert.R6TIP

# (id, row, expect-in-detail). None row => self_check mutation.
ROW_MUTATIONS = [
    ("MUT-A false grep (pattern absent at HEAD)",
     R("guard pin", "grep", "psh/parser/session.py",
       "this text is not in the file", BASE),
     "NOT FOUND at HEAD"),
    ("MUT-B false absent (pattern present at HEAD)",
     R("x", "absent", "psh/parser/session.py", "_lexer_pending_heredocs",
       BASE),
     "STILL PRESENT at HEAD"),
    ("MUT-C nonexistent test node id",
     R("x", "testid", "tests/unit/io_redirect/test_heredoc_executable_type.py"
       "::test_this_test_does_not_exist", "", R6TIP),
     "does not collect"),
    ("MUT-D anchor not self-stamping HEAD",
     R("x", "anchor", "base-tip-identity-r5.txt"),
     "does NOT self-stamp"),
    ("MUT-E THE RETIRED N13 ROW (pattern predates the change)",
     R("x", "grep", "psh/parser/session.py", "seeded from LEXER EVENTS",
       R6TIP),
     "NOT AN ORDERED CHANGE"),
    ("MUT-F removal that was already removed",
     R("x", "absent", "psh/parser/session.py", "text never in this file",
       R6TIP),
     "NOT AN ORDERED REMOVAL"),
    ("MUT-I pin row naming a test that predates `since`",
     R("x", "testid", "tests/unit/io_redirect/test_heredoc_executable_type.py"
       "::test_redirect_heredoc_rejects_the_non_executable_state", "", R6TIP),
     "NOT AN ORDERED ADDITION"),
]

SELF_CHECK_MUTATIONS = [
    ("MUT-G THE N18 CLASS (test claim answered by production text)",
     R("N18 offender row for the arm", "grep",
       "psh/io_redirect/file_redirect.py", "carries no content", R6TIP),
     "the N18 class"),
    ("MUT-H tree-change row with no `since`",
     R("some doc row", "grep", "psh/parser/session.py",
       "_lexer_pending_heredocs"),
     "the N13 class"),
]


def main():
    print(f"MUTATION PROOF — certify_ledger.py at HEAD {cert.HEAD[:8]}\n")
    failures = 0

    baseline = cert.self_check()
    print(f"[baseline] self_check on the REAL rows: "
          f"{'clean' if not baseline else baseline}")
    if baseline:
        failures += 1

    print("\n--- per-row checks (each must go RED for its OWN reason) ---")
    for name, row, expect in ROW_MUTATIONS:
        ok, detail = cert.check(row)
        good = (not ok) and expect in detail
        print(f"  [{'PASS' if good else 'FAIL'}] {name}")
        print(f"         -> ok={ok}  detail={detail[:88]}")
        if not good:
            failures += 1

    print("\n--- self_check rules (must reject BEFORE any row is evaluated) ---")
    real = cert.ROWS
    for name, row, expect in SELF_CHECK_MUTATIONS:
        cert.ROWS = real + [row]
        problems = cert.self_check()
        good = any(expect in p for p in problems)
        print(f"  [{'PASS' if good else 'FAIL'}] {name}")
        print(f"         -> {problems[-1][:88] if problems else 'NOT REJECTED'}")
        if not good:
            failures += 1
    cert.ROWS = real

    # A false-FAIL check: the four classes above must not be so strict that a
    # GENUINE row trips them. Round 6 found the first version's `error`-in-
    # stdout detector false-FAILing two real rows, so this direction matters.
    print("\n--- false-FAIL control (a genuine row must stay green) ---")
    genuine = R("N13(a) session step numbers correct", "grep",
                "psh/parser/session.py", "trial parse at step 5", R6TIP)
    ok, detail = cert.check(genuine)
    print(f"  [{'PASS' if ok else 'FAIL'}] genuine ordered row -> {detail[:70]}")
    if not ok:
        failures += 1

    print(f"\nVERDICT: {'PASS — every false-row class is caught' if not failures else f'FAIL ({failures})'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
