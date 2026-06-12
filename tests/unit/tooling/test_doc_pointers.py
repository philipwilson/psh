"""Doc-pointer meta-test: architecture docs must point at things that exist.

Scans ARCHITECTURE.md, docs/architecture/ast_data_flow.md,
docs/architecture/tour_of_psh_internals.md and every
psh/**/CLAUDE.md for backticked repo paths and symbol references, and
asserts each one resolves against the current tree. The goal is to catch
the "ghost class" of documentation failure loudly:

  * a named path (`psh/...`, `tests/...`, `docs/...`, or `foo/bar.py`)
    that no longer exists, and
  * a `symbol()` or `Class.method` claimed by the docs that no longer
    greps anywhere in the source (or, for ``**File**:``-anchored code
    blocks, in the specific file the doc names).

Extraction is deliberately high-precision rather than high-recall:
prose, pseudo-code without a file anchor, and lowercase attribute
references (``shell.state``, ``ctx.errors``) are ignored. 100% recall is
impossible; what matters is that every rule below has near-zero false
positives, so a failure here means the docs are lying.

Rules:
  R1  backticked repo path (psh/, tests/, docs/ prefix) must exist
      (globs must match something; trailing `/` must be a directory)
  R2  backticked relative ``*.py`` path must suffix-match a real file
      under psh/ or tests/
  R3  backticked ``ClassName.member`` (capitalized head): the class must
      be defined under psh/, and the member name must appear in a file
      defining that class
  R4  backticked ``function()`` call: ``def function(`` must exist
      somewhere under psh/ or tests/
  R5  every ``**File**:`` / ``**Files**:`` marker path must resolve
      (tried as-is from the repo root, then under psh/)
  R6  ``def``/``class`` names in fenced code blocks that follow a
      ``**File**:`` marker in the same section must grep in (one of) the
      named file(s)

Deliberate placeholders used by tutorials/examples are exempted below.
"""

import glob as globmod
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Documentation files under test.
DOC_FILES = sorted(
    [
        PROJECT_ROOT / "ARCHITECTURE.md",
        PROJECT_ROOT / "docs" / "architecture" / "ast_data_flow.md",
        PROJECT_ROOT / "docs" / "architecture" / "tour_of_psh_internals.md",
    ]
    + list((PROJECT_ROOT / "psh").rglob("CLAUDE.md"))
)

# ---------------------------------------------------------------------------
# Exemptions: deliberate placeholders and example names that intentionally
# do not resolve. Keep this list explicit and commented — every entry is a
# conscious decision, not a shrug.
# ---------------------------------------------------------------------------
EXEMPT = {
    # "Adding a builtin" tutorial placeholders (psh/builtins/CLAUDE.md,
    # psh/executor/CLAUDE.md)
    "mybuiltin.py",
    "psh/builtins/mybuiltin.py",
    "mycommand",
    "MyCommandBuiltin",
    # "Adding a new expansion type" tutorial placeholder (psh/expansion/CLAUDE.md)
    "new_expander.py",
    "NewExpander.expand",
}

# OS-level calls referenced in prose (`fork()`, `tcsetpgrp()`...) describe
# syscalls/os-module functions, not psh definitions — R4 skips them.
OS_CALLS = {
    "fork", "exec", "execve", "execvp", "tcsetpgrp", "tcgetpgrp", "setpgid",
    "getpgid", "setsid", "waitpid", "wait", "kill", "killpg", "open", "close",
    "dup", "dup2", "pipe", "read", "write", "isatty", "sigprocmask", "_exit",
    "exit", "select",
}

# Common file extensions: `CLAUDE.md`, `ARCHITECTURE.llm` etc. are file
# names, not Class.member references — R3 skips them.
FILE_EXTENSIONS = {
    "md", "py", "llm", "txt", "json", "yaml", "yml", "sh", "rst", "toml",
    "ini", "cfg",
}

# Regexes -------------------------------------------------------------------

FENCE_RE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
HEADING_RE = re.compile(r"^#{1,6} ", re.MULTILINE)

