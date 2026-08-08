"""Census pins for the 5B consumer migration (remediation 5B.2).

Package 5B's exit criterion is that no service protocol is DEFINED BUT UNUSED —
a protocol with zero consumers documents an intention, not a dependency, and
the boundary campaign shipped three of them. 5B.2 adopted the witnesses, and
these cells keep the result honest in both directions.

**Consumers are resolved PER DEFINITION, never by name.** A module consumes a
protocol when it imports that name FROM the module that defines it and then
uses it in an annotation or as a base. Counting name hits instead is exactly
how the Checkpoint R census reported consumers for a protocol that had none (a
``modular_lexer`` hit for "ExpansionContext" was the concrete lexer class all
along), and it is why ``test_protocol_name_collision_q5.py`` exists.

The zero-consumer register below is a RATCHET, not an excuse list: an entry
must still be genuinely zero, so a protocol that gains a consumer fails the
test until its entry is deleted. It is currently EMPTY — the one protocol that
could not find a consumer was deleted rather than parked in it.
"""

import ast
import pathlib

import psh.protocols as P

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"

#: Protocols that STILL have zero production consumers, each with the reason
#: adoption did not land. Shrink-only: remove an entry when it gains a
#: consumer (the test below fails until you do).
#:
#: EMPTY, and that is the point. 5B.2 briefly registered the variable
#: value-surface protocol here while its fate was open; the fate was ruled
#: DELETE, so the entry left with the protocol rather than becoming a
#: permanent excuse. An empty register means every protocol this package
#: exports is genuinely depended upon by production code.
ZERO_CONSUMER_PENDING_RULING: dict = {}


def _module_dotted(path):
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve_relative(cur_mod, node, is_package):
    parts = cur_mod.split(".")
    pkg = list(parts) if is_package else parts[:-1]
    up = node.level - 1
    if up > 0:
        pkg = pkg[:-up] if up <= len(pkg) else []
    target = ".".join(pkg)
    if node.module:
        target = f"{target}.{node.module}" if target else node.module
    return target


def _names_in_annotations(tree):
    """Every identifier used in an annotation, including inside string
    forward-refs (the migrations annotate via strings, so a scanner that only
    walked real expressions would see none of them)."""
    found = set()

    def record(ann):
        if ann is None:
            return
        for n in ast.walk(ann):
            if isinstance(n, ast.Name):
                found.add(n.id)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                try:
                    sub = ast.parse(n.value, mode="eval")
                except SyntaxError:
                    continue
                for m in ast.walk(sub):
                    if isinstance(m, ast.Name):
                        found.add(m.id)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            for p in (list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
                      + ([a.vararg] if a.vararg else [])
                      + ([a.kwarg] if a.kwarg else [])):
                record(p.annotation)
            record(node.returns)
        elif isinstance(node, ast.AnnAssign):
            record(node.annotation)
    return found


