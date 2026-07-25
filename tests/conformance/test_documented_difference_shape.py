"""F1: documented-difference classification must be BEHAVIOR-AWARE.

`_is_documented_difference` used to be `command in catalog['documented']` — a
COMMAND-KEY lookup that never looked at what either shell actually did. Any
future divergence on a catalogued command therefore classified as
DOCUMENTED_DIFFERENCE, including a genuine regression, so an
`assert_documented_difference` pin could not fail for the right reason (the
HIGH-1 defect shape: a test that cannot fail).

Closure: every catalog entry carries the EXPECTED SHAPE of its difference as
structured data (per-side expected exit status and an output predicate), and
classification validates the OBSERVED divergence against that shape before
returning DOCUMENTED_DIFFERENCE. A divergence that no longer matches its
entry is NOT documented — the difference changed, or a shell regressed.

The forged-output test below is the discriminator: it feeds a nonsense psh
stdout for a catalogued command and requires the classifier to REFUSE it. On
base that forgery classified DOCUMENTED_DIFFERENCE.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from conformance_framework import (  # noqa: E402
    CommandResult,
    ConformanceTestFramework,
)


@pytest.fixture
def framework():
    return ConformanceTestFramework()


def _result(command, stdout="", stderr="", exit_code=0, shell="psh"):
    return CommandResult(stdout=stdout, stderr=stderr, exit_code=exit_code,
                         execution_time=0.0, shell=shell, command=command)


# --------------------------------------------------------------------------
# The discriminator: a forged observation must NOT be waved through.
# --------------------------------------------------------------------------

def test_forged_psh_output_is_not_a_documented_difference(framework):
    """RED ON BASE. `echo $$` is catalogued (PROCESS_ID_DIFFERENCE) as "both
    print their own pid". A psh stdout of 'banana' matches no such shape, so
    the classifier must refuse it.

    On base this returned DOCUMENTED_DIFFERENCE purely because the COMMAND
    was a catalog key — which is exactly why the pin on this command could
    not fail for the right reason.
    """
    command = 'echo $$'
    psh = _result(command, stdout='banana\n', exit_code=0, shell='psh')
    bash = _result(command, stdout='14087\n', exit_code=0, shell='bash')

    assert not framework._is_documented_difference(command, psh, bash), (
        "a nonsense psh stdout for a catalogued command was accepted as a "
        "DOCUMENTED_DIFFERENCE — classification is not looking at behavior"
    )


def test_forged_exit_status_is_not_a_documented_difference(framework):
    """The same blindness on the status axis: `echo $$` is documented with
    BOTH shells exiting 0. A psh that started failing must not be documented.
    """
    command = 'echo $$'
    psh = _result(command, stdout='', stderr='boom\n', exit_code=3, shell='psh')
    bash = _result(command, stdout='14087\n', exit_code=0, shell='bash')

    assert not framework._is_documented_difference(command, psh, bash)


def test_uncatalogued_command_is_never_documented(framework):
    """Membership is still necessary — it is just no longer sufficient."""
    command = 'echo not-in-the-catalog'
    psh = _result(command, stdout='a\n', shell='psh')
    bash = _result(command, stdout='b\n', shell='bash')

    assert not framework._is_documented_difference(command, psh, bash)


# --------------------------------------------------------------------------
# The genuine divergences must still classify (no over-correction).
# --------------------------------------------------------------------------

def test_real_pid_divergence_still_classifies(framework):
    """Two different numeric pids, both exit 0 — the documented shape."""
    command = 'echo $$'
    psh = _result(command, stdout='14085\n', exit_code=0, shell='psh')
    bash = _result(command, stdout='14087\n', exit_code=0, shell='bash')

    assert framework._is_documented_difference(command, psh, bash)


def test_real_alias_divergence_still_classifies(framework):
    """The sanctioned non-interactive alias divergence: psh 0, bash 127."""
    command = 'alias ll="echo ALIAS_EXPANDED"; ll'
    psh = _result(command, stdout='ALIAS_EXPANDED\n', exit_code=0, shell='psh')
    bash = _result(command, stderr='ll: command not found\n', exit_code=127,
                   shell='bash')

    assert framework._is_documented_difference(command, psh, bash)


# --------------------------------------------------------------------------
# Catalog integrity (F2's invariant, enforced here so it cannot rot again).
# --------------------------------------------------------------------------

#: A side must constrain at least one of these, or it checks nothing.
_CHECKABLE_KEYS = {'exit_code', 'stdout_pattern', 'stderr_pattern'}


def _shape_defects(documented):
    """Every way an `expected` block can fail to constrain the observation."""
    defects = []
    for cmd, entry in documented.items():
        name = entry.get('id', cmd)
        expected = entry.get('expected')
        if not expected:
            defects.append(f"{name}: no 'expected' block")
            continue
        for side in ('psh', 'bash'):
            spec = expected.get(side)
            if not spec:
                defects.append(f"{name}: no '{side}' side")
            elif not _CHECKABLE_KEYS & set(spec):
                defects.append(
                    f"{name}: '{side}' side constrains nothing "
                    f"(needs one of {sorted(_CHECKABLE_KEYS)}, has "
                    f"{sorted(spec)})")
    return defects


def test_every_documented_entry_carries_an_expected_shape(framework):
    """Every entry must actually CONSTRAIN both sides' observations.

    Presence of an `expected` key is not enough. This test originally asserted
    only `'expected' in entry`, which a block containing nothing but prose —
    `{"note": "..."}` — satisfied while checking nothing at runtime, so such an
    entry re-opened the blind classification F1 closed. Both sides must exist
    and each must pin at least an exit status or one output pattern.
    """
    documented = framework.differences_catalog.get('documented', {})
    assert documented, "catalog is empty — the fixture is not loading it"
    defects = _shape_defects(documented)
    assert not defects, "catalog entries that do not constrain behavior: " + \
        "; ".join(defects)


def test_a_vacuous_expected_block_is_refused(framework):
    """OFFENDER REPLAY for the anti-bypass hole (round-2 blocker A).

    Injects an entry whose `expected` block names no checkable key. Before the
    fix, `_matches_side({}, ...)` returned True (nothing to check), so this
    entry classified TOTAL NONSENSE on both sides as DOCUMENTED_DIFFERENCE
    while the meta-test stayed green — a guard present but empty.

    Both halves must now refuse it: the meta-test statically, and the
    classifier at runtime, so a hand-edited catalog cannot bypass either.
    """
    documented = framework.differences_catalog['documented']
    documented['zzz vacuous offender'] = {
        'id': 'VACUOUS_OFFENDER',
        'description': 'synthetic: expected block that checks nothing',
        'expected': {'note': 'prose only — constrains neither side'},
    }

    # (a) static half: the meta-test's own predicate flags it.
    defects = _shape_defects(documented)
    assert any('VACUOUS_OFFENDER' in d for d in defects), (
        "the catalog-shape check accepted an entry that constrains nothing")

    # (b) runtime half: it must not classify, however absurd the observation.
    psh = _result('zzz vacuous offender', stdout='total nonsense',
                  exit_code=99, shell='psh')
    bash = _result('zzz vacuous offender', stdout='other nonsense',
                   exit_code=7, shell='bash')
    assert not framework._is_documented_difference(
        'zzz vacuous offender', psh, bash), (
        "a vacuous expected block classified nonsense as a documented "
        "difference — blind classification is back")

    # A side present but empty is the same hole by another route.
    documented['zzz vacuous offender']['expected'] = {'psh': {}, 'bash': {}}
    assert not framework._is_documented_difference(
        'zzz vacuous offender', psh, bash)
    assert any('VACUOUS_OFFENDER' in d for d in _shape_defects(documented))


def test_no_documented_entry_is_dead_inventory(framework):
    """Every catalog entry must be referenced by at least one test (F2).

    4 of the 7 original entries (HELP_BUILTIN, PUSHD_BEHAVIOR,
    PUSHD_CWD_DIFFERENCE, POPD_BEHAVIOR) were referenced by ZERO tests. They
    were inventory, not closures: nothing proved the difference was still
    real, and probing showed three of them were not — pushd/popd behave
    IDENTICALLY to bash (which is what user guide 17 claims: "pushd/popd/dirs
    | Full support"), and PUSHD_CWD_DIFFERENCE documented a HARNESS artifact,
    two different working directories, as a shell difference. All four are
    deleted; this keeps the catalog from re-growing dead rows.

    HONEST LIMIT: this is a TEXTUAL search for the difference ID across the
    conformance test sources, so a mere MENTION — an ID appearing only in a
    comment or a docstring — satisfies it. It catches the failure mode that
    actually occurred (entries nothing in the tree referred to at all); it
    does NOT verify that the referencing test exercises the entry. Tightening
    it would mean statically resolving `assert_documented_difference` call
    arguments, worth doing only if a mention-without-exercise case appears.
    """
    conformance_root = Path(__file__).parent
    sources = [
        p.read_text(encoding='utf-8', errors='replace')
        for p in conformance_root.rglob('test_*.py')
        if p != Path(__file__)
    ]

    unreferenced = []
    for command, entry in framework.differences_catalog.get('documented', {}).items():
        difference_id = entry.get('id', command)
        if not any(difference_id in src for src in sources):
            unreferenced.append(difference_id)

    assert not unreferenced, (
        "documented-difference entries referenced by NO test (dead "
        f"inventory — give each a proving test or delete it): {unreferenced}"
    )
