"""The version string must match across version.py, README.md, ARCHITECTURE.md.

CLAUDE.md's release workflow mandates that the canonical `psh/version.py`
`__version__` and the `**Current Version**:` lines in README.md and
ARCHITECTURE.md always agree. Nothing regenerates them — they are bumped by
hand per release — so this meta-test fails loudly when one is forgotten,
instead of the docs silently drifting from the code.
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_CURRENT_VERSION_RE = re.compile(r"\*\*Current Version\*\*:\s*([0-9]+\.[0-9]+\.[0-9]+)")


def _canonical_version() -> str:
    text = (PROJECT_ROOT / "psh" / "version.py").read_text()
    m = re.search(r'__version__\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', text)
    assert m, "could not find __version__ in psh/version.py"
    return m.group(1)


def _doc_version(relpath: str) -> str:
    text = (PROJECT_ROOT / relpath).read_text()
    m = _CURRENT_VERSION_RE.search(text)
    assert m, f"could not find a '**Current Version**:' line in {relpath}"
    return m.group(1)


def test_readme_version_matches_version_py():
    assert _doc_version("README.md") == _canonical_version(), (
        "README.md '**Current Version**:' is out of sync with psh/version.py"
    )


def test_architecture_version_matches_version_py():
    assert _doc_version("ARCHITECTURE.md") == _canonical_version(), (
        "ARCHITECTURE.md '**Current Version**:' is out of sync with "
        "psh/version.py"
    )


def test_changelog_has_an_entry_for_the_current_version():
    version = _canonical_version()
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text()
    assert f"## {version} " in changelog, (
        f"CHANGELOG.md has no '## {version}' entry for the current version"
    )
