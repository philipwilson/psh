"""Static ratchet: the pipeline-member exec-in-place rule has ONE owner (C001).

The C001 defect class is *a second reader of the exec-in-place decision*. The
rule "this member's top-level simple command may execve() in place" used to
live in a durable ``in_pipeline`` flag that every nested frame inherited, so
a function body / ``eval`` text / sourced file exec-replaced the member
process and silently lost every command after the first external one. The
fix makes it a ONE-SHOT token owned by
``psh/executor/context.py#ExecutionContext.for_pipeline_member`` and spent by
``take_exec_in_place`` on the member's own dispatch.

That fix survives only while nobody re-reads the decision somewhere else, so
this ratchet fixes each name to the files entitled to it:

* ``in_pipeline`` — the retired name. Nowhere in ``psh/``, in code OR prose,
  so a revival cannot hide in a comment that later grows back into a field.
* ``exec_in_place_token`` / ``take_exec_in_place`` — the token and its single
  consumer: ``context.py`` only. A second consumer would hand a nested frame
  a live token.
* ``exec_in_place`` — the per-dispatch answer: the owner (``context.py``),
  the writer that grants the token (``pipeline.py``), and the exec branch
  that reads it (``strategies.py``).
* ``exec_in_place_decision`` — the binder and the single gateway that enters
  it once per simple command (``command.py``).
* ``is_pipeline_member`` — the DIFFERENT, durable question ("is this process
  a pipeline member?"), read only by ``strategies.py``. Keeping it separate
  is what stops it from drifting back into a second exec-in-place flag.
* ``for_pipeline_member`` — the owner and the one site that calls it.

Each rule is self-tested against a synthetic offender, so the scanner cannot
rot into a no-op.
"""

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"

EXECUTOR = "psh/executor"

# identifier -> the relative paths entitled to mention it.
ALLOWED = {
    "exec_in_place_token": {f"{EXECUTOR}/context.py"},
    "take_exec_in_place": {f"{EXECUTOR}/context.py"},
    "exec_in_place": {f"{EXECUTOR}/context.py",
                      f"{EXECUTOR}/pipeline.py",
                      f"{EXECUTOR}/strategies.py"},
    "exec_in_place_decision": {f"{EXECUTOR}/context.py",
                               f"{EXECUTOR}/command.py"},
    "is_pipeline_member": {f"{EXECUTOR}/context.py",
                           f"{EXECUTOR}/strategies.py"},
    "for_pipeline_member": {f"{EXECUTOR}/context.py",
                            f"{EXECUTOR}/pipeline.py"},
}

RETIRED = "in_pipeline"
RETIRED_RE = re.compile(rf"\b{RETIRED}\b")


def _sources():
    """Yield (relative path, text) for every module in psh/."""
    for path in sorted(PSH.rglob("*.py")):
        yield path.relative_to(ROOT).as_posix(), path.read_text()


def identifiers_used(source: str):
    """Return the set of ratcheted identifiers *source* mentions in CODE.

    AST-based: attribute access, bare names, keyword arguments and parameter
    names all count, because each is a way to read or write the decision.
    Comments and docstrings do not — they are handled by the retired-name
    rule, which is deliberately stricter.
    """
    used = set()

    def note(name):
        if name in ALLOWED:
            used.add(name)

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute):
            note(node.attr)
        elif isinstance(node, ast.Name):
            note(node.id)
        elif isinstance(node, ast.keyword) and node.arg is not None:
            note(node.arg)
        elif isinstance(node, ast.arg):
            note(node.arg)
        elif isinstance(node, ast.FunctionDef):
            note(node.name)
    return used


def scan_tree():
    """Return [(relpath, identifier)] for every entitlement violation."""
    offenders = []
    for relpath, text in _sources():
        for name in identifiers_used(text):
            if relpath not in ALLOWED[name]:
                offenders.append((relpath, name))
    return sorted(offenders)


def retired_name_hits():
    """Return [(relpath, lineno)] for every ``in_pipeline`` mention in psh/."""
    hits = []
    for relpath, text in _sources():
        for lineno, line in enumerate(text.splitlines(), 1):
            if RETIRED_RE.search(line):
                hits.append((relpath, lineno))
    return hits


def test_exec_in_place_decision_has_one_owner():
    """No module outside the entitled set reads the exec-in-place rule."""
    offenders = scan_tree()
    assert offenders == [], (
        "a new reader of the pipeline-member exec-in-place decision appeared. "
        "The decision is a one-shot owned by ExecutionContext."
        "for_pipeline_member and spent once per simple command — read what you "
        f"actually need instead (state.in_forked_child, is_pipeline_member): "
        f"{offenders}")


def test_retired_in_pipeline_name_is_gone():
    """``in_pipeline`` is retired: not code, not prose, anywhere in psh/.

    Repro the flag caused: `f(){ /bin/echo A; echo B; }; f | cat` printed
    only A because every nested frame inherited it (C001).
    """
    hits = retired_name_hits()
    assert hits == [], (
        "`in_pipeline` is the retired durable flag whose inheritance caused "
        f"C001 (silent data loss); use the one-shot token instead: {hits}")


def test_ratchet_flags_a_synthetic_offender_module(tmp_path):
    """A new module reading the one-shot is caught (mutation check)."""
    offender = tmp_path / "sneaky_reader.py"
    offender.write_text(
        "def decide(context):\n"
        "    if context.exec_in_place:\n"
        "        return 'exec'\n"
        "    return 'fork'\n"
    )
    used = identifiers_used(offender.read_text())
    assert "exec_in_place" in used
    assert offender.relative_to(tmp_path).as_posix() not in ALLOWED["exec_in_place"]


def test_ratchet_flags_each_ratcheted_identifier():
    """Every entry in ALLOWED is actually detectable (no dead rule)."""
    shapes = {
        "exec_in_place_token": "def f(c):\n    return c.exec_in_place_token\n",
        "take_exec_in_place": "def f(c):\n    return c.take_exec_in_place()\n",
        "exec_in_place": "def f(c):\n    return c.exec_in_place\n",
        "exec_in_place_decision": "def f(c):\n    return c.exec_in_place_decision()\n",
        "is_pipeline_member": "def f(c):\n    return c.is_pipeline_member\n",
        "for_pipeline_member": "def f(c):\n    return c.for_pipeline_member(exec_in_place=True)\n",
    }
    assert set(shapes) == set(ALLOWED), "add a synthetic offender for each rule"
    for name, source in shapes.items():
        assert name in identifiers_used(source), name


def test_ratchet_flags_a_retired_name_revival():
    """The retired-name rule catches prose as well as code (mutation check)."""
    assert RETIRED_RE.search("        if context.in_pipeline:")
    assert RETIRED_RE.search("# restore in_pipeline for the body")
    # Not a substring match: the durable successor must not trip it.
    assert not RETIRED_RE.search("context.is_pipeline_member")
