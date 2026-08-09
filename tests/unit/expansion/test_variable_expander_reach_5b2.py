"""Adoption census for ``VariableExpanderProtocol.host`` (remediation 5C.1).

**This file used to pin the RETIREMENT DEBT; it now pins the RETIREMENT.**

The boundary campaign named ``VariableExpanderProtocol.shell`` the "broad owner
escape hatch". 5B.2 was chartered to remove it and could not, and the previous
version of this file recorded exactly what survived: eight
``self.shell.expansion_manager`` hops plus three whole-``Shell`` forwards, ELEVEN
sites, with the count asserted so the remainder stayed a measured quantity.

5C.1 removed it. The obstacle was never the mixins — it was that the two things
they FORWARD to (``evaluate_arithmetic`` and ``PromptExpander``) each took a
whole ``Shell``, so the mixins could not be narrower than their callees. Typing
those two signatures against ``protocols.ExpansionHost`` dissolved that, and the
hop set became ``ExpansionSubExpanders``, composed with ``ExpansionRuntime``
into the ``ExpansionSurface`` that ``ExpansionHost.expansion_manager`` returns.

The cells below are the SUCCESSORS of the four that pinned the debt, and they
are deliberately not weaker:

* the hop census still runs, now over ``self.host`` — the same per-file counts,
  so a hop that quietly reappeared elsewhere would still show;
* ``test_no_consumer_reaches_a_whole_shell`` is the grep-zero: ``self.shell``
  must not exist in any of the four consumers at all;
* the whole-``Shell`` forward count, previously pinned at exactly 3, is now
  pinned at exactly **0**;
* the headline total, previously 11, is now **0** whole-``Shell`` reach with
  the 8 hops accounted for on the narrow member.

The member is RENAMED as well as retyped, and that is load-bearing rather than
cosmetic: the consumer ratchet's instance-assignment detector keys on the FIELD
NAME, so a ``self.shell`` that merely changed type would still be — and should
still be — reported as a service-locator reach.
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

#: Every holder whose field remediation 5C.1 renamed ``shell`` -> ``host``.
#: The grep-zero cell sweeps ALL of them, not just the four mixin consumers:
#: verify-round N-5 found prompt.py and parameter_expansion.py outside the
#: original sweep, so a regrown ``self.shell`` in either would have passed
#: every cell in this file. subscript.py is additionally covered by the
#: consumer ratchet (it is a scanned module there); the other two are not
#: covered anywhere else, which is precisely why they belong here.
RENAMED_HOLDERS = CONSUMERS + [
    "psh/expansion/variable.py",
    "psh/expansion/subscript.py",
    "psh/expansion/parameter_expansion.py",
    "psh/interactive/prompt.py",
]

#: Per consumer: ``self.host.<attr>`` hop count, keyed by attribute.
EXPECTED_HOPS = {
    "psh/expansion/arrays.py": {"expansion_manager": 3},
    "psh/expansion/fields.py": {},
    "psh/expansion/operands.py": {"expansion_manager": 4},
    "psh/expansion/operators.py": {"expansion_manager": 1},
}

#: Per consumer: how many times the HOST is passed on whole. All three of
#: operators.py's forwards survive as forwards -- what changed is WHAT is
#: forwarded: `ExpansionHost` rather than `Shell`. Forwarding a narrow surface
#: is not the debt; forwarding the whole shell was.
EXPECTED_WHOLE_FORWARDS = {
    "psh/expansion/arrays.py": 0,
    "psh/expansion/fields.py": 0,
    "psh/expansion/operands.py": 0,
    "psh/expansion/operators.py": 3,
}


def _reach(rel, field="host"):
    """(attr-hop counter, whole-forward count) for ``self.<field>`` in *rel*."""
    tree = ast.parse((ROOT / rel).read_text())
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    hops, whole = {}, 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and node.attr == field
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"):
            continue
        p = parents.get(id(node))
        if isinstance(p, ast.Attribute):
            hops[p.attr] = hops.get(p.attr, 0) + 1
        else:
            whole += 1
    return hops, whole


def test_host_member_hop_census():
    """Which sub-object each consumer reaches through ``self.host``.

    Successor to the ``self.shell`` hop census. The per-file counts are
    UNCHANGED (3/0/4/1) because the hops did not move -- only the type of what
    they hop through did. Keeping the counts means a hop that reappeared
    somewhere new still shows up here.
    """
    for rel in CONSUMERS:
        hops, _ = _reach(rel)
        assert hops == EXPECTED_HOPS[rel], (
            f"{rel}: `self.host.<attr>` reach changed — expected "
            f"{EXPECTED_HOPS[rel]}, found {hops}. A NEW attribute here widens "
            "the host's use; a removed one is progress (update this table).")


def test_host_member_reaches_only_the_expansion_manager():
    """No hop kind other than ``expansion_manager`` survives.

    ``ExpansionHost`` also carries ``.state``, but the mixins reach state
    through their OWN ``state`` member, not through the host. A second hop kind
    appearing here would mean the host is being used as a service locator
    again, which is the thing this campaign retires.
    """
    kinds = set()
    for rel in CONSUMERS:
        hops, _ = _reach(rel)
        kinds |= set(hops)
    assert kinds == {"expansion_manager"}, (
        f"`self.host` is reached for {sorted(kinds)}; only 'expansion_manager' "
        "should appear.")


def test_no_consumer_reaches_a_whole_shell():
    """GREP-ZERO: the retirement itself.

    The predecessor of this cell asserted the member reached the whole ``Shell``
    at ELEVEN sites and pinned that number so it could not grow. The successor
    asserts the member does not exist: no consumer holds ``self.shell`` at all.

    This is why the field was RENAMED rather than only retyped -- a
    ``self.shell`` annotated ``ExpansionHost`` would satisfy every other cell in
    this file while still reading, to the consumer ratchet and to a human, as
    the service-locator reach the campaign set out to remove.
    """
    offenders = {}
    for rel in RENAMED_HOLDERS:
        hops, whole = _reach(rel, field="shell")
        if hops or whole:
            offenders[rel] = (hops, whole)
    assert not offenders, (
        "`self.shell` is still reached in a variable-expander consumer — the "
        f"whole-Shell escape hatch has regrown: {offenders}")


def test_whole_shell_forwards_are_zero():
    """The three forwards that KEPT the escape hatch alive now forward a
    narrow surface.

    Previously: exactly 3 whole-``Shell`` forwards, all in operators.py
    (``evaluate_arithmetic`` twice, ``PromptExpander`` once), and they were the
    reason the member could not retire -- the mixins cannot be narrower than
    what they forward to. Both callees now take ``ExpansionHost``, so the
    forwards remain but carry the narrow type; what must be ZERO is forwards of
    a whole ``Shell``, which is what the grep-zero cell above establishes.
    """
    for rel in CONSUMERS:
        _, whole = _reach(rel)
        assert whole == EXPECTED_WHOLE_FORWARDS[rel], (
            f"{rel}: whole-`self.host` forwards changed — expected "
            f"{EXPECTED_WHOLE_FORWARDS[rel]}, found {whole}")
    shell_forwards = sum(_reach(rel, field="shell")[1] for rel in CONSUMERS)
    assert shell_forwards == 0, (
        f"{shell_forwards} whole-`self.shell` forward(s) remain; the "
        "retirement requires zero")


def test_total_host_reach_accounts_for_the_retired_eleven():
    """The headline, restated for the post-retirement state.

    The predecessor pinned 11 sites of whole-``Shell`` reach (8 hops + 3
    forwards). The successor pins where those 11 went: 8 hops and 3 forwards
    still exist, on the NARROW member, and whole-``Shell`` reach is 0. Pinning
    the total rather than only the per-file table keeps a partial regression
    from hiding inside a table someone updated to match.
    """
    hops = sum(sum(_reach(rel)[0].values()) for rel in CONSUMERS)
    forwards = sum(_reach(rel)[1] for rel in CONSUMERS)
    assert (hops, forwards) == (8, 3), (
        f"host reach is {hops} hops + {forwards} forwards, expected 8 + 3")
    shell_total = sum(sum(_reach(rel, field="shell")[0].values())
                      + _reach(rel, field="shell")[1] for rel in CONSUMERS)
    assert shell_total == 0, (
        f"whole-`Shell` reach is {shell_total}, expected 0 after retirement")


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
