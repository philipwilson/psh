"""R18 Tier-2 T2-C — lexer/parser narrow fixes (bash-pinned).

Four independent divergences, each probe-verified against bash 5.2:

* M-cc1  A case pattern starting with a POSIX character class (`[[:alpha:]])`)
         on its own line mis-lexed the leading `[[` as the `[[` conditional
         operator. The `[[` operator recognizer now carries the same
         `in_case_pattern` guard the `[` recognizer already had. The related
         `[!...]` negated bracket also lexed split (`[` `!x` `]`) because the
         operator-debris recognizer treated `!` as a terminator; a `!`
         immediately after a bracket `[` is now kept.
* M-p1   Empty / dangling-operand `[[ ]]` (`[[ ]]`, `[[ ! ]]`, `[[ x || ]]`)
         were silently accepted (rc0/rc1); bash makes them syntax errors. The
         empty-operand fallback in the enhanced-test parser was removed.
* M-p2   `function NAME` accepted only a brace-group body; bash allows any
         compound command. The keyword normalizer now puts the token after the
         function name at command position, and the recursive-descent function
         parser only consumes an *empty* `()` marker (a `(` with content is a
         subshell body).
* T1-5   A nested bare `((` inside a C-style `for` header (`for ((i=0;
         i<((5)-1); i++))`) fused the following `do` body into one WORD because
         the lexer counted arithmetic `((`/`))` per-token instead of per-paren.

The end-to-end behaviour is also pinned in tests/behavioral/golden_cases.yaml
(prefix `r18t2_lexparse_`, re-run against real bash via --compare-bash).
"""

import pytest

from psh.lexer import tokenize
from psh.lexer.token_types import TokenType
from psh.parser import ParseError, Parser


def _rd_parse(source: str):
    return Parser(tokenize(source), source_text=source).parse()


def _combinator_parse(source: str):
    from psh.parser.combinators.parser import ParserCombinatorShellParser
    return ParserCombinatorShellParser().parse(list(tokenize(source)))


BOTH_PARSERS = pytest.mark.parametrize(
    "parse", [_rd_parse, _combinator_parse],
    ids=["recursive_descent", "combinator"])


def _token_types(source):
    return [t.type for t in tokenize(source)]


def _token_values(source):
    return [t.value for t in tokenize(source)]


# --------------------------------------------------------------------------
# M-cc1: case-pattern character classes lex as one WORD, on both forms
# --------------------------------------------------------------------------

@pytest.mark.parametrize("pattern", [
    "[[:alpha:]]", "[[:digit:]]", "[[:space:]]",
    "[[:alpha:][:digit:]]",  # nested classes
])
def test_case_charclass_ownline_not_double_lbracket(pattern):
    """A char-class pattern on its own line is not lexed as the `[[` operator."""
    src = f"case $c in\n{pattern}) echo hit ;;\nesac"
    types = _token_types(src)
    assert TokenType.DOUBLE_LBRACKET not in types
    assert pattern in _token_values(src)


@pytest.mark.parametrize("pattern", [
    "[[:alpha:]]", "[[:digit:]]", "[[:alpha:][:digit:]]",
])
def test_case_charclass_inline_single_word(pattern):
    """The inline form already worked; keep it lexing as one WORD too."""
    src = f"case $c in {pattern}) echo hit ;; esac"
    assert TokenType.DOUBLE_LBRACKET not in _token_types(src)
    assert pattern in _token_values(src)


@pytest.mark.parametrize("pattern", ["[!x]", "[![:space:]]", "[!abc]xyz"])
def test_negated_bracket_lexes_as_one_word(pattern):
    """`!` right after a `[` is the bracket-negation marker, not a splitter."""
    src = f"case v in {pattern}) echo hit ;; esac"
    assert pattern in _token_values(src)


@BOTH_PARSERS
@pytest.mark.parametrize("pattern", [
    "[[:alpha:]]", "[[:digit:]]", "[![:space:]]", "[[:alpha:][:digit:]]",
])
def test_case_charclass_parses_both_parsers(parse, pattern):
    """Both parsers accept a char-class first pattern on its own line."""
    parse(f"case $c in\n{pattern}) echo hit ;;\n*) echo other ;;\nesac")


# --------------------------------------------------------------------------
# M-p1: empty / dangling-operand [[ ]] is a syntax error
# --------------------------------------------------------------------------

@pytest.mark.parametrize("source", [
    "[[ ]]", "[[ ! ]]", "[[ x || ]]", "[[ x && ]]",
])
def test_empty_dbracket_rejected_rd(source):
    """The recursive-descent parser rejects a missing test operand."""
    with pytest.raises(ParseError, match="Expected test operand"):
        _rd_parse(source)


@pytest.mark.parametrize("source", [
    '[[ x ]]', '[[ "" ]]', '[[ -n x ]]', '[[ ! x ]]',
    '[[ a == a || b == c ]]',
])
def test_valid_dbracket_still_parses_rd(source):
    """Removing the empty fallback must not disturb valid tests."""
    _rd_parse(source)


# --------------------------------------------------------------------------
# M-p2: `function NAME` accepts any compound body
# --------------------------------------------------------------------------

@BOTH_PARSERS
@pytest.mark.parametrize("body", [
    "for i in 1 2; do echo $i; done",
    "if true; then echo hi; fi",
    "while false; do :; done",
    "until true; do :; done",
    "case x in x) echo m ;; esac",
    "(( 1 + 1 ))",
    "( echo sub )",
    "{ echo br; }",
])
def test_function_keyword_compound_body(parse, body):
    """`function f <compound>` parses on both parsers for every body form."""
    parse(f"function f {body}\nf")


@BOTH_PARSERS
@pytest.mark.parametrize("source", [
    "function f ( ) { echo hi; }\nf",     # empty () marker + brace body
    "function f () ( echo sub )\nf",      # () marker + subshell body
    "f() ( echo sub )\nf",                # POSIX form + subshell body
])
def test_function_paren_marker_vs_subshell_body(parse, source):
    """An empty `()` is the marker; a `(` with content is a subshell body."""
    parse(source)


def test_function_body_leading_keyword_recognized_in_lexer():
    """After `function NAME`, the body's leading keyword is a keyword token."""
    types = _token_types("function f for i in 1 2; do echo $i; done")
    assert TokenType.FOR in types  # not a bare WORD 'for'


# --------------------------------------------------------------------------
# T1-5: nested bare `((` in a C-for header does not fuse the `do` body
# --------------------------------------------------------------------------

@pytest.mark.parametrize("header", [
    "for ((i=0; i<((5)-1); i++))",
    "for ((i=(1+2); i<((10)); i++))",
])
@pytest.mark.parametrize("tail", ["; do echo x; done", "\ndo echo x\ndone"])
def test_cfor_nested_paren_does_not_fuse_do(header, tail):
    """The `do` after a C-for header with nested `((` stays its own keyword."""
    src = header + tail
    types = _token_types(src)
    assert TokenType.DO in types
    # No WORD swallowed the whitespace-joined body (the old fusion bug).
    assert not any(" " in v for v in _token_values(src))


@BOTH_PARSERS
def test_cfor_nested_paren_parses_both(parse):
    parse("for ((i=0; i<((5)-1); i++)); do echo x; done")
