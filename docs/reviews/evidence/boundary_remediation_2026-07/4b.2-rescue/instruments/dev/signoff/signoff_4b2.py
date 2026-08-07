#!/usr/bin/env python3
"""Slot 4B.2 dev sign-off — the six legs defined in D10.

Deliberately NOT placed in tmp/w4b2/: that tree was declared FINAL with a
self-excluding manifest, and adding a file to it after the declaration would
mutate a declared artifact.

Every leg runs at a DETACHED checkout of the TAG, created fresh (so `tmp/` is
ABSENT, which is BL-1's mandated environment) and removed afterwards. Leg 1
gates the rest: if the child does not import the tag checkout's own module, the
whole sign-off ABORTS rather than reporting numbers for the wrong tree (F-4).

Usage:  python signoff_4b2.py <tag-or-sha>
"""
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORKTREE = os.path.dirname(os.path.dirname(HERE))   # the dev worktree
BASELINE = os.path.join(WORKTREE, 'tmp', 'w4b2', 'i10_carry21_BASE_clean.txt')

DEFECT_CELLS = [
    # 6 seam split-identity (RED at base)
    *[f"tests/unit/builtins/test_input_decoder_seam_4b2.py::"
      f"TestSplitCharIdentityAcrossSeam::"
      f"test_split_character_survives_the_bulk_drain[{cid}]"
      for cid in ("e_acute-split1", "euro-split1", "euro-split2",
                  "smile-split1", "smile-split2", "smile-split3")],
    # 8 rider (RED at base)
    *[f"tests/unit/builtins/test_read_exact_timeout_4b2.py::{cls}::{node}"
      for cls, node in [
          ("TestRiderParityFull", "test_no_input_and_no_eof_times_out"),
          ("TestRiderParityFull", "test_partial_input_and_no_eof_assigns_the_partial"),
          ("TestRiderParityFull", "test_input_arriving_after_the_read_is_not_consumed"),
          ("TestRiderParityFull", "test_deadline_wins_over_a_later_eof"),
          ("TestRiderRcParityWithDeclaredNew1Residue", "test_two_byte_char_split_by_the_deadline"),
          ("TestRiderRcParityWithDeclaredNew1Residue", "test_three_byte_char_split_by_the_deadline"),
          ("TestRiderRcParityWithDeclaredNew1Residue", "test_continuation_byte_arrives_after_the_read"),
      ]],
    "tests/unit/builtins/test_read_exact_timeout_4b2.py::"
    "TestNew2CountModelDivergesInStatusTooCharacterization::"
    "test_backslash_under_deadline_diverges_in_rc_and_value",
    # 5 end-to-end (RED at base)
    *[f"tests/system/test_read_seam_end_to_end_4b2.py::{cls}::{node}"
      for cls, node in [
          ("TestSeamEndToEndCharacterIdentity",
           "test_split_character_keeps_its_identity_through_mapfile[e_acute-2byte]"),
          ("TestSeamEndToEndCharacterIdentity",
           "test_split_character_keeps_its_identity_through_mapfile[euro-3byte]"),
          ("TestSeamEndToEndCharacterIdentity",
           "test_split_character_keeps_its_identity_through_mapfile[smile-4byte]"),
          ("TestRiderEndToEndFromAScriptFile",
           "test_exact_count_honors_the_deadline_with_no_input"),
          ("TestRiderEndToEndFromAScriptFile",
           "test_exact_count_honors_the_deadline_with_partial_input"),
      ]],
    # 3 PTY (2 RED at base + its control)
    *[f"tests/system/interactive/test_pty_read_exact_timeout_4b2.py::{n}"
      for n in ("test_exact_count_honors_the_deadline_at_a_tty",
                "test_exact_count_assigns_the_partial_at_a_tty",
                "test_full_count_before_the_deadline_at_a_tty")],
]

