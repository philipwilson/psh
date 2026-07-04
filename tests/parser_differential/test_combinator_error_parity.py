"""Recursive-descent vs combinator parse-error parity.

This gate is intentionally coarser than diagnostic parity.  It checks that
both parsers reject the same invalid syntax; message and location parity can
be tightened later once accept/reject behavior is stable.
"""

import pytest

from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.combinators.parser import ParserCombinatorShellParser

REJECTION_CORPUS = [
    pytest.param('()', id='empty-subshell'),
    pytest.param('( )', id='empty-subshell-spaced'),
    pytest.param('{ }', id='empty-brace-group'),
    pytest.param('(', id='unterminated-subshell'),
    pytest.param('{ echo hi', id='unterminated-brace-group'),
    pytest.param('if true; then echo yes', id='unterminated-if'),
    pytest.param('if true echo yes; fi', id='if-missing-then'),
    pytest.param('if true; then; fi', id='if-empty-then'),
    pytest.param('if true; then if true; then echo x; fi',
                 id='nested-if-missing-fi'),
    pytest.param('if true; then if true echo x; fi; fi',
                 id='nested-if-missing-then'),
    pytest.param('if true; then while true; do echo x; fi',
                 id='if-body-while-missing-done'),
    pytest.param('while true; do echo x', id='unterminated-while'),
    pytest.param('while true; do while true; do echo x; done',
                 id='nested-while-missing-done'),
    pytest.param('while true; do if true; then echo x; done',
                 id='while-body-if-missing-fi'),
    pytest.param('while true; do; done', id='while-empty-body'),
    pytest.param('until true; do; done', id='until-empty-body'),
    # No-separator empty bodies (`do done`, not `do; done`): the form that
    # actually hung the RD parser (appraisal H1) until v0.516. Both parsers
    # must reject; an empty `do` body would be an infinite loop.
    pytest.param('while true; do done', id='while-empty-body-no-sep'),
    pytest.param('until true; do done', id='until-empty-body-no-sep'),
    pytest.param('if true; then fi', id='if-empty-then-no-sep'),
    pytest.param('select x in a; do done', id='select-empty-body-no-sep'),
    pytest.param('for ((i=0; i<1; i++)); do done',
                 id='cstyle-for-empty-body-no-sep'),
    pytest.param('if true; then echo y; elif true; then fi',
                 id='if-empty-elif-body'),
    pytest.param('for x in a b; do echo $x', id='unterminated-for'),
    pytest.param('for x in a; do; done', id='for-empty-body'),
    pytest.param('for x in a; do done', id='for-empty-body-no-sep'),
    pytest.param('case x in a) echo a', id='unterminated-case'),
    pytest.param('case x in ; esac', id='case-empty-pattern-list'),
    pytest.param('case x in a) case y in b) echo b ;; esac',
                 id='nested-case-missing-esac'),
    pytest.param('case a b in x) echo x ;; esac', id='bad-case-subject'),
    pytest.param('echo >', id='redirect-missing-target-out'),
    pytest.param('cat <', id='redirect-missing-target-in'),
    pytest.param('echo 2>&', id='redirect-missing-dup-target'),
    pytest.param('cat <<', id='heredoc-missing-delimiter'),
    pytest.param('cat <<<', id='herestring-missing-content'),
    pytest.param('a=(1 2', id='unterminated-array-init'),
    pytest.param('f() { echo hi', id='unterminated-function-posix'),
    pytest.param('function f {', id='unterminated-function-keyword'),
    pytest.param('function { echo hi; }', id='function-missing-name'),
    pytest.param('f() { if true; then echo x; }',
                 id='function-body-if-missing-fi'),
    pytest.param('f() { while true; do echo x; }',
                 id='function-body-while-missing-done'),
    pytest.param('[[ -n $x', id='unterminated-enhanced-test'),
    pytest.param('[[ $x == ]]', id='enhanced-test-missing-rhs'),
    pytest.param('for ((i=0; i<3; i++); do echo $i; done',
                 id='bad-cstyle-for-close'),
    pytest.param('for ((i=0; i<1; i++)); do; done',
                 id='cstyle-for-empty-body'),
    # A C-style for header needs exactly two semicolons (reappraisal #18 T1-5).
    # A one-semicolon header would otherwise parse with an empty update and
    # loop forever; bash rejects it. The paren variant guards the interaction
    # with the fixed collector (which now stops the condition at `))`).
    pytest.param('for ((i=0; i<3)); do echo x; done',
                 id='cstyle-for-one-semicolon'),
    pytest.param('for ((i=0; i<(3))); do echo x; done',
                 id='cstyle-for-one-semicolon-paren'),
    pytest.param('echo |', id='pipeline-missing-command'),
    pytest.param('echo &&', id='and-if-missing-rhs'),
    pytest.param('&& echo', id='and-if-missing-lhs'),
    pytest.param('echo ; && echo', id='and-if-after-separator'),
    pytest.param('echo ; | cat', id='pipe-after-separator'),
    pytest.param('echo | ;', id='pipe-before-separator'),
    pytest.param('echo && ;', id='and-if-before-separator'),
    pytest.param('if true; then echo x; fi >',
                 id='if-trailing-redirect-missing-target'),
    pytest.param('{ echo x; } <',
                 id='brace-trailing-redirect-missing-target'),
    pytest.param('while true; do echo x; done 2>',
                 id='while-trailing-redirect-missing-target'),
    pytest.param('( echo x ) >',
                 id='subshell-trailing-redirect-missing-target'),
]


def _parse_accepts_recursive_descent(source):
    try:
        Parser(tokenize(source), source_text=source).parse()
    except Exception:
        return False
    return True


def _parse_accepts_combinator(source):
    try:
        ParserCombinatorShellParser().parse(tokenize(source))
    except Exception:
        return False
    return True


# Valid constructs that both parsers must ACCEPT.  These guard against
# over-eager rejection when tightening the empty-body/empty-item diagnostics
# above: an empty `case` (no patterns) and zero-iteration loops are legal bash,
# distinct from the empty-*body* forms (`while true; do; done`) bash rejects.
ACCEPTANCE_CORPUS = [
    pytest.param('case x in esac', id='empty-case-bare'),
    pytest.param('case x in\n\nesac', id='empty-case-blank-lines'),
    pytest.param('case x in\n# c\nesac', id='empty-case-comment-only'),
    pytest.param('case x in esac; echo after', id='empty-case-trailing-command'),
    pytest.param('case x in a) echo a;; esac', id='normal-case'),
    pytest.param('for x in; do echo hi; done', id='for-empty-word-list'),
    pytest.param('if true; then :; fi', id='if-noop-body'),
    pytest.param('while false; do :; done', id='while-noop-body'),
    # Two-semicolon boundary: an empty *update* section is legal (distinct from
    # the one-semicolon header rejected above).
    pytest.param('for ((i=0; i<3;)); do echo x; done',
                 id='cstyle-for-empty-update'),
]


@pytest.mark.parametrize('source', REJECTION_CORPUS)
def test_combinator_rejects_recursive_descent_rejections(source):
    assert _parse_accepts_recursive_descent(source) is False
    assert _parse_accepts_combinator(source) is False


@pytest.mark.parametrize('source', ACCEPTANCE_CORPUS)
def test_combinator_accepts_recursive_descent_acceptances(source):
    assert _parse_accepts_recursive_descent(source) is True
    assert _parse_accepts_combinator(source) is True