def protocol_consumers(proto_name, defining_module="psh.protocols"):
    """Production modules that import *proto_name* from its DEFINING module and
    then use it (annotation or base). Never a name-only match."""
    consumers = []
    for path in sorted(PSH.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module = _module_dotted(path)
        if module == defining_module:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:  # pragma: no cover - psh always parses
            continue
        imported = False
        aliases = {proto_name}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                src = (_resolve_relative(module, node, path.name == "__init__.py")
                       if node.level else node.module)
                if src != defining_module:
                    continue
                for a in node.names:
                    if a.name == proto_name:
                        imported = True
                        aliases.add(a.asname or a.name)
        if not imported:
            continue
        used = bool(_names_in_annotations(tree) & aliases)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if {ast.unparse(b) for b in node.bases} & aliases:
                    used = True
        if used:
            consumers.append(str(path.relative_to(ROOT)))
    return consumers


def test_every_exported_protocol_has_a_production_consumer():
    """5B's exit criterion, as an executable check."""
    unused = {}
    for name in P.__all__:
        if name in ZERO_CONSUMER_PENDING_RULING:
            continue
        if not protocol_consumers(name):
            unused[name] = "no production consumer"
    assert not unused, (
        "Protocol(s) defined but UNUSED — 5B's exit criterion forbids it. "
        "Either adopt a witness consumer or register the protocol in "
        f"ZERO_CONSUMER_PENDING_RULING with its reason: {sorted(unused)}")


def test_zero_consumer_register_is_still_accurate():
    """The register may only SHRINK: a protocol listed as having no consumer
    must genuinely still have none.

    Without this, the register becomes a place where a resolved item sits
    forever claiming to be open — which is how an exception list stops
    describing the tree.
    """
    stale = {name: protocol_consumers(name)
             for name in ZERO_CONSUMER_PENDING_RULING}
    stale = {n: c for n, c in stale.items() if c}
    assert not stale, (
        "These protocols now HAVE production consumers, so their "
        f"ZERO_CONSUMER_PENDING_RULING entries are stale — delete them: {stale}")


def test_every_register_entry_carries_a_reason():
    for name, reason in ZERO_CONSUMER_PENDING_RULING.items():
        assert isinstance(reason, str) and len(reason.strip()) >= 40, (
            f"{name} needs a real reason, not a placeholder")


def test_the_adopted_witnesses_are_the_expected_ones():
    """The 5B.2 adoptions, pinned by consumer FILE so a silent revert shows up.

    Asserted as subsets: a future slot may add consumers, but it may not
    remove these without this cell going red.
    """
    assert "psh/expansion/subscript.py" in protocol_consumers("ExpansionRuntime")

    locale = set(protocol_consumers("LocaleAccess"))
    # The SIX `state.locale` readers (5B.1's corrected census), all adopted.
    assert {
        "psh/core/scope.py",
        "psh/executor/array.py",
        "psh/executor/enhanced_test_evaluator.py",
        "psh/expansion/glob.py",
        "psh/expansion/operators.py",
        "psh/expansion/parameter_expansion.py",
    } <= locale, sorted(locale)

    assert "psh/executor/foreground_session.py" in protocol_consumers("JobRuntime")
    io = set(protocol_consumers("IOContext"))
    assert {"psh/builtins/input_reader.py",
            "psh/io_redirect/input_cursor.py"} <= io, sorted(io)


def test_consumer_resolution_ignores_a_same_named_import_from_elsewhere():
    """Guard the guard: the resolver must key on the DEFINING module.

    A module importing an unrelated class that happens to share a protocol's
    name is not a consumer — the exact confusion the Checkpoint R census made.
    """
    consumers = protocol_consumers("LocaleAccess",
                                   defining_module="psh.core.locale_service")
    assert consumers == [], (
        "resolver matched on NAME rather than defining module: "
        f"{consumers}")


# --- The deleted protocol stays deleted -------------------------------------

#: The variable value-surface protocol the boundary campaign defined and
#: remediation 5B.2 removed. Named here ONCE, in the pin that keeps it gone.
DELETED_PROTOCOL = "VariableAccess"


def test_the_deleted_value_surface_protocol_has_no_production_references():
    """Grep-zero: the deleted protocol is absent from ``psh/`` entirely.

    It modelled a three-member value surface and never gained a consumer,
    because the boundary it was designed for reaches 11 distinct ``ShellState``
    members and 44 of its 47 sites fall outside those three. Deleting it was a
    ruled amendment to the campaign's own protocol-fate matrix; this cell stops
    it being reintroduced by a well-meaning revert.

    A future value-surface protocol is welcome — designed against the measured
    11-member usage recorded in ``VariableExpanderProtocol.state``'s docstring,
    not against the three-member guess. That is a new name and a new design,
    which is exactly why this pin keys on the OLD one.
    """
    offenders = []
    for path in sorted(PSH.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if DELETED_PROTOCOL in path.read_text():
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        f"{DELETED_PROTOCOL} was deleted by remediation 5B.2 but is "
        f"referenced again in: {offenders}")


def test_the_deleted_protocol_is_not_exported():
    assert DELETED_PROTOCOL not in P.__all__
    assert not hasattr(P, DELETED_PROTOCOL)


def test_grep_zero_pin_would_notice_a_reintroduction():
    """Guard the guard: the scan must be able to find the name.

    A pin that greps for a string in a tree it is not really reading passes
    forever. This proves the same scan finds a name that IS present.
    """
    present = [p for p in PSH.rglob("*.py")
               if "__pycache__" not in p.parts
               and "ExpansionRuntime" in p.read_text()]
    assert present, "the scan found no file containing a live protocol name"