MUST_HOLD_FILES = [
    "tests/unit/builtins/test_input_decoder_seam_4b2.py",
    "tests/unit/builtins/test_read_exact_timeout_4b2.py",
    "tests/system/test_read_seam_end_to_end_4b2.py",
    "tests/conformance/bash/test_cv_carry_characterization.py::"
    "TestMixedValidMalformedExactCountHybrid",
    "tests/unit/builtins/test_input_reader.py",
    "tests/unit/builtins/test_input_reader_record_bytes.py",
    "tests/unit/builtins/test_input_cursor_i1.py",
    "tests/unit/builtins/test_read_advanced.py",
    "tests/unit/builtins/test_mapfile.py",
    "tests/unit/builtins/test_read_unified_quirks.py",
    "tests/unit/io_redirect/test_input_cursor_registry_drops_i2.py",
    "tests/integration/redirection/test_input_cursor_identity_i1.py",
    "tests/system/test_read_malformed_bytes_i1.py",
]


def sh(cmd, cwd=None, **kw):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          errors="replace", **kw)


def emit(cmd, result, note=""):
    """Print the COMMAND that produced a figure next to the figure (lesson 7)."""
    tail = [ln for ln in result.stdout.strip().splitlines() if ln.strip()][-1:]
    print(f"    $ {' '.join(cmd)}")
    print(f"      exit={result.returncode}  {tail[0] if tail else '(no output)'}"
          f"{('  ' + note) if note else ''}")


def leg1_discriminator(tree):
    print("LEG 1 — DISCRIMINATOR PRECONDITION (gates every other leg)")
    cmd = [sys.executable, '-c',
           'import psh.builtins.read_builtin as rb; print(rb.__file__)']
    r = sh(cmd, cwd=tree)
    resolved = r.stdout.strip()
    want = os.path.join(tree, 'psh', 'builtins', 'read_builtin.py')
    print(f"    $ (cd {tree} && python -c 'import ...read_builtin; print(__file__)')")
    print(f"      resolved: {resolved}")
    if os.path.realpath(resolved) != os.path.realpath(want):
        print(f"      ABORT: expected {want}")
        return False
    print("      MATCHES the tag checkout — legs 2-6 may report numbers")
    return True


