"""README "Project Statistics" must stay within 10% of reality.

The numbers in README.md's Project Statistics section are hand-written
prose; nothing regenerates them. This test recomputes each one from the
tree and fails when the README drifts more than 10% from the truth, so
the section rots loudly instead of silently lying. When this fails,
update the README numbers (and keep them roughly rounded — the test
tolerates +/-10%, not exactness).
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
README = PROJECT_ROOT / "README.md"

STATS_RE = re.compile(
    r"\*\*Lines of Code\*\*: ~([\d,]+) lines of production code in `psh/` "
    r"across ([\d,]+) Python files, plus ~([\d,]+) lines of tests in "
    r"`tests/` \(([\d,]+) Python files\)"
)
TEST_COUNT_RE = re.compile(
    r"\*\*Test Coverage\*\*: ([\d,]+) tests in ([\d,]+) test files"
)


def _num(s: str) -> int:
    return int(s.replace(",", ""))


def _py_files(base: str):
    return [
        p for p in (PROJECT_ROOT / base).rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _line_count(paths) -> int:
    return sum(
        len(p.read_bytes().splitlines()) for p in paths
    )


def _assert_within(claimed: int, actual: int, what: str, tolerance=0.10):
    assert actual > 0, f"computed zero for {what}?"
    drift = abs(claimed - actual) / actual
    assert drift <= tolerance, (
        f"README claims {what} = {claimed:,} but the tree has {actual:,} "
        f"({drift:.0%} off; tolerance {tolerance:.0%}). "
        f"Update README.md's Project Statistics section."
    )


@pytest.fixture(scope="module")
def stats_section():
    text = README.read_text(encoding="utf-8")
    loc = STATS_RE.search(text)
    tests = TEST_COUNT_RE.search(text)
    assert loc, "README Project Statistics LOC line missing or reformatted"
    assert tests, "README Test Coverage line missing or reformatted"
    return loc, tests


def test_readme_loc_and_file_counts(stats_section):
    loc, _ = stats_section
    psh_files = _py_files("psh")
    test_files = _py_files("tests")
    _assert_within(_num(loc.group(1)), _line_count(psh_files),
                   "production lines in psh/")
    _assert_within(_num(loc.group(2)), len(psh_files),
                   "Python files in psh/")
    _assert_within(_num(loc.group(3)), _line_count(test_files),
                   "test lines in tests/")
    _assert_within(_num(loc.group(4)), len(test_files),
                   "Python files in tests/")


def test_readme_test_file_count(stats_section):
    _, tests = stats_section
    actual_files = len([
        p for p in (PROJECT_ROOT / "tests").rglob("test_*.py")
        if "__pycache__" not in p.parts
    ])
    _assert_within(_num(tests.group(2)), actual_files, "test files")


def test_readme_collected_test_count(stats_section):
    """Compare the claimed test count against a real pytest collection.

    Collection imports every test module in a subprocess (~1s) — the
    slowest check here, but cheap enough to keep in the quick gate.
    """
    _, tests = stats_section
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=300,
    )
    match = re.search(r"(\d+) tests collected", result.stdout)
    assert match, (
        f"could not parse collection output:\n{result.stdout[-2000:]}"
    )
    _assert_within(_num(tests.group(1)), int(match.group(1)),
                   "collected tests")
