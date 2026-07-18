"""The total parse outcome: ``Complete | Incomplete | Invalid``.

Campaign S4 (`docs/reviews/boundary_campaign_briefs_2026-07-16.md` §8) makes the
result of a parse an explicit, TYPED sum instead of "a ``Program`` on success,
or a ``ParseError`` whose ``at_eof`` field the caller re-derives the trichotomy
from":

* :class:`Complete` — the input parsed into a ``Program``.
* :class:`Incomplete` — the parse failed AT end of input, so more lines could
  complete it. Carries :class:`ExpectedInput` (the open-construct trail and any
  unclosed-expansion kind) — exactly what the PS2 continuation prompt needs.
* :class:`Invalid` — a real syntax error: the input is complete but ill-formed.
  Carries the ``ParseError`` diagnostic, and preserves its
  ``substitution_origin`` fact (the S3/I3 producer contract survives here).

:func:`outcome_from_parse` is the SINGLE decision point that classifies a raised
``ParseError`` into ``Incomplete`` vs ``Invalid`` (via ``at_eof``); both parser
implementations expose ``parse_outcome()`` built on it, so the trichotomy is
computed once, not re-derived at each consumer. :func:`materialize` is the
terminal adapter: it turns an outcome back into the ``Program`` (or re-raises the
carried error) for the execution call sites that still want the raising surface.

The one-shot outcome here is the same sum the resumable parser session (campaign
I3) will return, so I3 consumes this contract rather than inventing a second one.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterable, Optional, Tuple, Union

if TYPE_CHECKING:
    from ..ast_nodes import Program
    from .recursive_descent.helpers import ParseError


@dataclass(frozen=True)
class ExpectedInput:
    """Why a parse is INCOMPLETE — what more input the parser is waiting for.

    Attributes:
        constructs: The open-construct trail at the point of failure
            (``('if',)``, ``('for', 'then')``, ...). The interactive layer
            renders its contextual PS2 (``if> ``, ``for then> ``) from it.
        unclosed_expansion: Which expansion kind is still open ('command',
            'parameter', 'arithmetic', 'backtick'), or ``None`` when the
            incompleteness is a plain unclosed compound structure.
    """

    constructs: Tuple[str, ...] = ()
    unclosed_expansion: Optional[str] = None


@dataclass(frozen=True)
class Complete:
    """The input parsed into a complete ``Program``."""

    program: "Program"


@dataclass(frozen=True)
class Incomplete:
    """The parse failed at end of input; more input could complete it.

    ``error`` is the underlying ``at_eof`` ``ParseError`` (kept so a caller that
    still wants to render or re-raise it can, and so ``materialize`` has a
    concrete error to raise).
    """

    expected: ExpectedInput
    error: "ParseError"


@dataclass(frozen=True)
class Invalid:
    """A real syntax error: the input is complete but ill-formed.

    ``error`` is the diagnostic ``ParseError``. Its ``substitution_origin`` fact
    (``SubstitutionSyntaxError``) rides through unchanged, so the I3 consumer can
    still recognise a substitution-body origin from ``error``.
    """

    error: "ParseError"


# The total outcome sum. New code should branch on the three variants; the
# ``.error`` attribute is present on both failing variants for uniform handling.
ParseOutcome = Union[Complete, Incomplete, Invalid]


def outcome_from_parse(
    parse_fn: "Callable[[], Program]",
    open_constructs: "Callable[[], Iterable[str]]",
) -> ParseOutcome:
    """Run one parse and classify it into the ``Complete | Incomplete | Invalid``
    sum — the SINGLE place the trichotomy is decided.

    ``parse_fn`` is the raising one-shot parse (``Parser.parse`` /
    ``ParserCombinatorShellParser.parse``); ``open_constructs`` reports the
    parser's open-construct trail, read only when the parse raised at end of
    input. A ``ParseError`` with ``at_eof`` becomes ``Incomplete`` carrying the
    trail and any ``unclosed_expansion`` kind; any other ``ParseError`` becomes
    ``Invalid``. (Lexer-layer failures — ``UnclosedQuoteError`` and other
    ``SyntaxError``s raised before parsing — are the caller's concern and are not
    caught here.)
    """
    # cycle-break: ParseError lives in recursive_descent.helpers, and importing
    # any recursive_descent.* submodule runs recursive_descent/__init__ which
    # eagerly loads recursive_descent.parser -> back to this module. Deferring
    # the class import here keeps this peer outcome module import-clean.
    from .recursive_descent.helpers import ParseError

    try:
        return Complete(parse_fn())
    except ParseError as exc:
        if exc.at_eof:
            return Incomplete(
                ExpectedInput(
                    constructs=tuple(open_constructs()),
                    unclosed_expansion=exc.unclosed_expansion,
                ),
                error=exc,
            )
        return Invalid(error=exc)


def materialize(outcome: ParseOutcome) -> "Program":
    """Terminal adapter: return the ``Program`` or re-raise the carried error.

    The execution call sites that want the historical raising surface call
    ``materialize(parser.parse_outcome())`` (or, unchanged, the parser's own
    ``parse()`` which is exactly this over its own ``parse_outcome``-free path).
    """
    if isinstance(outcome, Complete):
        return outcome.program
    raise outcome.error
