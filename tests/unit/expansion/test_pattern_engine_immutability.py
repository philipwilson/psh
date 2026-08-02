"""Immutability pins for the compiled pattern representation (#20 MEDIUM-6).

Compiles are CACHED — ``pattern_engine.compile_cached`` (lru 4096) and
``parameter_expansion._sub_machinery_cached`` (lru 512) above it — so one
compile's result is handed to every later caller with the same key. While the
nodes were mutable, a caller that wrote to one POISONED every subsequent cache
hit. Each test below is the green arm of a poisoning that REPRODUCED on the
pre-freeze engine; the red-arm transcripts are recorded in the slot ledger.

THREAT MODEL (ruled): these pins prove the freeze stops HONEST-CALLER
ACCIDENT, not adversarial bypass. A normal attribute write raises
``FrozenInstanceError``; ``object.__setattr__`` and module-attribute rebinding
remain possible and are deliberately OUT OF SCOPE, because Python freezing is
leaky by construction and pinning "no adversarial bypass" would pin a
falsehood. The behavioural criterion actually pinned is the one that matters
to a caller: you cannot mutate the result of one compile and change a later
match.

The final test states that criterion end-to-end through a real ``Shell``, with
no engine API in the caller's hands — the form the defect was observed in.
"""
import dataclasses

import pytest

from psh.expansion import parameter_expansion as px
from psh.expansion import pattern_engine as pe
from psh.expansion.pattern_engine import (
    STRING,
    AnyChar,
    Bracket,
    CompiledPattern,
    Extglob,
    Literal,
    PatternCompiler,
    Sequence,
    Star,
)

NODE_TYPES = (Literal, AnyChar, Star, Bracket, Extglob, Sequence)


@pytest.fixture(autouse=True)
def _clear_pattern_caches():
    """Each test owns the cache state it observes (these pins are ABOUT the
    caches, so leaking entries between them would hide exactly the coupling
    under test)."""
    pe.compile_cached.cache_clear()
    px._sub_machinery_cached.cache_clear()
    yield
    pe.compile_cached.cache_clear()
    px._sub_machinery_cached.cache_clear()


def test_every_node_type_is_frozen_and_identity_keyed():
    """Frozen for the cache; ``eq=False`` because the matcher memoizes on
    ``id(node)`` — losing identity semantics would silently merge states."""
    for cls in NODE_TYPES + (CompiledPattern,):
        params = cls.__dataclass_params__
        assert params.frozen is True, f"{cls.__name__} is not frozen"
        assert params.eq is False, (
            f"{cls.__name__} has eq=True — identity semantics lost")
    # Identity hashing still works — the matcher's memo key depends on it.
    # (The original form of this assertion was
    #     assert a != b and hash(a) != hash(b) or a is not b
    # which precedence-groups as ``(X and Y) or (a is not b)``. The final
    # disjunct is always true for two distinct objects, so the line was
    # VACUOUS: it would have passed even if the nodes had gained value
    # equality and started colliding in the memo.)
    a, b = Literal('x'), Literal('x')
    assert a is not b
    assert a != b, "value equality would merge distinct nodes in the memo"
    assert hash(a) != hash(b), "identity hash lost"
    assert len({a, b}) == 2


# --- the seven poisoning demos, as raise-assertions -------------------------

def test_literal_char_write_raises_and_cache_stays_clean():
    """Demo 1: mutating a Literal poisoned a later independent compile."""
    compiled = PatternCompiler.compile('abc')
    with pytest.raises(dataclasses.FrozenInstanceError):
        compiled.root.elements[0].char = 'z'
    assert PatternCompiler.compile('abc').full_match('abc', STRING) is True
    assert PatternCompiler.compile('abc').full_match('zbc', STRING) is False


def test_bracket_content_write_raises():
    compiled = PatternCompiler.compile('[abc]')
    bracket = compiled.root.elements[0]
    assert isinstance(bracket, Bracket)
    with pytest.raises(dataclasses.FrozenInstanceError):
        bracket.content = 'xyz'
    assert PatternCompiler.compile('[abc]').full_match('a', STRING) is True


