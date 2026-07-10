"""Regression pins: parse-error diagnostics anchored at KEYWORD tokens.

Phase C (lexer R2) made ``KeywordNormalizer`` rebuild a WORD-promoted-to-keyword
token with ``dataclasses.replace`` so its ``line``/``column`` survive. A
regression that rebuilt it with a bare ``Token(type=, value=, position=)`` ctor
would DROP line/column — and the user-visible diagnostic for a parse error
anchored at that keyword token silently loses both the ``(line L, column C)``
clause and the source-line + caret block, while the whole test suite still
passes. (Verifier mutation arm (f), 2026-07-10: 8/51 error-battery cases changed
stderr, 0 tests failed.)

These pins assert the EXACT line/column clause and the EXACT source-line/caret
block for each of those 8 keyword-anchored errors, so that rebuild path is
covered. In-process via ``ErrorContext.format_error`` (the text the shell prints
to stderr after its ``psh: -c:N:`` prefix), matching test_error_context_format.
"""

import pytest

from psh.lexer import tokenize
from psh.parser.recursive_descent.helpers import ParseError
from psh.parser.recursive_descent.parser import Parser


def _error_message(src: str) -> str:
    p = Parser(tokenize(src), source_text=src)
    with pytest.raises(ParseError) as excinfo:
        p.parse()
    return excinfo.value.error_context.format_error()


# src -> (exact "(line L, column C)" clause, exact "<source line>\n<caret>" block).
# Both are dropped when a keyword token is rebuilt without line/column.
KEYWORD_ANCHORED = {
    "if then":       ("(line 1, column 4)", "if then\n   ^"),
    "do echo; done": ("(line 1, column 1)", "do echo; done\n^"),
    "then echo; fi": ("(line 1, column 1)", "then echo; fi\n^"),
    "fi":            ("(line 1, column 1)", "fi\n^"),
    "done":          ("(line 1, column 1)", "done\n^"),
    "esac":          ("(line 1, column 1)", "esac\n^"),
    "else echo":     ("(line 1, column 1)", "else echo\n^"),
    "elif x":        ("(line 1, column 1)", "elif x\n^"),
}


@pytest.mark.parametrize("src,line_col,caret", sorted(
    (s, lc, c) for s, (lc, c) in KEYWORD_ANCHORED.items()))
def test_keyword_anchored_error_keeps_linecol_and_caret(src, line_col, caret):
    msg = _error_message(src)
    # The line/column clause survives (keyword token kept its line/column).
    assert line_col in msg, f"missing {line_col!r} in:\n{msg}"
    # The source-line + caret block survives (needs the column).
    assert f"\n{caret}\n" in msg, f"missing caret block {caret!r} in:\n{msg}"
