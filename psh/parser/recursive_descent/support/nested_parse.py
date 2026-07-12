"""Parse the inner text of a modern command/process substitution.

Bash validates the *syntax* of ``$(...)``/``<(...)``/``>(...)`` bodies when it
reads the enclosing command, so psh parses them here, at the outer parse
(``WordBuilder``), rather than deferring to expansion time. That makes an
invalid nested body (``echo $(if)``) reject the whole input buffer before any
command runs, and lets analysis visitors descend into the substitution.

This is a SYNTAX-VALIDATION parse, with three deliberate properties:

* **No alias expansion.** bash's read-time check does not consult the alias
  table (``$(beg echo hi; done)`` where ``alias beg='for i in 1 2; do'`` is a
  syntax error at read time), and — decisively — execution re-parses the body
  against the *runtime* alias table (``alias ll=x; echo $(ll)`` runs ``x``).
  Baking parse-time alias state into the stored ``Program`` would therefore
  diverge from bash, so the stored program is the alias-free syntactic view
  used for early rejection and analysis; command_sub/process_sub still run the
  body from ``source``.
* **Heredoc-aware.** A ``$(cat <<EOF ... EOF)`` body carries its own heredocs,
  so it is tokenized with heredoc support and parsed with the heredoc map.
* **Position- and depth-aware.** Errors report the enclosing source line
  (``line_offset``) and the parent's compound-nesting budget is carried in
  (``initial_depth``), so deep ``$( $( ... ) )`` nesting degrades to a clean
  ``ParseError`` rather than a Python ``RecursionError`` traceback.
"""
from typing import TYPE_CHECKING, Mapping, Optional

from ....lexer import tokenize_with_heredocs
from ....lexer.token_types import Token, TokenType

if TYPE_CHECKING:
    from ....ast_nodes import Program

# Cap on nested modern-substitution depth (``$( $( ... ) )``). bash parses each
# level once and accepts far deeper nesting, but psh's interim approach
# re-tokenizes/re-parses each body, so a deep chain is O(n^2); this bounds the
# worst case to a clean, fast ParseError while comfortably clearing any
# realistic code (real shells nest a handful of levels). Lifting it is the job
# of the deferred lexer token-level-recursion campaign.
MAX_SUBSTITUTION_NESTING = 100


def parse_nested_command(source: str, *, line_offset: int = 0,
                         initial_depth: int = 0,
                         substitution_depth: int = 0,
                         lexer_options: Optional[Mapping[str, object]] = None
                         ) -> 'Program':
    """Parse ``source`` (a substitution body, delimiters stripped) to a Program.

    Raises :class:`ParseError` on invalid syntax (the caller lets it propagate
    to reject the enclosing parse). ``initial_depth`` seeds the compound-command
    nesting budget so a compound inside the body counts toward
    ``MAX_NESTING_DEPTH``; ``substitution_depth`` is the depth of THIS body in a
    ``$( $( ... ) )`` chain and is checked against ``MAX_SUBSTITUTION_NESTING``
    before any work, so an over-deep chain fails cheaply. ``lexer_options`` (the
    shell option dict in effect) is threaded to the tokenizer so the body is
    re-lexed with the same option-sensitive lexing as the outer command — most
    importantly ``extglob``, which governs whether ``@(a|b)`` is an extglob
    pattern. Imports are local to avoid an import cycle with the parser package,
    which reaches this module through ``WordBuilder``.
    """
    from ..helpers import ErrorContext, ParseError
    from ..parser import Parser

    if substitution_depth > MAX_SUBSTITUTION_NESTING:
        # Fail before tokenizing/parsing the (potentially huge) body.
        tok = Token(TokenType.EOF, "", 0)
        raise ParseError(ErrorContext(
            token=tok,
            message="command substitution nested too deeply",
            position=0, line=1, column=1))

    tokens, heredoc_map = tokenize_with_heredocs(source, shell_options=lexer_options)
    parser = Parser(tokens, source_text=source, line_offset=line_offset,
                    heredoc_map=heredoc_map, lexer_options=lexer_options)
    parser.ctx.nesting_depth = initial_depth
    parser.ctx.substitution_depth = substitution_depth
    return parser.parse()
