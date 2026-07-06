"""Array-assignment recognition requires lexical adjacency (findings 5b, 5c).

bash treats `(` as an array initializer only when it is glued to the
assignment head, and only consumes an element value that is adjacent to `=`:

- `a=(x)` / `a+=(x)` are inits; `a= (x)`, `a =(x)`, `a = (x)`, `a += (x)`
  (any whitespace gap) are NOT — bash reports a syntax error (finding 5b).
- `a[0]=v` assigns v; in `a[0]= v` the non-adjacent `v` is NOT the element
  value — psh parses an empty `a[0]=` assignment with `v` as a following
  word (bash treats `a[0]=` as a command prefix and rejects it as an
  invalid identifier; that residual divergence is pre-existing and out of
  scope here — the adjacency fix only stops swallowing `v` into the value);
  `a[0] =v` is the command `a[0]` with argument `=v`, not an element
  assignment (finding 5c).

Both parsers must agree on whether the head is an array assignment. (The
downstream handling of a rejected spaced-init — rd raises a syntax error while
the combinator hits a pre-existing word-then-`(subshell)` sequencing gap — is
covered separately in test_word_then_subshell_sequencing.py.)
"""

import pytest

from psh.ast_nodes import ArrayElementAssignment, ArrayInitialization
from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.combinators.arrays import ArrayParsers
from psh.parser.recursive_descent.helpers import ParseError


def _rd_array_assignments(src):
    """Return the first command's array_assignments (or None on parse error)."""
    try:
        prog = Parser(tokenize(src)).parse()
    except ParseError:
        return None
    cmd = prog.statements[0].pipelines[0].commands[0]
    return getattr(cmd, "array_assignments", [])


def _comb_is_array_head(src):
    """True if the combinator classifies position 0 as an array head."""
    toks = tokenize(src)
    return (ArrayParsers.is_initializer_head(toks, 0)
            or ArrayParsers.is_element_head(toks, 0))


# --- Initializer adjacency (5b) ---

def test_adjacent_init_is_array():
    arrs = _rd_array_assignments("a=(x y)")
    assert len(arrs) == 1 and isinstance(arrs[0], ArrayInitialization)


def test_adjacent_append_init_is_array():
    arrs = _rd_array_assignments("a+=(x)")
    assert len(arrs) == 1 and isinstance(arrs[0], ArrayInitialization)


@pytest.mark.parametrize("src", ["a= (x)", "a =(x)", "a = (x)", "a += (x)"])
def test_spaced_init_is_not_array(src):
    # rd: not an initializer -> not parsed as an ArrayInitialization prefix
    # (in these cases rd goes on to report a syntax error at `(`).
    assert _rd_array_assignments(src) in (None, [])
    # combinator: must also NOT classify it as an array head (parity of the
    # array-init DECISION, independent of the downstream sequencing gap).
    assert _comb_is_array_head(src) is False


# --- Element value adjacency (5c) ---

def test_adjacent_element_value():
    arrs = _rd_array_assignments("a[0]=v")
    assert len(arrs) == 1
    el = arrs[0]
    assert isinstance(el, ArrayElementAssignment)
    assert el.value == "v"


def test_empty_element_value_does_not_swallow_next_word():
    # `a[0]= v` -> a[0] empty; `v` is a SEPARATE command, not the value.
    arrs = _rd_array_assignments("a[0]= v")
    assert len(arrs) == 1
    el = arrs[0]
    assert isinstance(el, ArrayElementAssignment)
    assert el.value == ""
    # The command word `v` survives as the simple command.
    prog = Parser(tokenize("a[0]= v")).parse()
    cmd = prog.statements[0].pipelines[0].commands[0]
    assert [w.display_text() for w in cmd.words] == ["v"]


@pytest.mark.parametrize("src", ["a[0] =v", "a[0] = v"])
def test_spaced_element_head_is_not_assignment(src):
    # `a[0] =v` -> `a[0]` is a command word, `=v` an argument; no element assign.
    arrs = _rd_array_assignments(src)
    assert arrs == []
    assert _comb_is_array_head(src) is False
