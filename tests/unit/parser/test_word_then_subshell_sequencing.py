"""A simple command immediately followed by `(subshell)` needs a separator.

bash requires a separator (`;`, newline, `&`, `|`, `&&`, `||`) between a
command and a following compound command; `echo (x)` is a syntax error. The
recursive-descent parser matches bash and reports a ParseError.

This behavior is exercised by the parser-hardening array-initializer fix
(appraisal finding 5b): once `a= (x)` / `arr += (one two)` are no longer
treated as array initializers (a non-adjacent `(` is not an init, matching
bash), the trailing `(...)` becomes exactly this word-then-`(subshell)` case.

KNOWN COMBINATOR GAP: the combinator parser accepts `echo (x)` as TWO
statements because its statement-list loop does not require a separator — a
pre-existing sequencing gap tracked in
docs/guides/combinator_parser_remaining_failures.md and deliberately NOT
fixed in this campaign. These tests pin the rd (production) parser only.
"""

import pytest

from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.recursive_descent.helpers import ParseError


@pytest.mark.parametrize("src", [
    "echo (x)",
    "foo (bar)",
    "a= (x)",            # not an array init (non-adjacent '(') -> then this
    "a = (x)",
    "arr += (one two)",
])
def test_word_then_subshell_without_separator_is_parse_error(src):
    with pytest.raises(ParseError):
        Parser(tokenize(src)).parse()


@pytest.mark.parametrize("src", [
    "echo; (x)",         # separator present -> two statements, fine
    "echo && (x)",
    "echo | (x)",
    "(x)",               # bare subshell
])
def test_subshell_with_separator_or_bare_is_accepted(src):
    # Should parse without raising (a separator, operator, or a bare subshell).
    Parser(tokenize(src)).parse()
