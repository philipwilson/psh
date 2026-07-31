"""The COMPLETE lexical value graph is frozen (remediation 2.5, #22 MEDIUM-10b).

`LexedUnit.tokens` was already a tuple and its heredoc map a read-only mapping,
but every frozen `Token` in it handed out a mutable `parts` LIST of mutable
`TokenPart` objects -- so a lexed value could be rewritten after the lexer had
returned it. A probe at base e36116c3 rewrote a real lexed `echo "a$b"c` from
`[('a','"'), ('b','"')]` to `[('PWNED',"'"), ('b','"'), ('PWNED',"'")]`.

WHY THE UNIVERSE IS COMPUTED, NOT LISTED: a guard that names the fields it
knows about proves nothing about the field somebody adds next year. These tests
enumerate `dataclasses.fields(TokenPart)` at runtime, so a NEW TokenPart field
is automatically in the guard's universe and a new mutable one fails here
without anybody remembering to update this file. The same applies to the
container edges: they are derived by walking a real LexedUnit.

SCOPE of the frozen claim: the value graph reachable from a `LexedUnit` --
`tokens` (tuple) -> `Token` (frozen) -> `parts` (tuple) -> `TokenPart` (frozen),
plus `heredocs` (read-only mapping). Construction-time list building is NOT in
scope and stays legal: `Token.__post_init__` coerces `parts` to a tuple, so a
scanner may build a list and hand it over.
"""
import dataclasses

import pytest

from psh.lexer.heredoc_lexer import HeredocLexer
from psh.lexer.token_parts import TokenPart
from psh.lexer.token_types import Token, TokenType

# A source exercising every part-bearing shape: quoted composites, an
# expansion part, a variable part, and a heredoc (so `heredocs` is populated).
_SOURCE = 'echo "a$b"c $(x) ${y:-d} <<E\nbody\nE\n'


@pytest.fixture(scope="module")
def unit():
    return HeredocLexer(_SOURCE, warn_unterminated=False).tokenize_with_heredocs()


@pytest.fixture(scope="module")
def part(unit):
    for token in unit.tokens:
        if token.parts:
            return token.parts[0]
    pytest.fail("no part-bearing token in the corpus — the fixture is stale")


def test_tokenpart_is_frozen():
    assert TokenPart.__dataclass_params__.frozen
    assert Token.__dataclass_params__.frozen


@pytest.mark.parametrize(
    "field_name",
    [f.name for f in dataclasses.fields(TokenPart)],
    ids=[f.name for f in dataclasses.fields(TokenPart)],
)
def test_every_tokenpart_field_rejects_a_write(part, field_name):
    """EVERY declared field, enumerated at runtime — add a field, get a row."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(part, field_name, getattr(part, field_name))


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


@pytest.mark.parametrize("edge,mutate", [
    ("Token.parts rebind", lambda u, p: setattr(u.tokens[0], "parts", ())),
    ("Token.parts.append", lambda u, p: u.tokens[0].parts.append(p)),
    ("Token.parts[0]=", lambda u, p: u.tokens[0].parts.__setitem__(0, p)),
    ("LexedUnit.tokens[0]=", lambda u, p: u.tokens.__setitem__(0, u.tokens[0])),
    ("LexedUnit.heredocs[0]=", lambda u, p: u.heredocs.__setitem__(0, None)),
])
def test_every_container_edge_rejects_a_write(unit, part, edge, mutate):
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError,
                        TypeError)):
        mutate(unit, part)


def test_the_base_probe_rewrite_is_now_impossible(unit):
    """The exact rewrite the base-SHA probe performed, asserted dead."""
    token = next(t for t in unit.tokens if t.parts)
    before = [(p.value, p.quote_type) for p in token.parts]
    with pytest.raises(dataclasses.FrozenInstanceError):
        token.parts[0].value = "PWNED"
    assert [(p.value, p.quote_type) for p in token.parts] == before
