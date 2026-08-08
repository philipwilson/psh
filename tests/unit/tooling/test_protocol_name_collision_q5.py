"""Guard: a Protocol's name is unique across all classes in ``psh`` (5B.1).

Checkpoint R found two live collisions in which a ``Protocol`` and an unrelated
CONCRETE class shared a name:

* ``ExpansionContext`` — Protocol in ``psh/protocols/__init__.py`` vs the lexer's
  concrete class in ``psh/lexer/expansion_parser.py``;
* ``LocaleContext`` — Protocol in ``psh/protocols/__init__.py`` vs the frozen
  dataclass in ``psh/core/locale_service.py``.

The cost is not aesthetic. A protocol exists so a reader (and mypy) can see WHAT
a consumer depends on; when the name also denotes a concrete class, a reference
no longer says which, and a census that counts NAMES silently conflates the two.
That is exactly how the Checkpoint R usage census reported consumers for a
protocol that had none — a ``modular_lexer`` hit for "ExpansionContext" was the
lexer class all along.

**Scope: deliberately narrow.** The rule fires only when at least one definition
of a duplicated name is a ``Protocol``. Concrete-concrete duplicates
(``CasePhase``, ``Complete``, ``Parser`` at the time of writing) are NOT
offenders: they are ordinary, locally-unambiguous names, and conscripting them
would turn a targeted guard into a tree-wide renaming project. A guard scoped
instead to Protocol-vs-Protocol only would have been GREEN while both real
collisions were live — vacuous, which is the shape this file exists to avoid.

The ``test_guard_*`` self-tests drive the detector over synthetic offenders, so
it cannot rot into a no-op.
"""

import ast
import collections
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"


def class_definitions(root):
    """{class name: [(relpath, lineno, is_protocol)]} for every class in psh/."""
    out = collections.defaultdict(list)
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:  # pragma: no cover - psh always parses
            continue
        rel = str(path.relative_to(root.parent))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                is_proto = any(
                    "Protocol" in ast.unparse(b) for b in node.bases)
                out[node.name].append((rel, node.lineno, is_proto))
    return out


def protocol_name_collisions(definitions):
    """Duplicated class names where at least one definition is a Protocol."""
    return {
        name: sites
        for name, sites in definitions.items()
        if len(sites) > 1 and any(is_proto for _, _, is_proto in sites)
    }


def test_no_protocol_name_collisions():
    offenders = protocol_name_collisions(class_definitions(PSH))
    assert not offenders, (
        "A Protocol shares its name with another class. Rename one side — "
        "prefer the side with fewer consumers — so a reference to the name "
        "identifies exactly one definition:\n  "
        + "\n  ".join(
            f"{name}: " + ", ".join(
                f"{'PROTOCOL' if p else 'CONCRETE'} {rel}:{ln}"
                for rel, ln, p in sites)
            for name, sites in sorted(offenders.items()))
    )


# --- Detector self-tests ----------------------------------------------------

def _defs(**named):
    """Build a definitions mapping without touching the filesystem."""
    return {name: list(sites) for name, sites in named.items()}


def test_guard_flags_protocol_vs_concrete():
    """The shape both real collisions had."""
    offenders = protocol_name_collisions(_defs(
        Dup=[("psh/a.py", 1, True), ("psh/b.py", 2, False)]))
    assert set(offenders) == {"Dup"}


def test_guard_flags_protocol_vs_protocol():
    offenders = protocol_name_collisions(_defs(
        Dup=[("psh/a.py", 1, True), ("psh/b.py", 2, True)]))
    assert set(offenders) == {"Dup"}


def test_guard_ignores_concrete_vs_concrete():
    """Ordinary duplicate class names are not this guard's business."""
    assert protocol_name_collisions(_defs(
        Dup=[("psh/a.py", 1, False), ("psh/b.py", 2, False)])) == {}


def test_guard_ignores_a_unique_protocol():
    assert protocol_name_collisions(_defs(
        Solo=[("psh/a.py", 1, True)])) == {}


def test_guard_reports_only_the_offending_name():
    offenders = protocol_name_collisions(_defs(
        Bad=[("psh/a.py", 1, True), ("psh/b.py", 2, False)],
        FineConcrete=[("psh/c.py", 3, False), ("psh/d.py", 4, False)],
        FineSolo=[("psh/e.py", 5, True)]))
    assert set(offenders) == {"Bad"}


def test_class_definitions_finds_protocols_and_concretes():
    """The real scanner classifies both kinds — so a green
    test_no_protocol_name_collisions cannot be green because the scanner
    found nothing at all."""
    defs = class_definitions(PSH)
    assert len(defs) > 100, "scanner found implausibly few classes"
    protos = {n for n, sites in defs.items()
              if any(is_proto for _, _, is_proto in sites)}
    # The service protocols must be among them, under their current names.
    assert {"ExpansionRuntime", "IOContext",
            "JobRuntime", "LocaleAccess"} <= protos
    # And the renamed-away names must no longer denote a Protocol anywhere.
    assert "ExpansionContext" not in protos
    assert "LocaleContext" not in protos