# R1: repo-rooted path, optionally a glob or a directory reference.
REPO_PATH_RE = re.compile(r"^(?:psh|tests|docs)(?:/[A-Za-z0-9_.*\-]+)*/?$")
# R2: relative .py path (one or more components, last ends in .py).
REL_PY_RE = re.compile(r"^[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-]+)*\.py$")
# R3: ClassName.member, optionally called. Head must be CamelCase-ish.
DOTTED_RE = re.compile(r"^([A-Z][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)(\(\))?$")
# R4: bare function call with empty parens.
CALL_RE = re.compile(r"^([a-z_][A-Za-z0-9_]*)\(\)$")
# R5/R6: **File**: markers and definitions inside fenced blocks.
MARKER_RE = re.compile(r"^\*\*Files?\*\*:(.*)$", re.MULTILINE)
DEF_RE = re.compile(r"^(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


@pytest.fixture(scope="module")
def source_corpus():
    """{path: text} for every production and test Python file."""
    corpus = {}
    for base in ("psh", "tests"):
        for path in (PROJECT_ROOT / base).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            corpus[path] = path.read_text(encoding="utf-8", errors="replace")
    return corpus


def _resolve_repo_path(token: str) -> bool:
    if "*" in token:
        return bool(globmod.glob(str(PROJECT_ROOT / token)))
    target = PROJECT_ROOT / token
    if token.endswith("/"):
        return target.is_dir()
    return target.exists()


def _suffix_match(token: str, corpus) -> bool:
    suffix = tuple(token.split("/"))
    return any(path.parts[-len(suffix):] == suffix for path in corpus)


def _class_files(cls: str, corpus):
    pattern = re.compile(rf"^class {re.escape(cls)}\b", re.MULTILINE)
    return [
        path for path, text in corpus.items()
        if path.is_relative_to(PROJECT_ROOT / "psh") and pattern.search(text)
    ]


def _check_inline_tokens(doc: Path, corpus):
    """Apply R1-R4 to inline backticked tokens (fenced blocks stripped)."""
    text = FENCE_RE.sub("", doc.read_text(encoding="utf-8"))
    failures = []
    for token in INLINE_CODE_RE.findall(text):
        token = token.strip()
        if token in EXEMPT:
            continue
        if REPO_PATH_RE.match(token):
            if not _resolve_repo_path(token):
                failures.append(f"R1 path does not exist: `{token}`")
            continue
        if REL_PY_RE.match(token):
            if not _suffix_match(token, corpus):
                failures.append(f"R2 no file matches: `{token}`")
            continue
        dotted = DOTTED_RE.match(token)
        if dotted:
            cls, member = dotted.group(1), dotted.group(2)
            if member in FILE_EXTENSIONS and not dotted.group(3):
                continue  # `NAME.md` style file names, not symbols
            files = _class_files(cls, corpus)
            if not files:
                failures.append(f"R3 class not found in psh/: `{token}`")
            elif not any(
                re.search(rf"\b{re.escape(member)}\b", corpus[f]) for f in files
            ):
                failures.append(
                    f"R3 `{token}`: `{member}` absent from file(s) defining "
                    f"class {cls}"
                )
            continue
        call = CALL_RE.match(token)
        if call:
            name = call.group(1)
            if name in OS_CALLS:
                continue
            if not any(f"def {name}(" in text_ for text_ in corpus.values()):
                failures.append(f"R4 no `def {name}(` anywhere: `{token}`")
    return failures


def _check_file_markers(doc: Path, corpus):
    """Apply R5/R6: **File**: markers and their adjacent code blocks."""
    text = doc.read_text(encoding="utf-8")
    failures = []
    # Split into sections at headings; a code block is only checked
    # against markers in its own section.
    boundaries = [m.start() for m in HEADING_RE.finditer(text)] + [len(text)]
    sections = [text[boundaries[i]:boundaries[i + 1]]
                for i in range(len(boundaries) - 1)] or [text]
    for section in sections:
        marker_files = []
        for marker in MARKER_RE.finditer(section):
            for token in INLINE_CODE_RE.findall(marker.group(1)):
                token = token.strip()
                if token in EXEMPT:
                    continue
                # Marker lines may also name the class they discuss
                # (e.g. **File**: `io_redirect/file_redirect.py`
                # (`FileRedirector`)) — only path-shaped tokens are files.
                if not re.search(r"\.\w+$", token):
                    continue
                resolved = None
                for candidate in (PROJECT_ROOT / token,
                                  PROJECT_ROOT / "psh" / token):
                    if candidate.is_file():
                        resolved = candidate
                        break
                if resolved is None:
                    failures.append(f"R5 **File** marker unresolvable: `{token}`")
                else:
                    marker_files.append(resolved)
        if not marker_files:
            continue
        texts = [corpus.get(f) or f.read_text(encoding="utf-8")
                 for f in marker_files]
        for block in re.findall(r"^```.*?\n(.*?)^```", section,
                                re.MULTILINE | re.DOTALL):
            for name in DEF_RE.findall(block):
                if name in EXEMPT or name == "__init__":
                    continue
                if not any(re.search(rf"\b{re.escape(name)}\b", t)
                           for t in texts):
                    failures.append(
                        f"R6 `{name}` (defined in a code block) does not "
                        f"appear in marker file(s) "
                        f"{[str(f.relative_to(PROJECT_ROOT)) for f in marker_files]}"
                    )
    return failures


@pytest.mark.parametrize(
    "doc", DOC_FILES, ids=[str(d.relative_to(PROJECT_ROOT)) for d in DOC_FILES]
)
def test_doc_pointers_resolve(doc, source_corpus):
    failures = _check_inline_tokens(doc, source_corpus)
    failures += _check_file_markers(doc, source_corpus)
    assert not failures, (
        f"{doc.relative_to(PROJECT_ROOT)} has stale pointers:\n  "
        + "\n  ".join(failures)
    )


def test_scanned_docs_exist():
    """If a scanned doc is deleted/renamed, fail here rather than silently
    shrinking coverage."""
    assert (PROJECT_ROOT / "ARCHITECTURE.md").is_file()
    assert (PROJECT_ROOT / "docs/architecture/ast_data_flow.md").is_file()
    assert (PROJECT_ROOT / "docs/architecture/tour_of_psh_internals.md").is_file()
    assert len(DOC_FILES) >= 12  # ARCHITECTURE + ast_data_flow + tour + 9 CLAUDE.md
