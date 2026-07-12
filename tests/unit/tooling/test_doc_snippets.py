"""Drift-lock meta-guard for verbatim code snippets quoted in CLAUDE.md docs.

Rule (root ``CLAUDE.md`` → Development Principles): subsystem ``CLAUDE.md``
files carry invariant prose and ``file.py#symbol`` pointers, NOT implementation
sketches — reappraisal #19 found that 8 of 9 subsystem docs had drifted and in
every case the worst rot was an embedded code sketch teaching a since-fixed
bug. Where a snippet is deliberately kept as VERBATIM code (load-bearing string
constants, enum values, exact declarations), it must be **drift-locked** here:
each registered fragment must appear verbatim BOTH in the doc that quotes it AND
in the source file it claims to mirror. If the source changes, this test fails,
forcing the doc to be updated in lockstep.

This is the companion to ``test_doc_pointers.py`` (which checks that pointers
RESOLVE); this one checks that the quoted code STILL MATCHES.

Guard-the-guard: ``test_guard_flags_source_drift`` and
``test_guard_flags_missing_source`` feed synthetic entries the checker MUST
reject, so an accidentally-green registry entry cannot pass silently (the
guard-the-guard idiom every tooling meta-test in this directory follows).
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Registry: each entry pins load-bearing VERBATIM fragments that must appear in
# BOTH the doc file and the source file. Keep fragments minimal (the exact
# load-bearing text — an enum value, a flag declaration) so incidental edits
# (comment rewording, reflow) do not churn the registry, while a genuine change
# to the pinned code trips the guard.
# ---------------------------------------------------------------------------
REGISTRY = [
    {
        # `ProcessRole` enum: the string VALUES are a wire-level contract
        # (job-control role dispatch); test_doc_pointers checks the symbol
        # exists, not that the values still read "single"/"pipeline_*".
        "name": "ProcessRole enum values",
        "doc": "psh/executor/CLAUDE.md",
        "source": "psh/executor/process_launcher.py",
        "fragments": [
            'SINGLE = "single"',
            'PIPELINE_LEADER = "pipeline_leader"',
            'PIPELINE_MEMBER = "pipeline_member"',
        ],
    },
    {
        # `VarAttributes` flag members: the core CLAUDE.md sketch enumerates
        # them; pin the declarations so a renamed/removed flag can't leave the
        # doc teaching a phantom attribute.
        "name": "VarAttributes flag members",
        "doc": "psh/core/CLAUDE.md",
        "source": "psh/core/variables.py",
        "fragments": [
            "READONLY = auto()",
            "EXPORT = auto()",
            "NAMEREF = auto()",
        ],
    },
]


def _check(entry: dict) -> list:
    """Return a list of failure strings for one registry entry (empty == OK)."""
    failures = []
    doc_path = PROJECT_ROOT / entry["doc"]
    src_path = PROJECT_ROOT / entry["source"]
    if not doc_path.is_file():
        return [f"{entry['name']}: doc file missing: {entry['doc']}"]
    if not src_path.is_file():
        return [f"{entry['name']}: source file missing: {entry['source']}"]
    doc_text = doc_path.read_text(encoding="utf-8")
    src_text = src_path.read_text(encoding="utf-8")
    for frag in entry["fragments"]:
        if frag not in doc_text:
            failures.append(
                f"{entry['name']}: fragment absent from doc {entry['doc']}: "
                f"{frag!r} (the doc no longer quotes this snippet — update the "
                f"registry or restore the snippet)")
        if frag not in src_text:
            failures.append(
                f"{entry['name']}: fragment absent from source {entry['source']}: "
                f"{frag!r} (the doc snippet has DRIFTED from the code — update "
                f"the doc to match)")
    return failures


@pytest.mark.parametrize("entry", REGISTRY, ids=[e["name"] for e in REGISTRY])
def test_doc_snippet_matches_source(entry):
    failures = _check(entry)
    assert not failures, (
        "Drift-locked doc snippet no longer matches its source:\n  "
        + "\n  ".join(failures))


def test_registry_nonempty():
    """A drift-lock with no entries pins nothing — fail loudly if emptied."""
    assert REGISTRY, "drift-lock registry is empty — add the snippets it pins"


def test_guard_flags_source_drift():
    """Guard-the-guard: a fragment absent from the SOURCE must be flagged."""
    stale = {
        "name": "SYNTHETIC source-drift entry",
        "doc": "psh/executor/CLAUDE.md",
        "source": "psh/executor/process_launcher.py",
        "fragments": ['PIPELINE_GHOST = "ghost-not-in-source"'],
    }
    failures = _check(stale)
    assert failures, (
        "guard-the-guard: checker failed to flag a fragment absent from source")
    assert any("absent from source" in f for f in failures), failures


def test_guard_flags_missing_source():
    """Guard-the-guard: a registry entry naming a non-existent source file
    must be flagged, not silently skipped."""
    missing = {
        "name": "SYNTHETIC missing-source entry",
        "doc": "psh/executor/CLAUDE.md",
        "source": "psh/executor/does_not_exist_zzz.py",
        "fragments": ["whatever"],
    }
    assert _check(missing), (
        "guard-the-guard: checker failed to flag a missing source file")
