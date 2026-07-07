"""README statistics must stay in sync with the tree — in every location.

The README quotes volatile numbers (test count, test-file count, source and
test line counts) in several places. They used to be hand-maintained and had
drifted apart into four contradictory test counts (finding D1 of the
2026-07-06 tests/docs appraisal). This test recomputes each number from the
tree — via the single ``tools/gen_test_stats.py`` computation — and checks
*every* README location, so any one of them going stale fails the suite.

Two kinds of claim are checked:

* **Exact-ish** numbers (the Project Statistics ``Lines of Code`` and
  ``Test Coverage`` lines) must be within 10% of reality.
* **Floor** numbers written as ``N+`` (the header ``**Tests**: N+`` and the
  ``Comprehensive Testing: N+ tests`` bullet) must never overclaim
  (``N <= actual``) and must not fall stale (within 15% below reality).

When this fails, update the README numbers and/or re-run
``python tools/gen_test_stats.py``.
"""

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
README = PROJECT_ROOT / "README.md"
TESTS_README = PROJECT_ROOT / "tests" / "README.md"

sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from gen_test_stats import compute_stats  # noqa: E402

STATS_RE = re.compile(
    r"\*\*Lines of Code\*\*: ~([\d,]+) lines of production code in `psh/` "
    r"across ([\d,]+) Python files, plus ~([\d,]+) lines of tests in "
    r"`tests/` \(([\d,]+) Python files\)"
)
TEST_COUNT_RE = re.compile(
    r"\*\*Test Coverage\*\*: ([\d,]+) tests in ([\d,]+) test files"
)
# Header line: "**Tests**: 14,900+"
HEADER_TESTS_RE = re.compile(r"\*\*Tests\*\*: ([\d,]+)\+")
# Feature bullet: "**Comprehensive Testing**: 14,900+ tests ..."
BULLET_TESTS_RE = re.compile(r"\*\*Comprehensive Testing\*\*: ([\d,]+)\+ tests")
# tests/README.md: "about 14,900 tests\nacross 581 `test_*.py` files"
TESTS_README_RE = re.compile(
    r"about ([\d,]+) tests\s+across ([\d,]+) `test_\*\.py` files")


def _num(s: str) -> int:
    return int(s.replace(",", ""))


def _assert_within(claimed: int, actual: int, what: str, tolerance=0.10):
    assert actual > 0, f"computed zero for {what}?"
    drift = abs(claimed - actual) / actual
    assert drift <= tolerance, (
        f"README claims {what} = {claimed:,} but the tree has {actual:,} "
        f"({drift:.0%} off; tolerance {tolerance:.0%}). "
        f"Update README.md (see python tools/gen_test_stats.py).")


def _assert_floor(claimed: int, actual: int, what: str, staleness=0.15):
    """An ``N+`` claim: must not overclaim, must not fall too far behind."""
    assert claimed <= actual, (
        f'README claims "{claimed:,}+" {what} but the tree has only '
        f"{actual:,} — the floor overclaims. Lower it "
        f"(python tools/gen_test_stats.py).")
    drift = (actual - claimed) / actual
    assert drift <= staleness, (
        f'README\'s "{claimed:,}+" {what} is stale — the tree now has '
        f"{actual:,} ({drift:.0%} below; tolerance {staleness:.0%}). "
        f"Raise it (python tools/gen_test_stats.py).")


@pytest.fixture(scope="module")
def stats():
    return compute_stats(include_collection=True)


@pytest.fixture(scope="module")
def readme_text():
    return README.read_text(encoding="utf-8")


def _search(pattern, text, what):
    m = pattern.search(text)
    assert m, f"README {what} line missing or reformatted: {pattern.pattern}"
    return m


def test_readme_loc_and_file_counts(stats, readme_text):
    loc = _search(STATS_RE, readme_text, "Project Statistics LOC")
    _assert_within(_num(loc.group(1)), stats["psh_loc"],
                   "production lines in psh/")
    _assert_within(_num(loc.group(2)), stats["psh_files"],
                   "Python files in psh/")
    _assert_within(_num(loc.group(3)), stats["test_loc"],
                   "test lines in tests/")
    _assert_within(_num(loc.group(4)), stats["test_py_files"],
                   "Python files in tests/")


def test_readme_test_coverage_line(stats, readme_text):
    tests = _search(TEST_COUNT_RE, readme_text, "Test Coverage")
    _assert_within(_num(tests.group(1)), stats["collected_tests"],
                   "collected tests (Test Coverage line)")
    _assert_within(_num(tests.group(2)), stats["test_star_files"],
                   "test files (Test Coverage line)")


def test_readme_header_and_bullet_test_floors(stats, readme_text):
    """The rounded ``N+`` mentions must agree with reality and each other."""
    header = _search(HEADER_TESTS_RE, readme_text, "header **Tests**")
    bullet = _search(BULLET_TESTS_RE, readme_text, "Comprehensive Testing bullet")
    _assert_floor(_num(header.group(1)), stats["collected_tests"],
                  "tests (header **Tests** line)")
    _assert_floor(_num(bullet.group(1)), stats["collected_tests"],
                  "tests (Comprehensive Testing bullet)")
    # The two rounded floors must not contradict each other.
    assert _num(header.group(1)) == _num(bullet.group(1)), (
        "README's two rounded test-count mentions disagree: header says "
        f"{header.group(1)}+, bullet says {bullet.group(1)}+. Keep them equal.")


def test_tests_readme_suite_size(stats):
    """tests/README.md's "about N tests across M test_*.py files" must track
    the tree (this was the fifth, contradictory D1 count)."""
    text = TESTS_README.read_text(encoding="utf-8")
    m = _search(TESTS_README_RE, text, "tests/README.md suite-size")
    _assert_within(_num(m.group(1)), stats["collected_tests"],
                   "tests/README.md test count", tolerance=0.15)
    _assert_within(_num(m.group(2)), stats["test_star_files"],
                   "tests/README.md test-file count")
