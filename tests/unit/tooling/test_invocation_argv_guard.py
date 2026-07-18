"""Static guard: ``parse_invocation`` is the ONLY argv interpreter (F1).

The frozen ``InvocationConfig`` is only trustworthy if no other production
code can reach around it to ``sys.argv``: a second reader could re-derive
invocation facts after startup and disagree with the config the shell was
constructed from. This ratchet scans every ``psh/`` module for ``sys.argv``
access (attribute use or ``from sys import argv``) and allows exactly the
entry point (``psh/__main__.py``, which passes ``sys.argv[1:]`` to the
parser) and ``psh/invocation.py`` itself (whose docstrings/name the scan
would not flag anyway, but which is the natural home for any future
argv-adjacent helper).

A synthetic-offender self-test proves the scanner actually fires.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PSH_DIR = REPO_ROOT / "psh"

# The ONLY modules that may touch sys.argv.
ALLOWED = {
    "psh/__main__.py",
    # psh/invocation.py is deliberately NOT allowlisted: parse_invocation is
    # pure (argv passed in), and the ratchet holds it to that.
}


def _argv_accesses(source: str, filename: str) -> list:
    """Return [(lineno, snippet)] for every sys.argv access in *source*.

    AST-based, so comments and docstrings never false-positive:
    - ``sys.argv`` attribute access (any expression context);
    - ``from sys import argv`` (with or without alias).
    """
    hits = []
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and node.attr == "argv"
                and isinstance(node.value, ast.Name)
                and node.value.id == "sys"):
            hits.append((node.lineno, "sys.argv"))
        elif isinstance(node, ast.ImportFrom) and node.module == "sys":
            for alias in node.names:
                if alias.name == "argv":
                    hits.append((node.lineno, "from sys import argv"))
    return hits


def test_no_sys_argv_outside_entry_point_and_invocation():
    offenders = []
    for path in sorted(PSH_DIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWED:
            continue
        for lineno, snippet in _argv_accesses(path.read_text(), rel):
            offenders.append(f"{rel}:{lineno}: {snippet}")
    assert not offenders, (
        "sys.argv accessed outside psh/__main__.py + psh/invocation.py — "
        "invocation facts must flow through parse_invocation()'s frozen "
        "InvocationConfig, never be re-derived from argv:\n  "
        + "\n  ".join(offenders)
    )


def test_entry_point_still_reads_argv_once():
    """The entry point genuinely consumes sys.argv (the allowlist is live,
    not vestigial) and hands it straight to parse_invocation."""
    source = (PSH_DIR / "__main__.py").read_text()
    hits = _argv_accesses(source, "psh/__main__.py")
    assert len(hits) == 1, hits
    assert "parse_invocation(sys.argv[1:])" in source


def test_scanner_fires_on_synthetic_offender():
    offender = (
        "import sys\n"
        "def sneaky():\n"
        "    if '--fast' in sys.argv:\n"
        "        return True\n"
    )
    hits = _argv_accesses(offender, "synthetic.py")
    assert hits == [(3, "sys.argv")]


def test_scanner_fires_on_from_import_offender():
    offender = "from sys import argv\nprint(argv)\n"
    hits = _argv_accesses(offender, "synthetic.py")
    assert (1, "from sys import argv") in hits


def test_scanner_ignores_comments_and_strings():
    innocent = (
        "# sys.argv is mentioned here in prose only\n"
        "DOC = 'parse sys.argv elsewhere'\n"
        "def f(argv):\n"
        "    return list(argv)\n"
    )
    assert _argv_accesses(innocent, "synthetic.py") == []
