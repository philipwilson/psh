"""Empty compound-command bodies/conditions are rejected at parse time.

bash rejects an empty loop/if body or condition as a SYNTAX error (exit 2),
not at runtime. Before v0.516 the recursive-descent parser silently accepted
them: ``while true; do done`` became an *infinite loop* (an empty ``do`` body
with a true condition), and ``if true; then fi`` / ``f() { }`` were silent
no-ops. The fix routes every required-body/condition position through
``StatementParser.parse_required_command_list_until`` (appraisal 2026-06-21,
finding H1). Every form here was probe-verified to be ``exit 2`` in bash.

These are pinned against the production recursive-descent parser. The
educational combinator parser still accepts a few of them (empty conditions,
empty ``else``, empty function body) — a documented gap, not a tracked defect
(see ``psh/parser/CLAUDE.md``); the both-reject subset is additionally pinned
in ``tests/parser_differential/test_combinator_error_parity.py``.
"""

import pytest

from psh.lexer import tokenize
from psh.parser import ParseError, Parser


def _rd_rejects(source: str) -> bool:
    try:
        Parser(tokenize(source), source_text=source).parse()
    except ParseError:
        return True
    return False


# (source, id) — each is bash "syntax error near unexpected token ..." (exit 2).
EMPTY_COMPOUND_REJECTIONS = [
    # Empty bodies — the no-separator `do done` forms that used to HANG.
    ('while true; do done', 'while-empty-body'),
    ('until false; do done', 'until-empty-body'),
    ('for i in 1 2; do done', 'for-empty-body'),
    ('for ((i=0; i<2; i++)); do done', 'cstyle-for-empty-body'),
    ('select x in a; do done', 'select-empty-body'),
    ('f() { }', 'function-empty-body'),
    # Empty then/elif/else bodies.
    ('if true; then fi', 'if-empty-then'),
    ('if true; then echo y; elif true; then fi', 'if-empty-elif'),
    ('if true; then echo y; else fi', 'if-empty-else'),
    # Empty conditions.
    ('while do echo x; done', 'while-empty-condition'),
    ('until do echo x; done', 'until-empty-condition'),
    ('if then echo x; fi', 'if-empty-condition'),
]


@pytest.mark.parametrize(
    'source', [pytest.param(s, id=i) for s, i in EMPTY_COMPOUND_REJECTIONS])
def test_empty_compound_body_is_parse_error(source):
    assert _rd_rejects(source), f"expected parse-time rejection: {source!r}"


# Valid forms that must still be ACCEPTED — the guard must not over-reject.
# An empty `case` and zero-iteration loops with a real body are legal bash.
EMPTY_COMPOUND_ACCEPTANCES = [
    ('while false; do :; done', 'while-noop-body'),
    ('if true; then :; fi', 'if-noop-body'),
    ('for i in; do echo hi; done', 'for-empty-word-list'),
    ('for i in 1 2; do echo $i; done', 'for-normal'),
    ('case x in esac', 'empty-case'),
    ('case x in x) ;; esac', 'empty-case-branch'),
    ('f() { :; }', 'function-noop-body'),
    ('if false; then echo a; elif true; then echo b; else echo c; fi',
     'if-elif-else-normal'),
]


@pytest.mark.parametrize(
    'source', [pytest.param(s, id=i) for s, i in EMPTY_COMPOUND_ACCEPTANCES])
def test_valid_compound_still_accepted(source):
    assert not _rd_rejects(source), f"should parse: {source!r}"
