"""User-facing docs must not point at things that don't exist.

`test_doc_pointers.py` already guards the architecture docs and CLAUDE.md
files, but it deliberately skips the high-traffic, prose-heavy entry docs
(README, tests/README, the testing source of truth) because its symbol
rules would false-positive on marketing prose. Those docs still drift —
the classic failures this catches are a referenced `examples/foo.sh` with
no `examples/` directory and a `tests/README.md` naming directories that
were renamed away.

So this test applies the two checks that matter for entry docs and have
near-zero false positives:

  * every backticked repo-rooted path (`psh/…`, `tests/…`, `docs/…`,
    `examples/…`) resolves against the tree, and
  * every inline Markdown link to a local path resolves.
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DOCS = [
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "tests" / "README.md",
    PROJECT_ROOT / "docs" / "testing_source_of_truth.md",
    PROJECT_ROOT / "examples" / "README.md",
]

FENCE_RE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
# A backticked token that looks like a repo-rooted path.
REPO_PATH_RE = re.compile(r"^(?:psh|tests|docs|examples)(?:/[A-Za-z0-9_.*\-]+)*/?$")
# Inline Markdown links: [text](target). Images share the syntax.
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _resolve_repo_path(token: str) -> bool:
    import glob as globmod
    if "*" in token:
        return bool(globmod.glob(str(PROJECT_ROOT / token)))
    target = PROJECT_ROOT / token
    return target.is_dir() if token.endswith("/") else target.exists()


@pytest.mark.parametrize("doc", DOCS, ids=[str(d.relative_to(PROJECT_ROOT)) for d in DOCS])
def test_backticked_paths_exist(doc):
    text = FENCE_RE.sub("", doc.read_text(encoding="utf-8"))
    failures = [
        f"`{tok}`" for tok in INLINE_CODE_RE.findall(text)
        if REPO_PATH_RE.match(tok.strip()) and not _resolve_repo_path(tok.strip())
    ]
    assert not failures, (
        f"{doc.relative_to(PROJECT_ROOT)} references missing paths: "
        + ", ".join(sorted(set(failures)))
    )


@pytest.mark.parametrize("doc", DOCS, ids=[str(d.relative_to(PROJECT_ROOT)) for d in DOCS])
def test_markdown_links_resolve(doc):
    text = doc.read_text(encoding="utf-8")
    failures = []
    for target in LINK_RE.findall(text):
        target = target.strip()
        # External links, in-page anchors, and mailto are out of scope.
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        path_part = target.split("#", 1)[0]  # drop any #anchor
        if not path_part:
            continue
        resolved = (doc.parent / path_part).resolve()
        ok = resolved.is_dir() if path_part.endswith("/") else resolved.exists()
        if not ok:
            failures.append(target)
    assert not failures, (
        f"{doc.relative_to(PROJECT_ROOT)} has broken local links: "
        + ", ".join(sorted(set(failures)))
    )
