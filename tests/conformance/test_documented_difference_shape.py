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

def test_every_documented_entry_carries_an_expected_shape(framework):
    """A catalog entry without a shape would silently fall back to blind
    membership matching — the exact defect this closes."""
    documented = framework.differences_catalog.get('documented', {})
    assert documented, "catalog is empty — the fixture is not loading it"
    missing = [
        entry.get('id', cmd) for cmd, entry in documented.items()
        if 'expected' not in entry
    ]
    assert not missing, f"catalog entries with no expected shape: {missing}"


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
