"""Every combinator production carries its trailing redirects (C020).

The combinator parser used to leave a trailing redirect on ``(( ))`` and
``[[ ]]`` unconsumed. The statement-list loop then absorbed it as a SECOND
statement, silently dropping the redirection AND replacing the compound's
exit status with the redirect-only command's 0::

    python -m psh --parser combinator -c '(( 0 )) >/dev/null; echo $?'   # was 0

This module is the standing guard. For EVERY AST class that has a
``redirects`` field it parses a representative statement carrying a trailing
redirect through BOTH parsers' direct APIs and asserts the two ASTs are
equal, so the recursive descent parser (the reference implementation) pins
the combinator. A production that forgets to consume its redirects fails
here even if no behavioural test happens to cover its shape.

The class list is DERIVED from ``psh.ast_nodes`` at collection time, so a
new redirect-bearing node cannot join the AST without a matrix row.

Owner of the single helper under test:
``psh/parser/combinators/trailing_redirects.py``
(``TrailingRedirectMixin._parse_trailing_redirects``).
"""

import dataclasses
import inspect

import pytest

import psh.ast_nodes as ast_nodes
from psh.lexer import tokenize
from psh.parser import Parser as RecursiveDescentParser
from psh.parser.combinators.parser import ParserCombinatorShellParser


def _redirect_bearing_classes():
    """Every dataclass in psh.ast_nodes that declares a ``redirects`` field."""
    found = set()
    for name in dir(ast_nodes):
        obj = getattr(ast_nodes, name)
        if not (inspect.isclass(obj) and dataclasses.is_dataclass(obj)):
            continue
        if any(f.name == 'redirects' for f in dataclasses.fields(obj)):
            found.add(obj.__name__)
    return found


# One representative statement per redirect-bearing node, each with a trailing
# redirect. Keep in sync with the AST: the completeness test below fails if a
# node is added or removed.
REPRESENTATIVE_SOURCES = {
    'ArithmeticEvaluation': '(( 0 )) > /dev/null',
    'BraceGroup': '{ :; } > /dev/null',
    'CStyleForLoop': 'for ((i=0;i<1;i++)); do :; done > /dev/null',
    'CaseConditional': 'case x in x) :;; esac > /dev/null',
    'EnhancedTestStatement': '[[ a == b ]] > /dev/null',
    'ForLoop': 'for i in a; do :; done > /dev/null',
    'FunctionDef': 'f() { :; } > /dev/null',
    'IfConditional': 'if :; then :; fi > /dev/null',
    'SelectLoop': 'select x in a; do break; done > /dev/null',
    'SimpleCommand': 'echo hi > /dev/null',
    'SubshellGroup': '( : ) > /dev/null',
    'UntilLoop': 'until :; do :; done > /dev/null',
    'WhileLoop': 'while false; do :; done > /dev/null',
}

# Redirect operators the two parsers must agree on for the two productions
# this slot repaired. `{v}>` exercises the fd-variable form, `<<` the heredoc
# path (whose body is collected by the lexer, not the redirect parser).
REDIRECT_FORMS = ['> /dev/null', '>> out.txt', '< in.txt', '2>&1', '2> err.txt',
                  '{v}> fv.txt', '>| clob.txt', '<> rw.txt']

REPAIRED_HEADS = ['(( 0 ))', '[[ a == b ]]']


def _rd_ast(source):
    return RecursiveDescentParser(tokenize(source)).parse()


def _combinator_ast(source):
    """Parse through the combinator's direct API (D6), not the --parser flag."""
    return ParserCombinatorShellParser().parse(tokenize(source))


def test_matrix_covers_every_redirect_bearing_node():
    """A new node with a ``redirects`` field must gain a matrix row."""
    assert _redirect_bearing_classes() == set(REPRESENTATIVE_SOURCES)


@pytest.mark.parametrize('node_name', sorted(REPRESENTATIVE_SOURCES))
def test_rd_and_combinator_agree_on_trailing_redirects(node_name):
    """RD and combinator build the SAME AST for a node with a trailing redirect."""
    source = REPRESENTATIVE_SOURCES[node_name]
    rd = _rd_ast(source)
    combinator = _combinator_ast(source)
    assert combinator == rd, (
        f"{node_name}: combinator AST differs from the recursive descent "
        f"reference for {source!r}"
    )


@pytest.mark.parametrize('node_name', sorted(REPRESENTATIVE_SOURCES))
def test_redirect_lands_on_the_node_not_a_second_statement(node_name):
    """The redirect is a field of ONE statement, never a statement of its own.

    AST equality alone would not catch a parser that split the redirect off
    AND made the RD parser split it too, so assert the shape directly: one
    top-level statement, and the redirect count over the whole tree is 1.
    """
    program = _combinator_ast(REPRESENTATIVE_SOURCES[node_name])
    assert len(program.statements) == 1, (
        f"{node_name}: trailing redirect was split into a second statement"
    )
    assert _count_redirects(program) == 1


def _count_redirects(node, total=0):
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        if any(f.name == 'redirects' for f in dataclasses.fields(node)):
            total += len(node.redirects)
        for field in dataclasses.fields(node):
            total = _count_redirects(getattr(node, field.name), total)
    elif isinstance(node, (list, tuple)):
        for item in node:
            total = _count_redirects(item, total)
    return total


@pytest.mark.parametrize('head', REPAIRED_HEADS)
@pytest.mark.parametrize('form', REDIRECT_FORMS)
def test_repaired_heads_agree_for_every_redirect_form(head, form):
    """`(( ))` / `[[ ]]` match RD for each redirect operator, not just `>`."""
    source = f'{head} {form}'
    assert _combinator_ast(source) == _rd_ast(source)


@pytest.mark.parametrize('head', REPAIRED_HEADS)
def test_repaired_heads_take_several_redirects(head):
    """A redirection LIST (not just one redirect) is consumed."""
    source = f'{head} >o1.txt 2>o2.txt'
    program = _combinator_ast(source)
    assert len(program.statements) == 1
    assert _count_redirects(program) == 2
    assert program == _rd_ast(source)


@pytest.mark.parametrize('head', REPAIRED_HEADS)
def test_trailing_ampersand_is_not_consumed_as_a_redirect(head):
    """`&` backgrounds the whole and-or list, so the helper must leave it.

    Guards the other direction of the fix: over-consuming after `))`/`]]`.
    """
    source = f'{head} >/dev/null &'
    program = _combinator_ast(source)
    assert len(program.statements) == 1
    assert program.statements[0].background is True
    assert program == _rd_ast(source)
