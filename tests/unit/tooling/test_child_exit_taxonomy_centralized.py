"""Meta-test: the forked-child exit taxonomy lives ONLY in child_policy.py.

Reappraisal #19 H10 replaced a five-site hand-copy of the "a control-flow /
exit exception at a forked child's top → the child's exit code" mapping
(TopLevelAbort→.status, FunctionReturn→.exit_code, LoopBreak/LoopContinue→
.exit_status or 0, SystemExit→its code) with ONE function,
``child_policy.map_child_exception``. Two of the old copies had already
diverged (the launcher mapped ``SystemExit(None)`` → 1, child_policy → 0) —
the exact divergent-twin failure this codebase guards against.

This guard is the same shape as the ``.variables`` write-ban and the
no-``DISPLAY`` guards: it greps the production tree for the taxonomy's
distinctive fingerprint — the LoopBreak/LoopContinue arm ``.exit_status or 0``
— and asserts every occurrence is inside ``psh/executor/child_policy.py``. A
new fork site must catch ``child_policy.CHILD_EXIT_EXCEPTIONS`` and delegate to
``map_child_exception`` rather than re-deriving the arm, so the mapping (and
any future fix to it) stays single-source.

Not fingerprinted here: ``0 if code is None else 1`` also appears in
``scripting/source_processor.py`` for the MAIN shell's ``exit``/``set -e``
SystemExit handling — a legitimately separate concern (the main shell's exit
DOES unwind; a forked child's does not), so it is not part of this taxonomy.
"""

import os
import re

HERE = os.path.dirname(__file__)
TESTS_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
REPO_ROOT = os.path.abspath(os.path.join(TESTS_ROOT, '..'))
PSH_ROOT = os.path.join(REPO_ROOT, 'psh')

# The one home of the taxonomy: relative to PSH_ROOT.
TAXONOMY_HOME = os.path.join('executor', 'child_policy.py')

# Fingerprint: the LoopBreak/LoopContinue → status arm. A break/continue that
# escapes a forked child's own loops ends it with the signal's own status, or
# 0 (`x=$(break 0)` in a loop → 1). This exact phrasing is the tell-tale of a
# hand-copied child-exit taxonomy.
_FINGERPRINT = re.compile(r'\.exit_status\s+or\s+0')


def _py_files():
    for root, _dirs, names in os.walk(PSH_ROOT):
        for name in names:
            if name.endswith('.py'):
                yield os.path.join(root, name)


def _fingerprint_hits(src):
    """Return line numbers in *src* matching the taxonomy fingerprint."""
    return [i for i, line in enumerate(src.splitlines(), start=1)
            if _FINGERPRINT.search(line)]


def test_child_exit_taxonomy_only_in_child_policy():
    offenders = {}
    for path in _py_files():
        rel = os.path.relpath(path, PSH_ROOT)
        if rel == TAXONOMY_HOME:
            continue
        with open(path) as f:
            hits = _fingerprint_hits(f.read())
        if hits:
            offenders[rel] = hits
    assert not offenders, (
        "The forked-child exit taxonomy (`.exit_status or 0`, H10) reappeared "
        f"outside psh/{TAXONOMY_HOME}: {offenders}. A fork site must catch "
        "child_policy.CHILD_EXIT_EXCEPTIONS and delegate to "
        "child_policy.map_child_exception, not re-derive the mapping.")


def test_taxonomy_home_still_carries_the_mapping():
    """The home actually contains the fingerprint (guards against a rename
    that would silently make the negative test vacuous)."""
    with open(os.path.join(PSH_ROOT, TAXONOMY_HOME)) as f:
        assert _fingerprint_hits(f.read()), (
            f"psh/{TAXONOMY_HOME} no longer contains the taxonomy fingerprint "
            "— update this guard if map_child_exception moved.")


def test_fingerprint_regex_self_test():
    """The fingerprint matches the canonical arm and ignores decoys."""
    # Canonical: the map_child_exception / (old) hand-copied arm.
    assert _fingerprint_hits("        return exc.exit_status or 0") == [1]
    assert _fingerprint_hits("            exit_code = e.exit_status or 0") == [1]
    # Decoys that must NOT match: the loop-status helper keeps the body
    # status (a different recipe), and a plain attribute read.
    assert _fingerprint_hits(
        "return sig.exit_status if sig.exit_status is not None else current") == []
    assert _fingerprint_hits("exit_status = self._signal_status(lb, exit_status)") == []
    assert _fingerprint_hits("self.exit_status = exit_status") == []
