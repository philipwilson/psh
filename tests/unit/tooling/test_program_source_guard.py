"""Static guard: ProgramSource is the ONLY program-text entry (F3).

Two chokepoints, both grep-verifiable:

1. **InputSource construction census** — ``FileInput``/``LazyFileInput``/
   ``StringInput``/``StdinInput`` may be constructed only inside
   ``psh/scripting/program_source.py`` (the normalization boundary that
   decides each channel's NUL/byte policy and parse flags) and their own
   defining module. A direct construction elsewhere would reopen a second,
   policy-free path for program text into the parser.

2. **One sourced-file dialect** — ``psh/builtins/source_command.py`` and
   ``psh/interactive/rc_loader.py`` must not run files through
   ``execute_from_source``/``execute_as_main`` or any InputSource
   themselves: both route through ``execute_sourced_file`` so rc cannot
   drift back into a second source dialect (continuation medium 2).

Synthetic-offender self-tests prove each scanner actually fires.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PSH_DIR = REPO_ROOT / "psh"

INPUT_SOURCE_CLASSES = {"FileInput", "LazyFileInput", "StringInput",
                        "StdinInput"}

# The ONLY modules that may construct InputSource objects.
ALLOWED_CONSTRUCTORS = {
    "psh/scripting/program_source.py",   # the normalization boundary
    "psh/scripting/input_sources.py",    # the defining module
}


def _input_source_constructions(source: str, filename: str) -> list:
    """[(lineno, name)] for every InputSource construction/reference.

    AST-based: a ``Call`` whose func is a bare Name or an Attribute ending
    in one of the class names, and any ``from ... import FileInput``-style
    binding (an alias would let a caller construct under another name).
    Comments and docstrings never false-positive.
    """
    hits = []
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in INPUT_SOURCE_CLASSES:
                hits.append((node.lineno, name))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in INPUT_SOURCE_CLASSES:
                    hits.append((node.lineno, f"import {alias.name}"))
    return hits


def test_input_sources_constructed_only_in_program_source():
    offenders = []
    for path in sorted(PSH_DIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWED_CONSTRUCTORS:
            continue
        for lineno, name in _input_source_constructions(path.read_text(), rel):
            offenders.append(f"{rel}:{lineno}: {name}")
    assert not offenders, (
        "InputSource constructed/imported outside the ProgramSource "
        "boundary — program text must enter parsing through "
        "ProgramSource.make_input_source() so the per-channel NUL/byte "
        "policy and parse flags are decided exactly once:\n  "
        + "\n  ".join(offenders)
    )


def test_boundary_is_live():
    """The allowlisted module genuinely constructs all three sources."""
    source = (PSH_DIR / "scripting" / "program_source.py").read_text()
    names = {name for _, name in
             _input_source_constructions(source, "program_source.py")}
    assert INPUT_SOURCE_CLASSES <= names, names


def test_source_and_rc_route_through_the_service():
    """No second sourced-file dialect: both callers use the service only."""
    for rel in ("psh/builtins/source_command.py",
                "psh/interactive/rc_loader.py"):
        source = (REPO_ROOT / rel).read_text()
        assert "execute_sourced_file" in source, rel
        for forbidden in ("execute_from_source", "execute_as_main",
                          "FileInput"):
            assert forbidden not in source, (
                f"{rel} references {forbidden} — sourced-file execution "
                "must go through execute_sourced_file (one dialect, F3)")


def test_scanner_fires_on_synthetic_offenders():
    direct = (
        "from psh.scripting.input_sources import FileInput\n"
        "def sneaky(path):\n"
        "    return FileInput(path)\n"
    )
    hits = _input_source_constructions(direct, "offender.py")
    assert {name for _, name in hits} == {"import FileInput", "FileInput"}

    attribute = (
        "import psh.scripting.input_sources as m\n"
        "def sneaky(cmd):\n"
        "    return m.StringInput(cmd, 'x')\n"
    )
    hits = _input_source_constructions(attribute, "offender2.py")
    assert [name for _, name in hits] == ["StringInput"]

    comment_only = "# FileInput(path) in a comment\nx = 1\n"
    assert _input_source_constructions(comment_only, "clean.py") == []
