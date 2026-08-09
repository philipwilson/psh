"""Ratchet: the seven APIs remediation 5C.2 deleted stay deleted.

Each was removed against a committed zero-witness census
(``docs/reviews/evidence/boundary_remediation_2026-07/5c.2-rescue/censuses/
DEAD-API-CENSUS.md``), and each delete commit verified grep-zero AT that
commit. That is history: it proves the tree was clean once. It does not stop a
future commit from reintroducing the name, which is exactly what the census
document's own "grep-zero pin" wording promises and what the 5B.2
``VariableAccess`` model — the model that census invokes — actually had.

This makes the property STANDING.

**What counts as a resurrection.** A production reference to one of these names
in ``psh/``, ``tests/`` or ``tools/``. Deliberately NOT counted:

* ``CHANGELOG.md``, ``docs/reviews/`` and ``docs/archive/`` — append-only
  history that correctly records what these symbols were. Rewriting history to
  satisfy a ratchet is the failure this exclusion prevents.
* two TEST FUNCTION NAMES that merely contain a deleted name as a substring
  (``test_disown_list_jobs``, ``test_echo_with_redirections`` /
  ``test_command_with_redirections``). They are different symbols; the census
  distinguished them by hand and so does this guard, by exact allowlist rather
  than by loosening the pattern.

**Why word-boundary matching, not substring.** ``list_jobs`` is a substring of
``test_disown_list_jobs``; a substring search would force the allowlist to grow
every time someone names a test after a behaviour. The pattern is anchored on
word boundaries and the residual collisions are listed explicitly.
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]

# The seven symbols deleted by slot 5C.2, with the row each discharges.
DELETED = {
    "with_redirections": "D-4B.4-s3 (IOManager dead twin)",
    "foreground_pgid": "D-5B.2-dead (write-only field, full chain)",
    "publish_foreground_pgid": "D-5B.2-dead (the JobRuntime publish member)",
    "get_job_by_pgid": "bounded census (never called since birth)",
    "list_jobs": "bounded census (orphaned by refactor)",
    "is_function_readonly": "bounded census (never called since birth)",
    "clear_functions": "bounded census (never called since birth)",
    "try_resolve_bash": "LEDGER L301 (referenced only by its own self-test)",
}

# Exact lines that legitimately contain a deleted name as a SUBSTRING of a
# different symbol, or as the historical record of the retirement itself.
# Each entry is a conscious decision, not a shrug.
ALLOWED_SUBSTRING_SITES = {
    # Test NAMES containing a deleted symbol as a substring — different symbols.
    ("tests/unit/builtins/test_disown_builtin.py", "test_disown_list_jobs"),
    ("tests/conformance/posix/test_posix_compliance.py",
     "test_command_with_redirections"),
    ("tests/unit/builtins/test_echo_comprehensive.py",
     "test_echo_with_redirections"),
    # The conformance row's comment recording WHY the publish member went.
    ("tests/unit/protocols/test_protocol_conformance_q1.py",
     "publish_foreground_pgid"),
    # This guard itself names all seven, by construction.
    ("tests/unit/tooling/test_dead_api_not_resurrected_5c2.py", "*"),
    # The frozen oracle census records the retired spelling as history.
    ("tests/harness/oracle_migration_census.md", "try_resolve_bash"),
}


def _scanned_files(root=ROOT):
    for base in ("psh", "tests", "tools"):
        base_dir = root / base
        if not base_dir.exists():
            continue
        for path in base_dir.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix not in (".py", ".md"):
                continue
            yield path


def _hits(symbol, root=ROOT):
    pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    out = []
    for path in _scanned_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if not pattern.search(line):
                continue
            if any(rel == f and (tok == "*" or tok in line)
                   for f, tok in ALLOWED_SUBSTRING_SITES):
                continue
            out.append((rel, lineno, line.strip()[:110]))
    return out


@pytest.mark.parametrize("symbol", sorted(DELETED))
def test_deleted_api_is_not_resurrected(symbol):
    hits = _hits(symbol)
    assert not hits, (
        f"`{symbol}` was DELETED by remediation 5C.2 "
        f"({DELETED[symbol]}) against a committed zero-witness census, and it "
        "is back:\n  "
        + "\n  ".join(f"{rel}:{ln}: {src}" for rel, ln, src in hits)
        + "\n\nIf the reintroduction is deliberate, the census that justified "
        "the delete is the thing to revisit — not this list."
    )


def test_the_guard_scans_a_plausible_corpus():
    """A ratchet over an empty corpus passes forever."""
    files = list(_scanned_files())
    assert len(files) > 500, (
        f"only {len(files)} files scanned — the corpus collapsed and every "
        "arm above would pass vacuously")


@pytest.mark.parametrize("symbol", sorted(DELETED))
def test_offender_a_resurrected_symbol_is_caught(symbol, tmp_path):
    """OFFENDER, per symbol: a planted production reference must be found.

    Drives ``_hits`` — the SAME function the real arms use — against a
    synthetic tree, rather than re-implementing the match here. A guard-the-
    guard that re-implements the thing it is checking proves only that the
    author can write the regex twice. Synthetic root, so nothing is planted in
    the real tree and the arm leaves nothing behind.
    """
    fake = tmp_path / "psh" / "resurrected.py"
    fake.parent.mkdir(parents=True)
    fake.write_text(f"def f(obj):\n    return obj.{symbol}()\n")

    found = _hits(symbol, root=tmp_path)
    assert found, (
        f"a planted production reference to `{symbol}` was NOT caught — the "
        "ratchet would not see a real resurrection either")


def test_control_an_unrelated_symbol_is_not_flagged(tmp_path):
    """CONTROL: the matcher is specific, not 'any reference anywhere'.

    Without this, a matcher that flagged every line would pass all eight
    offender arms above and be worthless.
    """
    fake = tmp_path / "psh" / "innocent.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("def f(obj):\n    return obj.guarded_redirections()\n")

    for symbol in DELETED:
        assert not _hits(symbol, root=tmp_path), (
            f"`{symbol}` was reported in a file that only mentions the LIVE "
            "sibling `guarded_redirections`")


def test_control_a_substring_test_name_is_not_flagged():
    """CONTROL: the allowlisted substring collisions must NOT trip.

    Without this, the guard could be 'fixed' by loosening the pattern and
    nobody would notice it had stopped distinguishing
    `test_disown_list_jobs` from `list_jobs`.
    """
    assert not _hits("list_jobs"), (
        "the substring test-name collision is being reported as a "
        "resurrection — the word-boundary pattern or the allowlist regressed")
