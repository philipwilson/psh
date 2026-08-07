"""Re-derivable red-on-base measurement for slot 4A.1's pin files.

RETAINED instrument (R8 "recorded" item: the ratios must be re-derivable).
An earlier hand-run of this measurement was taken BEFORE the composition
cells and the lock-closing pins were added, so its 19/7 figure did not
cover the whole shipped file — this script re-derives every ratio from
scratch, at a detached base checkout, and prints per-test outcomes so a
row-level claim (BL-5) can be made rather than a file-level one.

    python red_on_base.py <base-checkout> [<worktree>]

The SHIM is the point of the instrument. `LeaseRestoreError` and
`ComponentKind.MANAGED_SIGNALS` do not exist at a64eb6e8, so an unshimmed
copy errors at IMPORT and every cell then "fails" for one uninformative
reason. Aliasing them lets each cell fail for its own reason. The shim is
applied ONLY to the base copy, never to the shipped file.
"""
import os
import re
import shutil
import subprocess
import sys

WORKTREE_DEFAULT = "/Users/pwilson/src/psh-r4a-1"

PIN_FILES = [
    "tests/unit/core/test_activation_transaction_4a1.py",
    "tests/integration/redirection/test_failed_exec_lease_4a1.py",
    "tests/unit/interactive/test_managed_signal_lease_4a1.py",
]

SHIM = '''
# --- BASE-RUN SHIM (red_on_base.py) — never present in the shipped file ---
# Supplies ONLY the names whose ABSENCE would stop the module or the fixture
# from running at all. Post-fix BEHAVIOUR is never emulated: a cell that
# depends on the fix must still fail at base, for its own reason.
import psh.core.process_lease as _pl
if not hasattr(_pl, 'LeaseRestoreError'):
    _pl.LeaseRestoreError = _pl.LeaseError
if not hasattr(_pl.ComponentKind, 'MANAGED_SIGNALS'):
    class _MS:
        name = 'MANAGED_SIGNALS'
    _pl.ComponentKind.MANAGED_SIGNALS = _MS()
if not hasattr(_pl.ProcessLeaseCoordinator, '_quarantined'):
    # The coordinator fixture saves/restores this list. Without it every
    # test ERRORS at setup and the file reports no per-cell signal at all —
    # which is the failure mode this whole instrument exists to avoid.
    _pl.ProcessLeaseCoordinator._quarantined = []
# --- end shim ---
'''


def shim_source(text):
    """Insert the shim BEFORE the module's first import, after its docstring.

    It must precede the imports, not follow them: the pin files import the
    post-fix names directly (`from psh.core.process_lease import
    LeaseRestoreError`), so a shim placed afterwards never runs. Located via
    the AST rather than by scanning for import lines — a first draft matched
    the opening line of a PARENTHESIZED multi-line import and inserted into
    the middle of it, producing a SyntaxError that read as "0 red" for the
    whole file.
    """
    import ast

    tree = ast.parse(text)
    body = tree.body
    first = 0
    if body and isinstance(body[0], ast.Expr) and isinstance(
            getattr(body[0], 'value', None), ast.Constant) and isinstance(
            body[0].value.value, str):
        first = 1                      # skip the module docstring
    insert_line = body[first].lineno - 1 if len(body) > first else len(
        text.splitlines())
    lines = text.splitlines(keepends=True)
    lines.insert(insert_line, SHIM)
    return "".join(lines)


def run(base, worktree):
    print(f"# base checkout: {base}")
    print(f"# base sha:      "
          f"{subprocess.run(['git', '-C', base, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()}")
    print(f"# worktree:      {worktree}")
    totals = {}
    for rel in PIN_FILES:
        src = open(os.path.join(worktree, rel)).read()
        dest = os.path.join(base, rel)
        open(dest, "w").write(shim_source(src))
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", rel, "-q", "-p", "no:randomly",
                 "--tb=no", "-rf"],
                cwd=base, capture_output=True, text=True, timeout=600)
        finally:
            os.remove(dest)
        failed = sorted({ln.split("::")[-1].split()[0]
                         for ln in proc.stdout.splitlines()
                         if ln.startswith("FAILED")})
        tail = [ln for ln in proc.stdout.splitlines()
                if re.search(r"\d+ (passed|failed)", ln)]
        summary = tail[-1] if tail else "NO SUMMARY"
        m = re.search(r"(?:(\d+) failed)?,? ?(\d+) passed", summary)
        nf = int(m.group(1) or 0) if m else -1
        npass = int(m.group(2) or 0) if m else -1
        totals[rel] = (nf, npass)
        print(f"\n## {rel}")
        print(f"   base: {summary}")
        print(f"   RED at base ({len(failed)}):")
        for name in failed:
            print(f"     - {name}")
        print(f"   GREEN at base (must-holds) = {npass}")
    print("\n=== DERIVED ===")
    for rel, (nf, npass) in totals.items():
        print(f"{nf:3d} red / {npass:3d} green   {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1],
                         sys.argv[2] if len(sys.argv) > 2 else WORKTREE_DEFAULT))