def run_per_cell(tree, cells, label):
    passed = failed = 0
    fails = []
    for node in cells:
        r = sh([sys.executable, '-m', 'pytest', node, '-q', '--no-header'],
               cwd=tree)
        if r.returncode == 0:
            passed += 1
        else:
            failed += 1
            fails.append(node)
    print(f"    {label}: {passed} pass / {failed} fail "
          f"({len(cells)} interpreters, one per cell)")
    for f in fails:
        print(f"      FAILED: {f}")
    return failed == 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: signoff_4b2.py <tag-or-sha>", file=sys.stderr)
        return 2
    ref = sys.argv[1]
    tree = os.path.join(WORKTREE, 'tmp', 'signoff-wt')
    shutil.rmtree(tree, ignore_errors=True)
    sh(['git', 'worktree', 'prune'], cwd=WORKTREE)
    add = sh(['git', 'worktree', 'add', '--detach', tree, ref], cwd=WORKTREE)
    if add.returncode != 0:
        print(f"could not create the detached checkout: {add.stderr}")
        return 2
    sha = sh(['git', 'rev-parse', 'HEAD'], cwd=tree).stdout.strip()
    print("=" * 78)
    print(f"SLOT 4B.2 DEV SIGN-OFF — ref {ref!r} -> {sha}")
    print(f"detached checkout: {tree}   tmp/ present at creation: "
          f"{os.path.isdir(os.path.join(tree, 'tmp'))}")
    print("=" * 78)
    ok = {}
    t0 = time.monotonic()
    try:
        if not leg1_discriminator(tree):
            print("\nSIGN-OFF ABORTED at leg 1.")
            return 1
        ok['leg1'] = True

        print("\nLEG 2 — DEFECT LEGS (the 22 cells red at base), per-cell")
        ok['leg2'] = run_per_cell(tree, DEFECT_CELLS, "defect cells")

        print("\nLEG 3 — MUST-HOLD (control/characterization + named siblings)")
        r = sh([sys.executable, '-m', 'pytest', *MUST_HOLD_FILES, '-q'], cwd=tree)
        emit(['pytest', '<13 must-hold targets>', '-q'], r)
        ok['leg3'] = r.returncode == 0

        print("\nLEG 4 — NO-SILENT-CHANGE (carry #21) vs the clean base baseline")
        os.makedirs(os.path.join(tree, 'tmp', 'w4b2'), exist_ok=True)
        shutil.copy(os.path.join(WORKTREE, 'tmp', 'w4b2', 'i10_carry21.py'),
                    os.path.join(tree, 'tmp', 'w4b2', 'i10_carry21.py'))
        out = os.path.join(WORKTREE, 'tmp', 'signoff', 'i10_at_tag.txt')
        r = sh([sys.executable, 'tmp/w4b2/i10_carry21.py'], cwd=tree)
        open(out, 'w').write(r.stdout + r.stderr)
        strip = lambda p: [ln for ln in open(p).read().splitlines()
                           if not ln.startswith(('module under test:', 'HEAD:',
                                                 'psh/ dirty:'))]
        same = strip(BASELINE) == strip(out)
        print(f"    $ (cd <tag> && python tmp/w4b2/i10_carry21.py) "
              f"| diff vs i10_carry21_BASE_clean.txt")
        print(f"      exit={r.returncode}  diff EMPTY: {same}  (24/24 expected)")
        ok['leg4'] = same and r.returncode == 0

        print("\nLEG 5 — M8 AT THE FRESH CHECKOUT (tmp/ absent at creation)")
        r = sh([sys.executable, '-m', 'pytest',
                'tests/unit/tooling/test_input_decoder_m8_locks_4b2.py', '-q'],
               cwd=tree)
        emit(['pytest', 'test_input_decoder_m8_locks_4b2.py', '-q'], r)
        ok['leg5'] = r.returncode == 0

        print("\nLEG 6 — FALSIFICATION (revert the production hunks; legs must FAIL)")
        rev = sh(['git', 'checkout', '21a23a4c', '--',
                  'psh/builtins/input_reader.py', 'psh/builtins/read_builtin.py'],
                 cwd=tree)
        if rev.returncode != 0:
            print(f"      could not revert: {rev.stderr.strip()}")
            ok['leg6'] = False
        else:
            probe = DEFECT_CELLS[0]
            r = sh([sys.executable, '-m', 'pytest', probe, '-q', '--no-header'],
                   cwd=tree)
            print(f"    $ pytest {probe.split('::')[-1]}  (production REVERTED)")
            print(f"      exit={r.returncode}  "
                  f"{'FAILS as required' if r.returncode != 0 else 'PASSED — the leg cannot fail, so it proves nothing'}")
            ok['leg6'] = r.returncode != 0
    finally:
        sh(['git', 'worktree', 'remove', '--force', tree], cwd=WORKTREE)
        print(f"\ndetached checkout removed; still present: {os.path.isdir(tree)}")

    print("\n" + "=" * 78)
    for leg in ('leg1', 'leg2', 'leg3', 'leg4', 'leg5', 'leg6'):
        print(f"  {leg}: {'PASS' if ok.get(leg) else 'FAIL'}")
    verdict = all(ok.get(k) for k in ('leg1', 'leg2', 'leg3', 'leg4', 'leg5', 'leg6'))
    print(f"  VERDICT: {'SIGN-OFF PASS' if verdict else 'SIGN-OFF FAIL — report, do not re-run'}")
    print(f"  ({time.monotonic() - t0:.1f}s, tag {sha})")
    print("=" * 78)
    return 0 if verdict else 1


if __name__ == '__main__':
    sys.exit(main())
