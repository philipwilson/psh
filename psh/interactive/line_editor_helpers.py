"""The cmdhist joiner: multi-line commands as single history lines.

``convert_multiline_to_single`` is the ONE joiner for multi-line history
entries — ``HistoryManager.add_to_history`` applies it when recording and
``HistoryNavigator._editable`` when recalling. Like bash's cmdhist, each
newline is replaced by whatever separator makes the joined text reparse to
the same program, and the decision comes from the REAL lexer and parser
(the same oracle ``CommandAccumulator`` uses), not string heuristics:

- a newline inside quotes, a heredoc, or an unclosed expansion
  (``$(``/`` ` ``/``$((``/``${``) is content and stays verbatim;
- a backslash-newline continuation is removed (POSIX splice);
- after a separator/opener token (``;`` ``;;`` ``;&`` ``;;&`` ``&`` ``|``
  ``|&`` ``&&`` ``||`` ``(`` ``{`` ``((``), after a reserved word whose
  list starts right after it (``then``/``do``/``else``/``in``/...), after
  a case pattern's ``)`` or ``f()``, and inside ``name=( ... )``, the
  newline is a plain space;
- otherwise the newline was a command separator: ``; ``.

Every rule is pinned to interactive bash 5.2 recordings by
tests/unit/test_line_editor_helpers.py.
"""

from typing import List, Optional, Tuple

from ..lexer import UnclosedQuoteError, tokenize
from ..lexer.token_types import TokenType
from ..parser import ParseError, Parser
from ..utils import contains_heredoc, open_heredoc_delimiters

# Tokens after which a newline joins as a plain space: putting `;` after
# any of these would be a syntax error (`then;`, `do;`, `&&;`, `{;`, ...).
_NO_SEMI_AFTER = frozenset({
    TokenType.SEMICOLON, TokenType.DOUBLE_SEMICOLON, TokenType.SEMICOLON_AMP,
    TokenType.AMP_SEMICOLON, TokenType.AMPERSAND, TokenType.PIPE,
    TokenType.PIPE_AND, TokenType.AND_AND, TokenType.OR_OR,
    TokenType.LPAREN, TokenType.LBRACE, TokenType.DOUBLE_LPAREN,
    TokenType.IF, TokenType.THEN, TokenType.ELSE, TokenType.ELIF,
    TokenType.WHILE, TokenType.UNTIL, TokenType.FOR, TokenType.DO,
    TokenType.CASE, TokenType.SELECT, TokenType.IN, TokenType.FUNCTION,
    TokenType.EXCLAMATION, TokenType.TIME,
})


def convert_multiline_to_single(multiline_cmd: str) -> str:
    """Join a multi-line command into its single-line history form."""
    acc: Optional[str] = None
    open_heredocs: List[Tuple[str, bool]] = []
    for line in multiline_cmd.split('\n'):
        if acc is None:
            if line.strip():
                acc = line
            continue
        if open_heredocs:
            # Heredoc body (and terminator) lines stay verbatim; the
            # detector re-scan notices which delimiters this line closed.
            acc += '\n' + line
            open_heredocs = open_heredoc_delimiters(acc)
            continue
        if not line.strip():
            continue  # bash drops blank lines from the joined entry
        candidate = acc + '\n' + line
        if contains_heredoc(candidate):
            # This line opens a heredoc, or an earlier (closed) one is
            # already in acc: the newline must survive — a terminator
            # only counts on a line of its own.
            open_heredocs = open_heredoc_delimiters(candidate)
            if open_heredocs or contains_heredoc(acc):
                acc = candidate
                continue
        sep = _separator(acc, line)
        acc = acc[:-1] + line if sep is None else acc + sep + line
    return acc if acc is not None else ''


def _separator(acc: str, line: str) -> Optional[str]:
    """The text replacing the newline between *acc* and *line*.

    ``'; '`` (command separator), ``' '`` (plain whitespace), ``'\\n'``
    (the newline is content), or None (backslash continuation: splice,
    dropping acc's trailing backslash).
    """
    try:
        tokens = tokenize(acc)
    except UnclosedQuoteError:
        return '\n'      # mid-string: the newline is quoted content
    except SyntaxError:
        return '; '      # unlexable (an invalid command, recorded as typed)

    trailing_backslashes = len(acc) - len(acc.rstrip('\\'))
    if trailing_backslashes % 2 == 1:
        return None      # line continuation (quotes are balanced here)

    unclosed, open_constructs = _trial_parse(tokens)
    if unclosed:
        return '\n'      # inside $( / ` / $(( / ${ — the newline is content

    if _first_token_is_in(line):
        return ' '       # `for i <NL> in ...` / `case x <NL> in ...`

    last = tokens[-2] if len(tokens) >= 2 else None  # tokens[-1] is EOF
    if last is None:
        return '; '
    if last.type in _NO_SEMI_AFTER:
        return ' '
    if (last.type == TokenType.WORD and len(tokens) >= 3
            and tokens[-3].type == TokenType.FUNCTION):
        return ' '       # `function NAME <NL> { ... }`: head awaits body
    if last.type == TokenType.RPAREN:
        if len(tokens) >= 3 and tokens[-3].type == TokenType.LPAREN:
            return ' '   # function parens: `f() <NL> { ... }`
        if open_constructs and open_constructs[-1] == 'case':
            return ' '   # a case pattern's closing paren
        return '; '      # a subshell close: `if (true) <NL> then ...`
    if _in_array_initializer(tokens):
        return ' '       # `a=( 1 <NL> 2 ...`: elements join with spaces
    return '; '


def _trial_parse(tokens: list) -> Tuple[Optional[str], Tuple[str, ...]]:
    """Parse the accumulated tokens; report what is still open at EOF.

    Returns ``(unclosed_expansion, open_constructs)`` — the unclosed
    expansion kind ('command', 'backtick', 'arithmetic', 'parameter') if
    the parse failed at end of input inside one, and the parser's
    open-construct trail (('case',), ('case', 'if'), ...).
    """
    parser = Parser(tokens)
    try:
        parser.parse()
    except ParseError as e:
        if e.at_eof:
            return e.unclosed_expansion, tuple(parser.ctx.open_constructs)
    return None, ()


def _first_token_is_in(line: str) -> bool:
    """True when *line* starts with the reserved word ``in`` (which must
    never be preceded by a semicolon: ``for i <NL> in ...``). At the
    start of a lone line the lexer classifies ``in`` as a WORD — the
    for/case context lives in the accumulated text — so match by value.
    """
    try:
        tokens = tokenize(line)
    except SyntaxError:
        return False
    return bool(tokens) and tokens[0].value == 'in' and \
        tokens[0].type in (TokenType.IN, TokenType.WORD)


def _in_array_initializer(tokens: list) -> bool:
    """True when the tokens end inside an unclosed ``name=( ...`` (or
    ``name+=( ...``) compound assignment."""
    stack: List[int] = []
    for i, tok in enumerate(tokens):
        if tok.type == TokenType.LPAREN:
            stack.append(i)
        elif tok.type == TokenType.RPAREN and stack:
            stack.pop()
    if not stack or stack[-1] == 0:
        return False
    before = tokens[stack[-1] - 1]
    return before.type == TokenType.WORD and (
        before.value.endswith('=') or before.value == '+=')
