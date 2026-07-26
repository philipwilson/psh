"""Immutable parse inputs and mutable per-call parser state.

Campaign S4 (`docs/reviews/boundary_campaign_briefs_2026-07-16.md` §8) separates
the two kinds of thing a parse call carries:

* :class:`ParseInputs` — the FROZEN caller context: what the caller supplies
  *about* this parse (source text for diagnostics, the enclosing line offset,
  the shell lexer options, the collected heredoc map, the parser config). It
  never changes while the parse runs.
* :class:`ParserState` — the MUTABLE per-call state: where the parse currently
  *is* (the token cursor, the compound-nesting and substitution-nesting depth
  counters, and the open-construct trail). It advances as the parse proceeds.

The token stream itself is neither: it is the parse SUBJECT, owned mutably by
:class:`~psh.parser.recursive_descent.context.ParserContext` (which composes one
``ParseInputs`` and one ``ParserState``). Keeping the stream out of the frozen
inputs is deliberate — the recursive-descent parser rewrites exactly one slot of
its private token-list copy (the non-leading ``time`` → WORD substitution in
``CommandParser._parse_compound_component``), an observationally-pure edit of a
copy the caller never sees.

Because inputs and state are distinct objects built once with the
``ParserContext`` and never transiently installed elsewhere, there is nothing
for ``parse()`` to clear in a ``finally``. This does NOT make the RD ``Parser``
reusable: its ``ParserContext`` (and its ``ParserState`` cursor) is bound at
construction to the tokens given there, and ``parse()`` CONSUMES the cursor
without resetting it. The RD ``Parser`` is therefore SINGLE-USE (remediation
MEDIUM-11) — a second ``parse()``/``parse_outcome()`` raises a ``RuntimeError``
rather than silently returning an empty ``Program``; construct a new ``Parser``
(or use the module-level ``parse()``) to parse again. The combinator parser is
reusable by contrast: it takes tokens per ``parse(tokens)`` call. Both facts are
guarded by ``tests/unit/parser/test_parse_inputs_state_s4.py``.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Mapping, Optional

from .config import ParserConfig

if TYPE_CHECKING:
    from ..lexer.heredoc_lexer import LexedHeredoc


@dataclass(frozen=True)
class ParseInputs:
    """Immutable caller context for one parse (§5 canonical type).

    The ``source`` of §8's ``ParseInputs(source, line_offset, lexer_options,
    heredocs)`` is :attr:`source_text`; ``config`` rides along as the (also
    immutable) parser configuration. Frozen, so no consumer can reach back and
    mutate the caller's context mid-parse.

    Attributes:
        source_text: Original source for error messages (``None`` for a bare
            token list).
        line_offset: Source lines BEFORE this fragment in the enclosing input,
            so a nested/multi-line fragment's diagnostics report absolute lines.
        lexer_options: The shell option dict in effect (a plain data dict, never
            a ``Shell`` reference), threaded so a nested substitution body
            re-lexes with the same option-sensitive lexing (extglob) as the
            outer command. ``None`` outside the live shell parse path.
        heredocs: The ``LexedUnit``'s id-keyed map of ``LexedHeredoc`` entries
            (delimiter spec + collected body); present only on the
            heredoc-aware parse path, ``None`` otherwise.
        config: The parser configuration.
    """

    source_text: Optional[str] = None
    line_offset: int = 0
    lexer_options: Optional[Mapping[str, object]] = None
    heredocs: "Optional[Mapping[int, 'LexedHeredoc']]" = None
    config: ParserConfig = field(default_factory=ParserConfig)


@dataclass
class ParserState:
    """Mutable per-call parser state (§5 canonical type).

    Everything here advances during one parse and is meaningless across parses.
    A fresh ``ParserState`` is built for every ``ParserContext``; nothing carries
    over, so a parser instance holds no live state once its parse returns.

    Attributes:
        cursor: Current token position (the old ``ParserContext.current``).
        nesting_depth: Compound-command nesting depth, a resource counter checked
            against ``MAX_NESTING_DEPTH`` at the single compound chokepoint.
        substitution_depth: Nested modern-substitution depth, capped so an
            adversarially deep ``$( $( ... ) )`` chain fails as a clean
            ``ParseError`` rather than an O(n^2) re-parse cascade.
        open_constructs: Write-only trail of which constructs are open ('if',
            'then', 'while', ...). No parse decision reads it; its one consumer
            is the incomplete-input hint (``Incomplete``/``CommandAccumulator``)
            that drives the interactive ``if> ``/``for then> `` prompts.
    """

    cursor: int = 0
    nesting_depth: int = 0
    substitution_depth: int = 0
    open_constructs: List[str] = field(default_factory=list)
