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

The walk runs over a CORPUS, not one line (see `_SOURCES`): runtime discovery
only ever covers the shapes the source in hand actually produces, so the
universe of the claim is the corpus times the walk, and the corpus is stated.

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

# THE CORPUS, and why it is a corpus rather than a line (round-7 nit 5). The
# walk discovers its universe at runtime, but only over the shapes the source it
# runs on actually PRODUCES -- so a one-line corpus makes "a new node type is
# covered automatically" true of that line and no more. These sources are chosen
# to span the PART-BEARING CLASS: composite quoting, every expansion form,
# ANSI-C and backslash escapes, array and associative assignment, process
# substitution, named-fd and multiple heredocs, here-strings, and nested quoting
# inside a compound command.
#
# UNIVERSE, stated rather than implied: this covers the graph the LEXER builds.
# `Token.array_init` is a parser-set field (the combinator stashes `name=(...)`
# there), so no lexed unit reaches it today; if it ever became lexer-set, the
# corpus would have to grow a case that produces it -- the walk alone would not
# notice, because it cannot visit an edge no source creates.
_SOURCES = (
    ("composites_and_heredoc", 'echo "a$b"c $(x) ${y:-d} <<E\nbody\nE\n'),
    ("arith_and_backticks", 'echo $((1<<2)) `date` ${#x} ${y//a/b}\n'),
    ("ansi_c_and_escapes", "echo $'a\\tb' \\$literal 'sq' \"dq$v\"\n"),
    ("arrays_and_assoc", 'a=(1 "two" $three); declare -A m; m[k$i]=v\n'),
    ("process_substitution", 'diff <(echo a) >(cat) 2>&1\n'),
    ("named_fd_and_herestring", 'cat {v}<<E\nbody\nE\ncat <<<"a $b"\n'),
    ("two_heredocs_one_command", 'cat <<A <<B\n1\nA\n2\nB\n'),
    ("case_and_nested_quotes", 'case "$x" in a|b) echo "y${z:-d}";; esac\n'),
)

_MUTABLE_CONTAINERS = (list, dict, set, bytearray)


@pytest.fixture(scope="module", params=[s[1] for s in _SOURCES],
                ids=[s[0] for s in _SOURCES])
def unit(request):
    """ONE source per parametrization -- the freeze rows run against each."""
    return HeredocLexer(request.param,
                        warn_unterminated=False).tokenize_with_heredocs()


@pytest.fixture(scope="module")
def units():
    """ALL sources. Rows about the corpus's REACH aggregate over it: no single
    source produces every node type (a heredoc-free line has no CollectedHeredoc
    and a bare `cat <<A <<B` has no part-bearing token), so asserting per-source
    coverage would only force the corpus back down to one all-in-one line --
    the exact narrowness this widening exists to remove."""
    return [HeredocLexer(src, warn_unterminated=False).tokenize_with_heredocs()
            for _label, src in _SOURCES]


@pytest.fixture(scope="module")
def part(units):
    for unit in units:
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


def test_the_census_actually_reaches_the_interesting_nodes(units):
    """A guard on the guard: if the walk stopped early, the two rows above
    would pass vacuously. Assert the graph really was traversed to its leaves.

    Aggregated over the corpus -- see the `units` fixture for why per-source
    would be the wrong assertion."""
    kinds = {type(obj).__name__ for unit in units for _, obj in _walk(unit)}
    for expected in ("Token", "TokenPart", "Position", "LexedHeredoc",
                     "HeredocSpec", "CollectedHeredoc"):
        assert expected in kinds, (expected, sorted(kinds))


def test_every_source_in_the_corpus_lexes_to_something(units):
    """Non-vacuity for the WIDENING itself: a source that silently lexed to
    nothing would add a green freeze row that walked an empty graph."""
    for (label, _src), unit in zip(_SOURCES, units, strict=True):
        assert unit.tokens, label
        assert len(list(_walk(unit))) > 5, label


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


def test_the_base_probe_rewrites_are_now_impossible(units):
    """Both base-SHA probe rewrites -- the original parts mutation and the
    round-1 nested-Position mutation -- asserted dead."""
    token = next(t for unit in units for t in unit.tokens if t.parts)
    before = [(p.value, p.quote_type, p.start_pos.offset) for p in token.parts]
    with pytest.raises(dataclasses.FrozenInstanceError):
        token.parts[0].value = "PWNED"
    with pytest.raises(dataclasses.FrozenInstanceError):
        token.parts[0].start_pos.offset = 999
    assert [(p.value, p.quote_type, p.start_pos.offset)
            for p in token.parts] == before
