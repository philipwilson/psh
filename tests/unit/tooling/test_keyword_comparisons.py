"""Meta-test: no raw keyword comparisons against a token's ``.value``.

Keywords (``if``, ``then``, ``do``, ...) are classified by the lexer's
``KeywordNormalizer`` into dedicated token *types* at command position, so
production code decides "is this the reserved word X?" by TYPE — either
``token.type == TokenType.IF`` or, when a WORD-spelling has to be re-checked,
the shared helpers ``matches_keyword`` / ``matches_keyword_type``
(``psh/lexer/keyword_defs.py``). A raw ``token.value == 'if'`` duplicates the
keyword→type knowledge, silently ignores case-sensitivity, and matches a
quoted/escaped ``if`` that the lexer deliberately kept as a plain word. This
guard scans ``psh/`` and fails if such a comparison creeps in.

History: the guard was born vacuous (H21, reappraisal #19). Its regexes were
written with doubled backslashes inside raw strings
(``r"token\\.value\\s*=="``), so they required a *literal backslash* in the
scanned source and never matched anything. B5 single-escaped them and added
the guard-the-guard self-test below (the idiom every sibling meta-guard in
this directory has), so the guard can no longer silently rot.
"""

import re
from pathlib import Path

import pytest

from psh.lexer.keyword_defs import KEYWORD_TYPE_MAP

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PSH_ROOT = PROJECT_ROOT / "psh"

# Deliberate/correct raw keyword comparisons that must NOT trip the guard live
# here, each with a written justification. (Empty today: production compares
# reserved words by TYPE or via matches_keyword.) A path prefix relative to
# PROJECT_ROOT.
ALLOWLIST: set[Path] = set()

# The reserved-word spellings, sourced from production so the guard cannot
# drift when a keyword is added (longest-first so the alternation is greedy).
_KEYWORDS = "|".join(
    sorted((re.escape(k) for k in KEYWORD_TYPE_MAP), key=len, reverse=True)
)

# Match ``<any receiver>.value == '<keyword>'`` (and the ``.lower()`` variant).
# Single-escaped ``\.`` (NOT ``\\.``, the born-vacuous bug): each pattern
# matches real source such as ``tok.value == 'time'`` or
# ``tokens[0].value == 'in'``. The receiver is intentionally unanchored so the
# guard catches every token variable name (``token``/``tok``/``tokens[0]``/
# ``peek()``), and the RHS is restricted to the ACTUAL reserved words so a
# legitimate non-keyword value check (``t.value == 'alias'``) is not a false
# positive.
REGEXES = [
    re.compile(r"\.value\s*==\s*['\"](" + _KEYWORDS + r")['\"]"),
    re.compile(r"\.value\.lower\(\)\s*==\s*['\"](" + _KEYWORDS + r")['\"]"),
]


def _scan_text(text: str):
    """Yield each raw ``<recv>.value == '<keyword>'`` snippet found in *text*."""
    for regex in REGEXES:
        for match in regex.finditer(text):
            yield match.group(0)


def _scan_file(path: Path):
    yield from _scan_text(path.read_text(encoding="utf-8"))


def test_no_raw_keyword_comparisons():
    offending = []
    for file_path in PSH_ROOT.rglob("*.py"):
        rel = file_path.relative_to(PROJECT_ROOT)
        if any(str(rel).startswith(str(allowed)) for allowed in ALLOWLIST):
            continue
        for snippet in _scan_file(file_path):
            offending.append((rel, snippet))

    if offending:
        formatted = "\n".join(f"{path}: {snippet}" for path, snippet in offending)
        pytest.fail(
            "Found direct keyword comparisons; use matches_keyword or "
            "matches_keyword_type instead:\n"
            f"{formatted}"
        )


def test_guard_flags_synthetic_offender():
    """Guard-the-guard: a synthetic raw comparison MUST be flagged, and a
    typed comparison MUST NOT be — proving the (single-escaped) regexes match
    real source. This test would itself fail against the born-vacuous
    doubled-backslash regexes that shipped before B5."""
    # Offenders are flagged, under any token-variable receiver.
    assert list(_scan_text("if token.value == 'if':")) == [".value == 'if'"]
    assert list(_scan_text("in_run and tok.value == 'time'")) == [".value == 'time'"]
    assert list(_scan_text("tokens[0].value == 'in'")) == [".value == 'in'"]
    assert list(_scan_text("self.peek().value.lower() == 'while'")) == [
        ".value.lower() == 'while'"
    ]
    # The proper typed forms are NOT flagged.
    assert list(_scan_text("token.type == TokenType.IF")) == []
    assert list(_scan_text("matches_keyword(token, 'if')")) == []
    # A legitimate NON-keyword value check is not a false positive (the RHS is
    # restricted to real reserved words).
    assert list(_scan_text("t.value == 'alias'")) == []
    assert list(_scan_text("severity.value == 'error'")) == []
    # A non-keyword operand (e.g. an operator spelling) is ignored.
    assert list(_scan_text("token.value == '-p'")) == []
