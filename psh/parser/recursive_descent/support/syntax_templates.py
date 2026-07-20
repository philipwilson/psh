"""Read-time validators for expansion-bearing regions (campaign S3).

Each syntax-bearing region — a parameter-expansion operand, an arithmetic
expression, an array subscript — has its OWN grammar parsed lazily at
evaluation time, but bash validates the NESTED shell grammar (modern
``$(...)``/``<(...)``/``>(...)``) inside it at READ time. These builders do
exactly that and no more: they find the nested modern substitutions (using the
lexer's own balanced extent scanners, never a hand-rolled paren counter),
eagerly parse each body to reject invalid syntax at read time, defer legacy
backticks, and carry the result as a typed
:class:`~psh.ast_nodes.syntax_templates.SyntaxTemplate`.

Deliberately NOT a "parse every raw region as a shell program" helper (§8 S3):
the region's own arithmetic/pattern grammar is never parsed here, so
dynamically generated arithmetic keeps working. Only ``$``-expansions and
backticks are recognised, so arithmetic operators that clash with shell
metacharacters (``1 << 2``, ``a < b``, ``a && b``) are never mis-lexed — the
scanner looks for ``$`` and `` ` `` alone.

Three named builders, one per grammar (each names its region so the validator
is not generic): :func:`build_word_template` (parameter operand),
:func:`build_arithmetic_template` (arithmetic), :func:`build_subscript_spec`
(array subscript). All raise :class:`SubstitutionSyntaxError` (via the one
chokepoint ``parse_nested_command``) on an invalid nested body.
"""
from typing import TYPE_CHECKING, List, Mapping, Optional, Protocol

from ....ast_nodes import CommandSubstitution, ProcessSubstitution

if TYPE_CHECKING:
    from ....ast_nodes import Program
from ....ast_nodes.syntax_templates import (
    ArithmeticTemplate,
    NestedSub,
    SubscriptSpec,
    WordTemplate,
)
from ....lexer.cmdsub_scanner import find_command_substitution_end
from ....lexer.expansion_parser import ExpansionParser
from .nested_parse import parse_nested_command


class _TemplateCtx(Protocol):
    """The narrow parse-context contract the builders read (Q2 nit-1).

    ``line_offset`` and ``lexer_options`` are ALWAYS present — a ``ParserContext``
    property (RD) or a frozen ``ParseInputs`` field (combinator) — so they are the
    structural contract and are accessed DIRECTLY below. Read-only properties (not
    bare data attributes) so a FROZEN ``ParseInputs`` field satisfies them.
    ``nesting_depth`` / ``substitution_depth`` are deliberately NOT in this
    Protocol: the combinator's ``ParseInputs`` does not carry them (they live on
    ``ParserState``), so they are read absent-tolerantly via ``getattr(..., 0)``."""

    @property
    def line_offset(self) -> int: ...

    @property
    def lexer_options(self) -> "Optional[Mapping[str, object]]": ...


# One stateless extent finder shared by every scan (config-independent for the
# paren/brace constructs we care about; variable-name extraction never needs
# validation, so posix_mode is irrelevant here).
_EXPANSION = ExpansionParser(None)


def _validate_body(body: str, ctx: "Optional[_TemplateCtx]") -> 'Program':
    """Parse a modern substitution body at read time (raises on invalid syntax).

    Routes through the ONE chokepoint (``parse_nested_command``), which re-types
    any body ``ParseError`` as ``SubstitutionSyntaxError``. ``ctx`` (the active
    ParserContext or None) supplies the enclosing line offset and the
    compound-nesting / substitution-depth budgets, exactly like
    ``WordBuilder._nested_program``.
    """
    if ctx is not None:
        # line_offset/lexer_options are Protocol-guaranteed → direct access
        # (Q2: no defensive getattr on a declared member). nesting_depth/
        # substitution_depth are NOT on the combinator's ParseInputs, so they
        # stay absent-tolerant via getattr-with-default.
        line_offset = ctx.line_offset or 0
        depth = getattr(ctx, 'nesting_depth', 0) or 0
        sub_depth = getattr(ctx, 'substitution_depth', 0) or 0
        lexer_options = ctx.lexer_options
    else:
        line_offset, depth, sub_depth, lexer_options = 0, 0, 0, None
    return parse_nested_command(body, line_offset=line_offset,
                                initial_depth=depth,
                                substitution_depth=sub_depth + 1,
                                lexer_options=lexer_options)


def _skip_ansi_c(text: str, i: int) -> int:
    """Return the index just past a ``$'...'`` ANSI-C span starting at ``i`` (the
    ``$``). Contents are literal (no expansions); a backslash escapes the next
    char (so ``\\'`` does not close the span)."""
    n = len(text)
    j = i + 2  # past $'
    while j < n:
        if text[j] == '\\' and j + 1 < n:
            j += 2
            continue
        if text[j] == "'":
            return j + 1
        j += 1
    return n


