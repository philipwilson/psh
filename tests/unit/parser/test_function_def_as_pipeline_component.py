"""Parser AST shapes for a function definition as a PipelineComponent (S5, #20 H9).

A STANDALONE definition keeps its historical bare top-level shape
(Program.statements[0] is a FunctionDef); a definition used as a pipeline member,
negation/time target, and-or element, or background wraps through the and-or
machinery. Verified for BOTH parser implementations (parity).
"""
import pytest

from psh.ast_nodes import AndOrList, FunctionDef, Pipeline, SimpleCommand
from psh.lexer import tokenize
from psh.parser import parse
from psh.parser.combinators.parser import ParserCombinatorShellParser


def rd(src):
    return parse(tokenize(src))


def comb(src):
    return ParserCombinatorShellParser().parse(tokenize(src))


PARSERS = [pytest.param(rd, id='rd'), pytest.param(comb, id='combinator')]


@pytest.mark.parametrize("p", PARSERS)
def test_standalone_def_stays_bare_function_def(p):
    """`f() { :; }` -> Program.statements[0] is a bare FunctionDef (unchanged shape)."""
    prog = p('f() { echo hi; }')
    assert len(prog.statements) == 1
    assert isinstance(prog.statements[0], FunctionDef)
    assert prog.statements[0].name == 'f'


@pytest.mark.parametrize("p", PARSERS)
def test_standalone_def_in_list_stays_bare(p):
    """`f() { :; }; g` -> two statements, the def still bare."""
    prog = p('f() { :; }; echo done')
    assert isinstance(prog.statements[0], FunctionDef)


@pytest.mark.parametrize("p", PARSERS)
def test_def_piped_wraps_into_pipeline(p):
    """`f() { :; } | cat` -> AndOrList -> Pipeline([FunctionDef, SimpleCommand])."""
    prog = p('f() { echo hi; } | cat')
    andor = prog.statements[0]
    assert isinstance(andor, AndOrList)
    pipe = andor.pipelines[0]
    assert isinstance(pipe, Pipeline)
    assert len(pipe.commands) == 2
    assert isinstance(pipe.commands[0], FunctionDef)
    assert isinstance(pipe.commands[1], SimpleCommand)


@pytest.mark.parametrize("p", PARSERS)
def test_two_defs_piped(p):
    """`f(){ } | g(){ }` -> a pipeline of two FunctionDefs."""
    pipe = p('f() { echo a; } | g() { echo b; }').statements[0].pipelines[0]
    assert [type(c).__name__ for c in pipe.commands] == ['FunctionDef', 'FunctionDef']


@pytest.mark.parametrize("p", PARSERS)
def test_negated_def_is_single_member_pipeline(p):
    """`! f() { :; }` -> a negated single-member pipeline (runs in current shell)."""
    pipe = p('! f() { :; }').statements[0].pipelines[0]
    assert pipe.negated is True
    assert len(pipe.commands) == 1
    assert isinstance(pipe.commands[0], FunctionDef)


@pytest.mark.parametrize("p", PARSERS)
def test_timed_def_is_timed_pipeline(p):
    """`time f() { :; }` -> a timed single-member pipeline."""
    pipe = p('time f() { :; }').statements[0].pipelines[0]
    assert pipe.timed is True
    assert isinstance(pipe.commands[0], FunctionDef)


@pytest.mark.parametrize("p", PARSERS)
def test_def_in_and_list(p):
    """`true && f() { :; }` -> and-or list with the def as the second pipeline."""
    andor = p('true && f() { :; }').statements[0]
    assert isinstance(andor, AndOrList)
    assert andor.operators == ['&&']
    assert isinstance(andor.pipelines[1].commands[0], FunctionDef)


@pytest.mark.parametrize("p", PARSERS)
def test_def_backgrounded(p):
    """`f() { :; } &` -> the def wraps and the whole (single) list is background."""
    andor = p('f() { :; } &').statements[0]
    assert isinstance(andor, AndOrList)
    assert isinstance(andor.pipelines[0].commands[0], FunctionDef)
    # Background routes to the list level (a FunctionDef is never itself bg).
    assert andor.background is True
    assert andor.pipelines[0].commands[0].background is False


@pytest.mark.parametrize("p", PARSERS)
def test_def_with_redirect_stays_standalone(p):
    """`f() { :; } > out` (no pipe) stays a bare FunctionDef carrying the redirect."""
    fd = p('f() { :; } > out.txt').statements[0]
    assert isinstance(fd, FunctionDef)
    assert fd.redirects and fd.redirects[0].target == 'out.txt'


# --- still-invalid neighbors of the new grammar (integrator fixup, verify nit 7) ---
# When defs became pipeline components, the diagnostics for these (still
# rejected) inputs moved from the operator-token report to the generic
# pipeline-head report ("Expected command", past the operator) — the same way
# base psh already reports this defect class for any other pipeline head, and
# closer to bash's second-token error position. Pinned so further drift shows.

_STILL_INVALID_NEIGHBORS = [
    ("double_pipe_gap", "f() { :; } | | g() { :; }"),
    ("trailing_andand", "f() { :; } &&"),
    ("double_pipeamp", "f() { :; } |& |& cat"),
]


@pytest.mark.parametrize(
    "label,src", _STILL_INVALID_NEIGHBORS,
    ids=[r[0] for r in _STILL_INVALID_NEIGHBORS])
@pytest.mark.parametrize("p", PARSERS)
def test_still_invalid_def_continuations_rejected(p, label, src):
    with pytest.raises(Exception) as exc:
        p(src)
    if p is rd:
        assert "Expected command" in str(exc.value)
