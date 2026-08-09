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
  R4  backticked call cite: ``def <callable>(`` must exist somewhere under
      psh/, tests/ or tools/. Since remediation 5C.2 this covers DOTTED and
      ARGUMENT-BEARING cites too (``io_manager.guarded_redirections(node.redirects)``,
      not just ``function()``) — the narrow form let a deleted symbol sit in a
      live orientation doc. Exemptions: ``OS_CALLS`` for stdlib/builtin heads,
      and a structural filter for shell syntax (``for(( ))``, ``$(( ))``).
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

# Documentation files under test. Campaign Q2 (S2 guard-scope widening carry)
# extends the sweep beyond psh/: the ROOT ``CLAUDE.md`` (the orientation doc, the
# densest source of `file.py#symbol` pointers) and every ``tests/**/CLAUDE.md``
# are scanned too, so a stale pointer in them fails just as loudly.
DOC_FILES = sorted(
    [
        PROJECT_ROOT / "ARCHITECTURE.md",
        PROJECT_ROOT / "CLAUDE.md",
        PROJECT_ROOT / "docs" / "architecture" / "ast_data_flow.md",
        PROJECT_ROOT / "docs" / "architecture" / "tour_of_psh_internals.md",
        PROJECT_ROOT / "docs" / "architecture" / "command_position.md",
    ]
    + list((PROJECT_ROOT / "psh").rglob("CLAUDE.md"))
    + list((PROJECT_ROOT / "tests").rglob("CLAUDE.md"))
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
    # A REAL callable this matcher structurally cannot see: `clear_output` is
    # ASSIGNED as a lambda (tests/conftest.py, `shell.clear_output = lambda:`),
    # so `def clear_output(` never exists. Surfaced by the 5C.2 R4 widening and
    # deliberately NOT fixed here — assignment-defined callables are a SECOND
    # blind spot, and closing it means changing what the CORPUS understands, not
    # what the matcher matches. Named as successor row D-5C.2-s1 rather than
    # half-fixed: an exemption that hides a known class is honest only while it
    # says which class it is hiding.
    "captured_shell.clear_output()",
}

# OS-level calls referenced in prose (`fork()`, `tcsetpgrp()`...) describe
# syscalls/os-module functions, not psh definitions — R4 skips them.
#
# HONEST NOTE, because this list is itself a rot surface: it is HAND-CURATED.
# Every entry is a decision to STOP checking a name, and nothing asserts that
# an entry is still cited or still stdlib — a stale entry fails silently by
# construction. It is the cheapest correct mechanism (the alternative, importing
# and introspecting stdlib to classify every head, would make a documentation
# guard depend on the runtime environment), but it is a budget, not a proof.
#
# Remediation 5C.2 extended it 25 -> 31 when R4 was widened to see dotted and
# argument-bearing cites: the widening surfaced 8 stdlib/builtin cites that had
# always been in the docs and had always been invisible to the matcher.
OS_CALLS = {
    "fork", "exec", "execve", "execvp", "tcsetpgrp", "tcgetpgrp", "setpgid",
    "getpgid", "setsid", "waitpid", "wait", "kill", "killpg", "open", "close",
    "dup", "dup2", "pipe", "read", "write", "isatty", "sigprocmask", "_exit",
    "exit", "select",
    # Added with the 5C.2 R4 widening — Python builtins and stdlib callables
    # cited in prose, never psh definitions.
    "str", "print", "vars", "execvpe", "getrecursionlimit", "fcntl",
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
# R4 WIDENED (remediation 5C.2): a cite may carry a DOTTED head and ARGUMENTS
# — `io_manager.guarded_redirections(node.redirects)`. CALL_RE demanded a bare
# name and EMPTY parens, so that whole shape was structurally invisible and a
# deleted symbol could sit in a live orientation doc indefinitely. It did: the
# 5C.2 verify round found `io_manager.with_redirections(node.redirects)` still
# taught in docs/architecture/ast_data_flow.md after the symbol was deleted.
# The callable is the LAST dotted segment, which is the name a `def` would
# bind.
# ONE pattern, so group(1) is ALWAYS the callable: an alternation with two
# branches would leave group(1) None on the second and silently skip the check.
WIDE_CALL_RE = re.compile(
    r"^(?:[A-Za-z_][A-Za-z0-9_]*\.)*([a-z_][A-Za-z0-9_]*)\((.*)\)$")


def _is_shell_syntax(token: str) -> bool:
    """True for SHELL constructs that merely look like calls.

    psh's docs are full of shell, and widening the matcher means it now sees
    things like ``for(( ))`` and ``$(( ))``. A structural rule beats another
    hand-list here: doubled parens are arithmetic/C-style-for syntax, and a
    leading ``$`` is an expansion — neither is ever a Python callable.
    """
    return "((" in token or token.startswith("$")
# R5/R6: **File**: markers and definitions inside fenced blocks.
MARKER_RE = re.compile(r"^\*\*Files?\*\*:(.*)$", re.MULTILINE)
DEF_RE = re.compile(r"^(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


@pytest.fixture(scope="module")
def source_corpus():
    """{path: text} for every production, test, AND tools Python file.

    Q2 (S2 widening carry): ``tools/`` is scanned too, so a doc pointer to a
    tools symbol (``def``/``ClassName``/``function()``) resolves instead of
    silently failing R3/R4 or being invisible."""
    corpus = {}
    for base in ("psh", "tests", "tools"):
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
    # Q2 (S2 widening carry): a documented ClassName may be defined under psh/,
    # tests/, OR tools/ — resolve against the whole corpus, not just psh/.
    pattern = re.compile(rf"^class {re.escape(cls)}\b", re.MULTILINE)
    return [path for path, text in corpus.items() if pattern.search(text)]


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
                failures.append(f"R3 class not found in psh/tests/tools/: `{token}`")
            elif not any(
                re.search(rf"\b{re.escape(member)}\b", corpus[f]) for f in files
            ):
                failures.append(
                    f"R3 `{token}`: `{member}` absent from file(s) defining "
                    f"class {cls}"
                )
            continue
        call = CALL_RE.match(token) or WIDE_CALL_RE.match(token)
        if call:
            name = call.group(1)
            if name in OS_CALLS:
                continue
            if _is_shell_syntax(token):
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
    assert (PROJECT_ROOT / "CLAUDE.md").is_file()  # Q2: root orientation doc scanned
    assert (PROJECT_ROOT / "docs/architecture/ast_data_flow.md").is_file()
    assert (PROJECT_ROOT / "docs/architecture/tour_of_psh_internals.md").is_file()
    # ARCHITECTURE + root CLAUDE + ast_data_flow + tour + command_position
    # + 9 psh CLAUDE.md (+ any tests/**/CLAUDE.md).
    assert len(DOC_FILES) >= 13
    assert (PROJECT_ROOT / "CLAUDE.md") in DOC_FILES


# ---------------------------------------------------------------------------
# Guard-the-guard for the 5C.2 R4 widening. Before it, R4 matched only a bare
# name with EMPTY parens, so `obj.method(arg)` was structurally invisible — and
# a symbol deleted in one commit sat in a live orientation doc until a human
# happened to read it. These arms exist so the widening cannot silently regress
# to that.
# ---------------------------------------------------------------------------

def _failures_for(text, corpus, tmp_path):
    doc = tmp_path / "synthetic.md"
    doc.write_text(text, encoding="utf-8")
    return _check_inline_tokens(doc, corpus)


def test_offender_widened_r4_catches_a_dangling_dotted_cite(
        source_corpus, tmp_path):
    """OFFENDER: a dotted, argument-bearing cite to a nonexistent callable.

    This is the exact shape that produced the 5C.2 blocker.
    """
    failures = _failures_for(
        "Executors apply it with `io_manager.no_such_member(node.redirects)`.",
        source_corpus, tmp_path)
    assert failures, "a dangling dotted cite must be caught"
    # Reason asserted, not just the outcome: a failure for some OTHER rule
    # would prove nothing about R4.
    assert any("R4" in f and "no_such_member" in f for f in failures), failures


def test_control_widened_r4_passes_a_REAL_dotted_cite(source_corpus, tmp_path):
    """CONTROL: the corrected line itself must PASS.

    Without this the widening could be 'satisfied' by a matcher that flags
    every dotted call, which would fail the real doc and get reverted.
    """
    failures = _failures_for(
        "Executors apply it with `io_manager.guarded_redirections(node.redirects)`.",
        source_corpus, tmp_path)
    assert not failures, failures


def test_control_widened_r4_passes_a_stdlib_cite(source_corpus, tmp_path):
    """CONTROL: an exempt stdlib/builtin cite must PASS.

    The widening surfaced 8 of these that had always been in the docs. If the
    exemption stopped working they would all fail at once and the pressure
    would be to revert the widening rather than fix the list.
    """
    failures = _failures_for(
        "It prints with `print(..., file=sys.stderr)` and `str(error)`.",
        source_corpus, tmp_path)
    assert not failures, failures


def test_control_widened_r4_ignores_shell_syntax(source_corpus, tmp_path):
    """CONTROL: shell constructs are not Python callables.

    psh's docs are largely about shell, so the widened matcher sees things
    like `for(( ))`. A structural rule (doubled parens, leading `$`) keeps
    them out without another hand-list.
    """
    failures = _failures_for(
        "The C-style form is `for(( ))` and arithmetic is `$(( ))`.",
        source_corpus, tmp_path)
    assert not failures, failures
