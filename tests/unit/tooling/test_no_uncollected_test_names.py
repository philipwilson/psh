"""No test function is named so that pytest silently declines to collect it.

R15-C. A test whose name is `testfoo` instead of `test_foo` does not match
`python_functions = test_*` (pytest.ini), so it is never collected — and
nothing fails, because a test that does not run cannot fail. That is the worst
failure mode a suite has: the guard looks present in the diff and is absent
from the run.

The instance that prompted this was an editor-level substring replace during a
rename, which turned `test_offset_line_numbers_...` into
`testoffset_line_numbers_...` and silently de-collected a disclosure pin.
The string-surgery class guard in the analysis-session tests covers ONE
production module; this covers the failure mode itself, tree-wide, for every
file pytest is configured to collect.

Cheap by design: a name-shape check over the AST, not a collection run.
"""
import ast
import configparser
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def _collected_file_glob() -> str:
    """The `python_files` pattern, READ from pytest.ini rather than assumed.

    If the project ever changes what it collects, this guard follows it
    instead of quietly checking the wrong set of files.
    """
    parser = configparser.ConfigParser()
    parser.read(REPO / "pytest.ini")
    return parser.get("pytest", "python_files").strip()


#: Ordinary English words that begin with "test" and are not mangled test
#: names. `tests` is a real property in the conformance runner; `test` reads
#: as a noun. Anything else starting with "test" and missing the underscore is
#: a test name that lost it.
_ORDINARY_WORDS = {"test", "tests", "testing"}


def _suspect_names(source: str):
    """Function names that READ as tests but cannot be collected as tests."""
    tree = ast.parse(source)
    return [
        (node.name, node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test")
        and not node.name.startswith("test_")
        and node.name not in _ORDINARY_WORDS
    ]


def test_no_test_function_is_missing_its_underscore():
    pattern = _collected_file_glob()
    assert pattern == "test_*.py", (
        f"python_files is now {pattern!r}; update this guard's reasoning "
        "before changing the glob it scans")

    offenders = []
    scanned = 0
    for path in sorted((REPO / "tests").rglob(pattern)):
        try:
            source = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        try:
            names = _suspect_names(source)
        except SyntaxError:
            continue          # a deliberately-malformed fixture, not our business
        scanned += 1
        for name, lineno in names:
            offenders.append(f"{path.relative_to(REPO)}:{lineno}: {name}")

    assert scanned > 500, (
        f"only {scanned} collected files scanned — the guard is looking in "
        "the wrong place, so its clean result means nothing")
    assert not offenders, (
        "test function(s) named so pytest will not collect them "
        f"(python_functions = test_*):\n  " + "\n  ".join(offenders))


@pytest.mark.parametrize("source,expected", [
    ("def testfoo(): pass", ["testfoo"]),
    ("def testoffset_line_numbers_reaches(): pass",
     ["testoffset_line_numbers_reaches"]),
    ("class TestX:\n    def testbar(self): pass", ["testbar"]),
    ("async def testasync(): pass", ["testasync"]),
])
def test_the_scan_detects_a_planted_name(source, expected):
    """MUTATION PROOF: the clean result above is worth nothing until the
    scanner is shown catching the shape it claims to catch — including the
    exact name that got past the suite once."""
    assert [name for name, _ in _suspect_names(source)] == expected


@pytest.mark.parametrize("source", [
    "def test_foo(): pass",
    "def helper(): pass",
    "def tests(self): pass",          # a property named `tests`, not a test
    "class TestX:\n    def test_bar(self): pass",
])
def test_the_scan_does_not_flag_legitimate_names(source):
    """The other half of the mutation proof: a guard that flags everything is
    as useless as one that flags nothing. `def tests(self)` in particular is a
    real property in the conformance runner — it must stay unflagged, and it
    lives outside the collected glob anyway."""
    assert _suspect_names(source) == []
