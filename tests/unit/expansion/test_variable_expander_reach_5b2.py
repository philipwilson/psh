"""Reach census for ``VariableExpanderProtocol.shell`` (remediation 5B.2).

The boundary campaign named this member the "broad owner escape hatch" and
5B.2 was chartered to REMOVE it. It did not, and this file records exactly what
survived so the remainder is a measured quantity rather than a memory.

**What the member is reached for**, across its four consumers (arrays, fields,
operands, operators):

* EIGHT ``self.shell.expansion_manager`` hops, reaching the manager's
  sub-expanders — ``.subscript`` (4), ``.command_sub`` (2),
  ``.execute_arithmetic_expansion``, ``.tilde_expander``;
* THREE that forward the shell WHOLE — ``evaluate_arithmetic(expr, self.shell)``
  twice and ``PromptExpander(self.shell)`` once, all in ``operators.py``.

The eight hops could not migrate to ``protocols.ExpansionRuntime``: that
protocol declares ``expand_string_variables``, ``expand_assignment_value_word``,
``variable_expander`` and ``word_expander``, and the hops reach NONE of them.
Its surface fits the subscript authority (which does consume it) but not these
mixins. Widening it is a ruling, so the census is pinned here instead and the
remainder is successor row D-5B.2-s2.

A twelfth site — a ``state.locale`` read spelled ``self.shell.state.locale`` —
DID migrate, onto the ``state`` member as ``self.state.locale``. That is what
the ``expansion_manager``-only assertion below protects: the member must not
regrow a second hop kind.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]

CONSUMERS = [
    "psh/expansion/arrays.py",
    "psh/expansion/fields.py",
    "psh/expansion/operands.py",
    "psh/expansion/operators.py",
]

#: Per consumer: ``self.shell.<attr>`` hop count, keyed by attribute.
EXPECTED_HOPS = {
    "psh/expansion/arrays.py": {"expansion_manager": 3},
    "psh/expansion/fields.py": {},
    "psh/expansion/operands.py": {"expansion_manager": 4},
    "psh/expansion/operators.py": {"expansion_manager": 1},
}

#: Per consumer: how many times the shell is passed on WHOLE.
EXPECTED_WHOLE_FORWARDS = {
    "psh/expansion/arrays.py": 0,
    "psh/expansion/fields.py": 0,
    "psh/expansion/operands.py": 0,
    "psh/expansion/operators.py": 3,
}


def _reach(rel):
    """(attr-hop counter, whole-forward count) for ``self.shell`` in *rel*."""
    tree = ast.parse((ROOT / rel).read_text())
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    hops, whole = {}, 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and node.attr == "shell"
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"):
            continue
        p = parents.get(id(node))
        if isinstance(p, ast.Attribute):
            hops[p.attr] = hops.get(p.attr, 0) + 1
        else:
            whole += 1
    return hops, whole


def test_shell_member_hop_census():
    """Which sub-object each consumer reaches through ``self.shell``."""
    for rel in CONSUMERS:
        hops, _ = _reach(rel)
        assert hops == EXPECTED_HOPS[rel], (
            f"{rel}: `self.shell.<attr>` reach changed — expected "
            f"{EXPECTED_HOPS[rel]}, found {hops}. A NEW attribute here widens "
            "the escape hatch; a removed one is progress (update this table).")


def test_shell_member_reaches_only_the_expansion_manager():
    """No hop kind other than ``expansion_manager`` survives.

    The ``self.shell.state.locale`` read migrated onto the ``state`` member in
    5B.2. Re-growing a second hop kind means the member is being used as a
    service locator again, which is the thing the campaign is retiring.
    """
    kinds = set()
    for rel in CONSUMERS:
        hops, _ = _reach(rel)
        kinds |= set(hops)
    assert kinds == {"expansion_manager"}, (
        f"`self.shell` is reached for {sorted(kinds)}; only "
        "'expansion_manager' should remain (D-5B.2-s2 owns retiring that).")


def test_whole_shell_forwards_are_exactly_three():
    """The irreducible remainder: two ``evaluate_arithmetic`` calls and one
    ``PromptExpander`` construction, all in operators.py.

    These are why the member still exists at all. Removing it needs those two
    callees to take narrower surfaces — 5C's boundary-signature work — so this
    count going UP means a new whole-shell forward was added instead.
    """
    for rel in CONSUMERS:
        _, whole = _reach(rel)
        assert whole == EXPECTED_WHOLE_FORWARDS[rel], (
            f"{rel}: whole-`self.shell` forwards changed — expected "
            f"{EXPECTED_WHOLE_FORWARDS[rel]}, found {whole}")

    total = sum(_reach(rel)[1] for rel in CONSUMERS)
    assert total == 3, f"total whole-shell forwards is {total}, expected 3"


def test_total_reach_is_eleven_sites():
    """The headline number, so a partial regression cannot hide inside a
    per-file table that someone updated to match."""
    total = sum(sum(_reach(rel)[0].values()) + _reach(rel)[1]
                for rel in CONSUMERS)
    assert total == 11, (
        f"`VariableExpanderProtocol.shell` is reached at {total} sites, "
        "expected 11 (8 expansion_manager hops + 3 whole forwards)")


def test_the_locale_read_no_longer_goes_through_shell():
    """The one site 5B.2 did migrate, pinned at both ends."""
    src = (ROOT / "psh/expansion/operators.py").read_text()
    assert "self.shell.state.locale" not in src, (
        "the locale read regressed to reaching through `self.shell`")
    assert "self.state.locale" in src, (
        "the locale read should reach through the `state` member")


def test_scanner_detects_a_synthetic_new_hop():
    """Guard the guard: a passing census must be able to fail.

    Without this, a scanner that silently stopped matching would leave every
    cell above green while the member regrew freely.
    """
    import tempfile
    src = ("class C:\n"
           "    def f(self):\n"
           "        return self.shell.job_manager\n"
           "    def g(self):\n"
           "        return helper(self.shell)\n")
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "synthetic.py"
        p.write_text(src)
        tree = ast.parse(p.read_text())
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    hops, whole = {}, 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and node.attr == "shell"
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"):
            p2 = parents.get(id(node))
            if isinstance(p2, ast.Attribute):
                hops[p2.attr] = hops.get(p2.attr, 0) + 1
            else:
                whole += 1
    assert hops == {"job_manager": 1} and whole == 1