def _scan(text: str, base: int, dq: bool, allow_procsub: bool,
          ctx: "Optional[_TemplateCtx]") -> List[NestedSub]:
    """Scan ``text`` for nested modern substitutions, validating each.

    ``base`` is ``text``'s absolute offset in the enclosing region (so recorded
    spans are absolute). ``dq`` is True inside a double-quoted run. Single quotes
    and ``$'...'`` suppress expansions; double quotes keep ``$``/backtick active
    but make ``'`` literal and disallow process substitution. ``${...}`` and
    ``$((...))`` are recursed into (their nested subs are what matter); modern
    ``$()``/``<()``/``>()`` bodies are validated; backticks are DEFERRED.
    """
    subs: List[NestedSub] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '\\' and i + 1 < n:
            i += 2
            continue
        if c == '"':
            dq = not dq
            i += 1
            continue
        if c == "'" and not dq:
            j = text.find("'", i + 1)
            i = (j + 1) if j >= 0 else n
            continue
        if c == '$' and i + 1 < n and text[i + 1] == "'" and not dq:
            i = _skip_ansi_c(text, i)
            continue
        if c == '$' and i + 1 < n:
            part, nxt = _EXPANSION.parse_expansion(text, i, '"' if dq else None)
            _handle_dollar(part.expansion_type, part.value, text, i, nxt,
                           base, dq, ctx, subs)
            i = nxt
            continue
        if c == '`':
            part, nxt = _EXPANSION.parse_backtick_substitution(
                text, i, '"' if dq else None)
            # DEFERRED backtick: carried un-validated (source is the RAW slice so
            # it round-trips through the reconstruction guard). bash never
            # read-time-validates backticks; expansion re-parses them.
            subs.append(NestedSub(
                CommandSubstitution(program=None, source=text[i + 1:nxt - 1],
                                    backtick_style=True),
                base + i, base + nxt))
            i = nxt
            continue
        if (allow_procsub and not dq and c in '<>'
                and i + 1 < n and text[i + 1] == '('):
            end, found = find_command_substitution_end(text, i + 2)
            if found:
                body = text[i + 2:end - 1]
                prog = _validate_body(body, ctx)
                subs.append(NestedSub(
                    ProcessSubstitution(
                        direction='in' if c == '<' else 'out',
                        program=prog, source=body),
                    base + i, base + end))
                i = end
                continue
        i += 1
    return subs


def _handle_dollar(etype: Optional[str], value: str, text: str, i: int,
                   nxt: int, base: int, dq: bool, ctx: "Optional[_TemplateCtx]",
                   subs: List[NestedSub]) -> None:
    """Dispatch a ``$``-expansion found by the lexer's extent scanner."""
    if etype == 'command':
        body = value[2:-1]  # strip $( )
        prog = _validate_body(body, ctx)
        subs.append(NestedSub(
            CommandSubstitution(program=prog, source=body, backtick_style=False),
            base + i, base + nxt))
    elif etype == 'arithmetic':
        # Recurse into the arithmetic content (no process substitution — < / >
        # are arithmetic operators there). Offset by the `$((` prefix.
        subs.extend(_scan(value[3:-2], base + i + 3, False, False, ctx))
    elif etype == 'parameter':
        # Recurse into the ${...} content (its operand may hold nested subs).
        subs.extend(_scan(value[2:-1], base + i + 2, dq, True, ctx))
    elif etype and etype.endswith('_unclosed'):
        # The enclosing lexer already balanced this region, so an unclosed inner
        # construct means the region text itself is malformed — surface it as a
        # read-time error by validating the partial body.
        if etype == 'command_unclosed':
            _validate_body(value[2:], ctx)
    # 'variable' and a bare literal '$' need no validation.


def build_word_template(text: str, ctx: "Optional[_TemplateCtx]" = None) -> WordTemplate:
    """Validate the nested shell grammar of a parameter-expansion operand.

    ``text`` is the raw operand (``${x:-<text>}``), quotes included. Process
    substitution is permitted (an operand is word context). Raises on an invalid
    nested modern substitution; backticks are deferred.
    """
    return WordTemplate(text=text, subs=tuple(_scan(text, 0, False, True, ctx)))


def build_arithmetic_template(text: str, ctx: "Optional[_TemplateCtx]" = None) -> ArithmeticTemplate:
    """Validate the nested shell grammar of an arithmetic region.

    ``text`` is the raw arithmetic expression (``$((<text>))`` / ``(( <text> ))``
    / a C-style ``for`` clause). Its arithmetic grammar is NOT parsed here (lazy,
    so dynamic arithmetic keeps working); only nested modern ``$()`` are
    validated. Process substitution is disabled (``<`` / ``>`` are operators).
    """
    return ArithmeticTemplate(text=text, subs=tuple(_scan(text, 0, False, False, ctx)))


def build_subscript_spec(text: str, ctx: "Optional[_TemplateCtx]" = None) -> SubscriptSpec:
    """Validate the nested shell grammar of an array subscript.

    ``text`` is the raw subscript (``arr[<text>]``). Nested modern ``$()`` are
    validated at read time; the indexed-vs-associative interpretation is W2's
    ``SubscriptEvaluator`` (not decided here). Process substitution is disabled
    (an indexed subscript is arithmetic context).
    """
    return SubscriptSpec(text=text, subs=tuple(_scan(text, 0, False, False, ctx)))
