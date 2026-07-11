import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PSH_ROOT = PROJECT_ROOT / "psh"

ALLOWLIST = {
    Path("psh/parser/implementations/parser_combinator_example.py.archived"),
}

REGEXES = [
    re.compile(r"token\\.value\\s*==\\s*['\"]([A-Za-z_]+)['\"]"),
    re.compile(r"token\\.value\\.lower\\(\\)\\s*==\\s*['\"]([A-Za-z_]+)['\"]"),
]


def _scan_file(path: Path):
    text = path.read_text(encoding="utf-8")
    for regex in REGEXES:
        for match in regex.finditer(text):
            word = match.group(1)
            if word.isalpha():
                yield match.group(0)


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