def test_bash_quirk_bit_write_raises():
    """Demo 2: flipping the routing bit sent the pattern to the WRONG matcher
    (the measured bash-composition route vs the reachability DP)."""
    compiled = PatternCompiler.compile('*!(a)')
    assert compiled.root.bash_quirk is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        compiled.root.bash_quirk = False
    assert PatternCompiler.compile('*!(a)').full_match('a', STRING) is False


def test_extglob_enclosed_stamp_write_raises():
    """Demo 3: the parser's ``enclosed`` stamp decides bash's end-of-string
    negation rule; flipping it changed the answer on an empty remainder."""
    compiled = PatternCompiler.compile('*!(a)')
    group = next(e for e in compiled.root.elements if isinstance(e, Extglob))
    with pytest.raises(dataclasses.FrozenInstanceError):
        group.enclosed = True
    assert PatternCompiler.compile('*!(a)').full_match('', STRING) is True


def test_sequence_elements_rebind_raises():
    """Demo 4: the tuple is immutable, but the SLOT holding it was not."""
    compiled = PatternCompiler.compile('xy')
    with pytest.raises(dataclasses.FrozenInstanceError):
        compiled.root.elements = (Literal('q'),)
    assert PatternCompiler.compile('xy').full_match('xy', STRING) is True


def test_sub_fast_bit_write_raises():
    """Demo 5: flipping ``sub_fast`` changed the substitution DISPATCH
    (linear Path A vs the per-suffix bash machinery)."""
    compiled = PatternCompiler.compile('+([[:space:]])')
    assert compiled.root.sub_fast is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        compiled.root.sub_fast = False
    _c, _w, _e, fast_ok = px._sub_machinery_cached('+([[:space:]])', 'any', True)
    assert fast_ok is True


def test_compiled_pattern_root_rebind_raises():
    """Demo 7: ``_sub_machinery_cached`` hands out the SAME CompiledPattern
    objects, so a rebound ``root`` poisoned every later consumer."""
    first = px._sub_machinery_cached('a*', 'any', True)
    second = px._sub_machinery_cached('a*', 'any', True)
    assert first[0] is second[0] and first[1] is second[1]
    with pytest.raises(dataclasses.FrozenInstanceError):
        first[0].root = PatternCompiler.compile('zzz').root


def test_new_attributes_cannot_be_attached():
    """``slots=True``: a typo'd attribute name is an error, not a silent
    write that a later reader might pick up."""
    compiled = PatternCompiler.compile('abc')
    with pytest.raises((AttributeError, TypeError)):
        compiled.root.bash_qurik = True          # codespell:ignore


def test_poisoning_is_impossible_through_a_real_shell():
    """Demo 6, the criterion that matters: with no engine API in the caller's
    hands, a compiled pattern reached through ordinary shell execution cannot
    be mutated into changing a later identical command.

    Pre-freeze this sequence returned 'HIT' and then 'abc' — the same command,
    a different answer, because the cached node had been rewritten.
    """
    from psh.shell import Shell

    shell = Shell()
    shell.run_command('v=abc; r=${v//abc/HIT}')
    assert shell.state.get_variable('r') == 'HIT'

    node = pe.compile_cached('abc', True).elements[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        node.char = 'z'

    shell.run_command('v=abc; r=${v//abc/HIT}')
    assert shell.state.get_variable('r') == 'HIT'


def test_routing_bits_are_derived_at_construction_not_lazily():
    """The bits are present the moment the node exists — there is no
    first-query write, which is what made freezing possible at all."""
    root = pe.compile_pattern('**(a)b')
    for bit in ('has_extglob', 'bash_quirk', 'sub_fast', 'nullable'):
        value = getattr(root, bit)
        assert isinstance(value, bool), f"{bit} is {value!r}, not a bool"
    assert root.bash_quirk is True
    assert root.has_extglob is True
    # and they are not constructor parameters, so no caller can supply a lie
    init_fields = [f.name for f in dataclasses.fields(Sequence) if f.init]
    assert init_fields == ['elements']


def test_deeply_nested_ast_constructs_without_recursion():
    """Deriving the bits at construction must not recurse: a child's bits are
    read in O(1), so an iteratively-built deep AST is still constructible.
    (``test_pattern_relations.py`` depends on this to pin the MATCHER's
    recursion bound rather than the constructor's.)"""
    seq = Sequence((Literal('x'),))
    for _ in range(3000):
        seq = Sequence((Extglob('@', (seq,)),))
    assert seq.has_extglob is True
