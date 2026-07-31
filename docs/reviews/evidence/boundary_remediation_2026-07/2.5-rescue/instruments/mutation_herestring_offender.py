#!/usr/bin/env python3
"""MUTATION PROOF for the operand-less `{v}<<<` offender row (ruling R12-C).

Round 6 blocker 2: the `<<<` typed arm in
`psh/io_redirect/file_redirect.py#FileRedirector.apply_var_fd_redirect` had no
offender test anywhere in tests/ — deleting the arm left 195 tests green, so
the arm was unproven and the ledger's "offender rows both arms" claim had no
tree evidence. This script proves the NEW row bites: it deletes the arm from
the tree, runs the suite, and restores.

An arm-exists grep can never prove this; only removing the arm can. Run:

    python3 tmp/r2-5-probes/mutation_herestring_offender.py

Self-stamps the SHA it ran at. Restores the tree and VERIFIES the restore with
`git diff --exit-code` before exiting (a mutation probe that leaves the tree
dirty is worse than no probe).
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path("/Users/pwilson/src/psh-r2-5")
SRC = ROOT / "psh" / "io_redirect" / "file_redirect.py"
NEW_ROWS = (
    "tests/unit/io_redirect/test_heredoc_executable_type.py"
    "::test_operand_less_here_string_offender_raises_typed_on_the_var_fd_route"
)
SCOPE = [
    "tests/unit/io_redirect/",
    "tests/unit/lexer/test_fd_prefix_table_parity.py",
    "tests/unit/scripting/test_heredoc_declared_deltas_noninteractive.py",
]

ARM = """            if rtype == '<<<' and redirect.target is None \\
                    and getattr(redirect, 'target_word', None) is None:
                # The here-string twin of the arm above: an operand-less
                # `{v}<<<` reaching execution is the same non-executable parse
                # state, and died on a raw AttributeError from the None target.
                raise NonExecutableRedirectError(
                    f"here-string `{{{name}}}{rtype}` has no operand, so there "
                    "is nothing to redirect from.")
"""


def run(args):
    return subprocess.run([sys.executable, "-m", "pytest", *args, "-q",
                           "-p", "no:randomly"], cwd=ROOT,
                          capture_output=True, text=True)


def summary(r):
    lines = [ln for ln in r.stdout.splitlines() if " passed" in ln
             or " failed" in ln or " error" in ln]
    return lines[-1] if lines else r.stdout[-200:]


def main():
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    print(f"MUTATION PROOF — operand-less `{{v}}<<<` typed arm")
    print(f"tree: {ROOT}   SHA: {head}")

    original = SRC.read_text()
    if ARM not in original:
        print("FATAL: arm text not found — the source moved; update ARM.")
        return 2

    print(f"\n[1] UNMUTATED (arm present), row: {NEW_ROWS.split('::')[1]}")
    print("    " + summary(run([NEW_ROWS])))
    print("[2] UNMUTATED, full scope")
    print("    " + summary(run(SCOPE)))

    SRC.write_text(original.replace(ARM, ""))
    try:
        print("\n[3] MUTATED (arm DELETED), the new row — MUST be RED")
        r = run([NEW_ROWS])
        print("    " + summary(r))
        mutated_red = r.returncode != 0
        print("[4] MUTATED, full scope — records what else notices")
        print("    " + summary(run(SCOPE)))
    finally:
        SRC.write_text(original)

    clean = subprocess.run(["git", "diff", "--exit-code", "--", str(SRC)],
                           cwd=ROOT, capture_output=True, text=True)
    print(f"\n[5] RESTORED: git diff --exit-code -> rc={clean.returncode} "
          f"({'clean' if clean.returncode == 0 else 'DIRTY — INVESTIGATE'})")

    ok = mutated_red and clean.returncode == 0
    print(f"\nVERDICT: {'PASS — the arm is guarded' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
