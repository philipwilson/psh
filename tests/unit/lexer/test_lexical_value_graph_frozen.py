"""The COMPLETE lexical value graph is frozen (remediation 2.5, #22 MEDIUM-10b).

`LexedUnit.tokens` was already a tuple and its heredoc map a read-only mapping,
but every frozen `Token` in it handed out a mutable `parts` LIST of mutable
`TokenPart` objects -- so a lexed value could be rewritten after the lexer had
returned it. A probe at base e36116c3 rewrote a real lexed `echo "a$b"c` from
`[('a','"'), ('b','"')]` to `[('PWNED',"'"), ('b','"'), ('PWNED',"'")]`.

WHY THE GUARD IS TRANSITIVE, and what it cost to learn: round-1 verification
found the FIRST version of this module asserted only that REBINDING a TokenPart
attribute raised. Its universe was therefore "TokenPart attribute rebinding",
not "every edge of the value graph" -- and the gap was not hypothetical.
`TokenPart.start_pos`/`end_pos` held plain `Position` dataclasses, so the exact
shape MEDIUM-10b named (container frozen, contents mutable) survived ONE LEVEL
DOWN: `part.start_pos.offset = 999` succeeded and was visible on the stored
value. A field-NAME enumeration could never have caught that, because the
offending object is not a field of TokenPart -- it is a field's VALUE.

So the census below WALKS THE LIVE GRAPH: it starts from a real `LexedUnit` and
visits every reachable object, flagging (a) any dataclass that is not frozen and
(b) any mutable container. The universe is discovered at runtime, so a new
field, a new node type, or a new nesting level is covered automatically and
fails here without anybody remembering to update this file.

SCOPE of the frozen claim: the value graph reachable from a `LexedUnit` --
`tokens` (tuple) -> `Token` (frozen) -> `parts` (tuple) -> `TokenPart` (frozen)
-> `Position` (frozen), plus `heredocs` (read-only mapping) and the
`HeredocSpec`/`CollectedHeredoc` values inside it. Construction-time list
building is NOT in scope and stays legal: `Token.__post_init__` coerces `parts`
to a tuple, so a scanner may accumulate a list and hand it over.
"""
import dataclasses

import pytest

from psh.lexer.heredoc_lexer import HeredocLexer
from psh.lexer.position import Position
from psh.lexer.token_parts import TokenPart
from psh.lexer.token_types import Token, TokenType

# A source exercising every part-bearing shape: quoted composites, an expansion
# part, a variable part, and a heredoc (so `heredocs` is populated too).
_SOURCE = 'echo "a$b"c $(x) ${y:-d} <<E\nbody\nE\n'

_MUTABLE_CONTAINERS = (list, dict, set, bytearray)


@pytest.fixture(scope="module")
def unit():
    return HeredocLexer(_SOURCE, warn_unterminated=False).tokenize_with_heredocs()


@pytest.fixture(scope="module")
def part(unit):
    for token in unit.tokens:
        if token.parts:
            return token.parts[0]
    pytest.fail("no part-bearing token in the corpus -- the fixture is stale")


def _walk(root):
    """Every object reachable from *root*, with the path that reached it.

    Yields ``(path, obj)``. Descends dataclass fields, tuples/lists/sets,
    mapping values and NamedTuple fields -- the shapes a lexical value graph is
    built from. Atoms are yielded but not descended into.
    """
    seen, stack = set(), [("LexedUnit", root)]
    while stack:
        path, obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        yield path, obj
        if isinstance(obj, (str, bytes, int, float, bool, type(None))):
            continue
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            for f in dataclasses.fields(obj):
                stack.append((f"{path}.{f.name}", getattr(obj, f.name)))
        elif hasattr(obj, "_fields"):                       # NamedTuple
            for name in obj._fields:
                stack.append((f"{path}.{name}", getattr(obj, name)))
        elif isinstance(obj, (tuple, list, set, frozenset)):
            for i, item in enumerate(obj):
                stack.append((f"{path}[{i}]", item))
        elif hasattr(obj, "items"):
            for k, v in obj.items():
                stack.append((f"{path}[{k!r}]", v))


# === THE transitive census: the guard whose universe is the whole graph ===

def test_no_unfrozen_dataclass_is_reachable_from_a_lexed_unit(unit):
    """Walks the LIVE graph. This is the row that would have caught Position."""
    offenders = [
        (path, type(obj).__name__)
        for path, obj in _walk(unit)
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type)
        and not obj.__dataclass_params__.frozen
    ]
    assert not offenders, (
        "unfrozen dataclass reachable from a LexedUnit -- the value graph is "
        f"writable at these paths: {offenders}")


