"""One authority decides ``$name`` vs ``${name}`` in reconstructed source.

Rebuilding shell source from a Word has to choose a spelling for every
variable reference, and the choice is semantic: brace expansion runs BEFORE
parameter expansion, so ``$v{1,2}`` re-forms the names ``v1``/``v2`` while
``${v}{1,2}`` stays ``${v}1``/``${v}2``. When the decision lived in two
places, one of them drifted — the formatter restored braces only before an
``[A-Za-z0-9_]`` char, so ``declare -f`` and ``--format`` dropped them
before a brace expansion and the re-parsed function read other variables::

    v=1 v1=A v2=B; f() { echo ${v}{1,2}; }
    eval "$(declare -f f)"; f      # `11 12`, never `A B`

``psh/ast_nodes/words.py#variable_expansion_text`` now holds the rule and
every code-printing path asks it. This module keeps that true from two
sides: a static ratchet that forbids a second spelling decision in the
rendering trees, and a census that every user-visible printer preserves the
source's braces.

**Ratchet scope and honest limits.** Only ``psh/visitor/`` and
``psh/ast_nodes/`` are scanned — the trees that turn an AST back into text
(a ``${`` elsewhere is a diagnostic message or a scanner, not a rendering).
Three construction shapes are detected: an f-string with interpolation whose
literal text holds ``${``, a ``+`` concatenation with a ``${``-bearing string
constant, and a bare ``'${'`` element of a list/tuple (``''.join`` style).
NOT detected: ``%``/``str.format`` templating, a spelling assembled one
character at a time, or a rendering helper living outside the two scanned
trees. Extend the detector if such a shape ever arrives — do not allowlist
the module.
"""

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# The trees that reconstruct source text from an AST.
RENDERING_ROOTS = ("psh/visitor", "psh/ast_nodes")

# The one file allowed to spell a variable reference.
OWNER = "psh/ast_nodes/words.py"


def _docstring_nodes(tree: ast.AST) -> set:
    """ids of the Constant nodes that are docstrings (prose, not code)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


def _is_brace_constant(node) -> bool:
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)
            and "${" in node.value)


def find_brace_spellings(root: Path):
    """[(relative path, lineno, shape)] for every ``${…}`` construction."""
    hits = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text())
        docstrings = _docstring_nodes(tree)
        try:
            rel = path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            rel = path.as_posix()   # a synthetic tree in the offender test
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                literal = "".join(
                    v.value for v in node.values
                    if isinstance(v, ast.Constant) and isinstance(v.value, str))
                interpolated = any(isinstance(v, ast.FormattedValue)
                                   for v in node.values)
                if interpolated and "${" in literal:
                    hits.append((rel, node.lineno, "f-string"))
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                if _is_brace_constant(node.left) or _is_brace_constant(node.right):
                    hits.append((rel, node.lineno, "concatenation"))
            elif isinstance(node, (ast.List, ast.Tuple)):
                for elt in node.elts:
                    if (isinstance(elt, ast.Constant) and elt.value == "${"
                            and id(elt) not in docstrings):
                        hits.append((rel, node.lineno, "sequence element"))
    return hits


def test_only_the_owner_spells_a_variable_reference():
    """No module but the owner builds a ``${…}`` string in a rendering tree."""
    strays = []
    for root in RENDERING_ROOTS:
        for rel, lineno, shape in find_brace_spellings(PROJECT_ROOT / root):
            if rel != OWNER:
                strays.append(f"{rel}:{lineno} ({shape})")
    assert not strays, (
        "a second ``${…}`` spelling decision appeared; route it through "
        f"{OWNER}#variable_expansion_text instead:\n  " + "\n  ".join(strays))


def test_the_owner_is_actually_found_by_the_scan():
    """Negative control: the scan is not vacuously empty."""
    hits = find_brace_spellings(PROJECT_ROOT / "psh/ast_nodes")
    assert any(rel == OWNER for rel, _, _ in hits), hits


@pytest.mark.parametrize("offender,shape", [
    ('def render(name):\n    return f"${{{name}}}"\n', "f-string"),
    ("def render(name):\n    return '${' + name + '}'\n", "concatenation"),
    ("def render(name):\n    return ''.join(['${', name, '}'])\n",
     "sequence element"),
])
def test_synthetic_offender_is_rejected(tmp_path, offender, shape):
    """A hand-rolled spelling in a rendering tree is caught."""
    (tmp_path / "sneaky_renderer.py").write_text(textwrap.dedent(offender))
    hits = find_brace_spellings(tmp_path)
    assert any(s == shape for _, _, s in hits), hits


@pytest.mark.parametrize("source", [
    "def has_default(text):\n    return text.find('${') != -1\n",
    "MESSAGE = 'use ${var:-default}'\n",
    'def f():\n    """Handles ${x} forms."""\n',
])
def test_scanner_does_not_flag_scans_or_messages(tmp_path, source):
    """Reading ``${`` out of text, or naming it in prose, is not a spelling."""
    (tmp_path / "innocent.py").write_text(textwrap.dedent(source))
    assert find_brace_spellings(tmp_path) == []


# ---------------------------------------------------------------------------
# Consumer census: every user-visible printer keeps the source's braces.
# ---------------------------------------------------------------------------

_DEFS = "v=1; v1=A; v2=B; f() { echo ${v}{1,2}; };"

CONSUMERS = [
    ("declare -f", ["-c", f"{_DEFS} declare -f f"]),
    ("typeset -f", ["-c", f"{_DEFS} typeset -f f"]),
    ("type", ["-c", f"{_DEFS} type f"]),
    ("command -V", ["-c", f"{_DEFS} command -V f"]),
    ("export -f", ["-c", f"{_DEFS} export -f f; export -f"]),
    ("--format", ["--format", "-c", f"{_DEFS} true"]),
    ("--debug-ast", ["--debug-ast", "-c", "echo ${v}{1,2}"]),
    ("BASH_COMMAND",
     ["-c", 'trap \'echo "BC=[$BASH_COMMAND]"\' DEBUG; echo ${v}{1,2}']),
]


@pytest.mark.parametrize("name,args", CONSUMERS, ids=[c[0] for c in CONSUMERS])
def test_every_printer_keeps_the_source_braces(name, args):
    r = subprocess.run([sys.executable, "-m", "psh", *args],
                       cwd=PROJECT_ROOT, capture_output=True, text=True,
                       timeout=30)
    # --debug-ast writes its dump to stderr; every other printer uses stdout.
    printed = r.stdout + r.stderr
    assert "${v}{1,2}" in printed, f"{name}: {printed!r}"
    assert "$v{1,2}" not in printed.replace("${v}{1,2}", ""), printed