def test_no_mutable_container_is_reachable_from_a_lexed_unit(unit):
    """The other half: a frozen node reached THROUGH a mutable container is
    still rewritable (`Token.parts` was a list under a frozen Token)."""
    offenders = [
        (path, type(obj).__name__)
        for path, obj in _walk(unit)
        if isinstance(obj, _MUTABLE_CONTAINERS)
    ]
    assert not offenders, (
        f"mutable container reachable from a LexedUnit: {offenders}")


def test_the_census_actually_reaches_the_interesting_nodes(unit):
    """A guard on the guard: if the walk stopped early, the two tests above
    would pass vacuously. Assert the graph really was traversed to its leaves."""
    kinds = {type(obj).__name__ for _, obj in _walk(unit)}
    for expected in ("Token", "TokenPart", "Position", "LexedHeredoc",
                     "HeredocSpec", "CollectedHeredoc"):
        assert expected in kinds, (expected, sorted(kinds))


# === Per-field/edge rows (kept: they name the specific regressions) ===

def test_the_value_types_are_frozen():
    for cls in (Token, TokenPart, Position):
        assert cls.__dataclass_params__.frozen, cls


@pytest.mark.parametrize(
    "field_name",
    [f.name for f in dataclasses.fields(TokenPart)],
    ids=[f.name for f in dataclasses.fields(TokenPart)],
)
def test_every_tokenpart_field_rejects_a_write(part, field_name):
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(part, field_name, getattr(part, field_name))


@pytest.mark.parametrize(
    "field_name",
    [f.name for f in dataclasses.fields(Position)],
    ids=[f.name for f in dataclasses.fields(Position)],
)
def test_every_position_field_rejects_a_write(part, field_name):
    """The round-1 blocker, pinned directly: `part.start_pos.offset = 999`."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(part.start_pos, field_name, getattr(part.start_pos, field_name))


def test_token_parts_is_a_tuple_on_a_real_lexed_value(unit):
    for token in unit.tokens:
        assert isinstance(token.parts, tuple), token


def test_parts_list_handed_to_the_constructor_is_frozen_on_store():
    """Construction may pass a list; what is STORED is a tuple, and mutating
    the caller's original list cannot reach into the token."""
    caller_list = [TokenPart(value="a"), TokenPart(value="b")]
    token = Token(type=TokenType.WORD, value="ab", position=0,
                  parts=caller_list)
    assert isinstance(token.parts, tuple)
    caller_list.append(TokenPart(value="c"))
    assert len(token.parts) == 2


def test_rebinding_a_frozen_token_field_is_rejected(unit):
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(unit.tokens[0], "parts", ())


# (name, how to reach the real container, the mutation, a MUTABLE control)
# The control is the answer to round-1 nit 3: accepting a broad raises-set lets
# a typo'd attribute name pass as "rejected". Rather than narrowing the set --
# tuples legitimately raise AttributeError for `.append`, so narrowing breaks
# honest rows -- each mutation is proven WELL-FORMED by running it against a
# mutable stand-in of the same kind, where it MUST succeed. A typo therefore
# fails the control row instead of silently passing the frozen row.
_EDGES = [
    ("Token.parts.append", lambda u: u.tokens[0].parts,
     lambda c: c.append("X"), lambda: ["a"]),
    ("Token.parts[0]=", lambda u: u.tokens[0].parts,
     lambda c: c.__setitem__(0, "X"), lambda: ["a"]),
    ("Token.parts.clear", lambda u: u.tokens[0].parts,
     lambda c: c.clear(), lambda: ["a"]),
    ("LexedUnit.tokens[0]=", lambda u: u.tokens,
     lambda c: c.__setitem__(0, "X"), lambda: ["a"]),
    ("LexedUnit.heredocs[0]=", lambda u: u.heredocs,
     lambda c: c.__setitem__(0, None), lambda: {0: "a"}),
]


@pytest.mark.parametrize("edge,reach,mutate,control", _EDGES,
                         ids=[e[0] for e in _EDGES])
def test_every_container_edge_rejects_a_write(unit, edge, reach, mutate,
                                              control):
    mutate(control())          # POSITIVE CONTROL: the mutation is well-formed.
    with pytest.raises((dataclasses.FrozenInstanceError, TypeError,
                        AttributeError)):
        mutate(reach(unit))


def test_the_base_probe_rewrites_are_now_impossible(unit):
    """Both base-SHA probe rewrites -- the original parts mutation and the
    round-1 nested-Position mutation -- asserted dead."""
    token = next(t for t in unit.tokens if t.parts)
    before = [(p.value, p.quote_type, p.start_pos.offset) for p in token.parts]
    with pytest.raises(dataclasses.FrozenInstanceError):
        token.parts[0].value = "PWNED"
    with pytest.raises(dataclasses.FrozenInstanceError):
        token.parts[0].start_pos.offset = 999
    assert [(p.value, p.quote_type, p.start_pos.offset)
            for p in token.parts] == before
