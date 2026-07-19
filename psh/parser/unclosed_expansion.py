"""The single unclosed-expansion detector shared by both parsers.

The lexer deliberately tolerates ``${``, ``$(``, `` ` ``, ``$((``, and
``<(``/``>(`` without their closer so interactive and script line-gathering can
keep reading more physical lines until the closer arrives (multi-line command
substitution, parameter expansion, arithmetic, backticks, process
substitution — possibly with heredocs nested inside). At PARSE time such an
open expansion at end of input is INCOMPLETE input, not a hard syntax error:
more lines could close it. Both selectable parsers must classify it as
``Incomplete`` (``at_eof``), carrying WHICH expansion kind is open so the
continuation prompt / completeness oracle never string-matches a message
(campaign S4/I3).

Historically each parser inspected the token itself: the recursive-descent
``CommandParser._check_for_unclosed_expansions`` and the combinator's
``_unclosed_expansion_error`` were two hand-copied implementations that had
already drifted (the combinator gave a GENERIC "unclosed expansion" message for
fused-word parts and computed no kind, so its outcome classified as ``Invalid``
where recursive descent gave ``Incomplete`` — the disclosed S4 divergence). This
module is the ONE producer of that fact: it inspects a word-like token and
returns the diagnostic MESSAGE plus the structured KIND. Each parser turns a
non-``None`` result into its own ``at_eof`` ``ParseError`` with the kind, so the
two agree by construction (guarded by the combinator/RD parity pins in
``tests/unit/parser/test_parse_outcome_s4.py``).
"""

from dataclasses import dataclass
from typing import Optional

from ..lexer.token_types import Token

# Fused-word part expansion-type -> (human description, literal prefix, the
# number of prefix characters already present in ``part.value``). The message
# quotes ``prefix + part.value[skip:]`` so a decomposed part reads the same as
# a whole COMMAND_SUB/VARIABLE/... token would.
_PART_UNCLOSED = {
    'parameter_unclosed': ("unclosed parameter expansion", '${', 2),
    'command_unclosed': ("unclosed command substitution", '$(', 2),
    'arithmetic_unclosed': ("unclosed arithmetic expansion", '$((', 3),
    'backtick_unclosed': ("unclosed backtick substitution", '`', 1),
}

# The token types whose value/parts may carry an open expansion. A hoisted


@dataclass(frozen=True)
class UnclosedExpansion:
    """A word-like token carries an expansion left open at end of input.

    ``message`` is the full ``"syntax error: ..."`` diagnostic (identical
    across both parsers); ``kind`` is the structured signal the continuation
    hints key off ('command', 'parameter', 'arithmetic', 'backtick').
    """

    message: str
    kind: str


def detect_unclosed_expansion(token: Token) -> Optional[UnclosedExpansion]:
    """Return the open-expansion fact for ``token``, or ``None`` if closed.

    Inspection order mirrors the historical recursive-descent check: a fused
    WORD carrying an ``*_unclosed`` part first, then a whole expansion token
    whose value lacks its closer. The token-type strings are compared by name
    (``token.type.name``) so this module needs no import from either parser.
    """
    # 1. A fused WORD (or decomposable token) whose parts carry an unclosed
    #    expansion. Raise on the first such part.
    for part in token.parts or ():
        expansion_type = part.expansion_type
        if expansion_type and expansion_type.endswith('_unclosed'):
            kind = expansion_type[:-len('_unclosed')]
            fmt = _PART_UNCLOSED.get(expansion_type)
            if fmt:
                desc, prefix, skip = fmt
                message = f"syntax error: {desc} '{prefix}{part.value[skip:]}'"
            else:
                message = f"syntax error: unclosed expansion '{part.value}'"
            return UnclosedExpansion(message, kind)

    # 2. A whole expansion token whose value never reached its closer.
    value = token.value
    name = token.type.name
    if name == 'VARIABLE' and value.startswith('${') and not value.endswith('}'):
        return UnclosedExpansion(
            f"syntax error: unclosed parameter expansion '{value}'", 'parameter')
    if name == 'COMMAND_SUB' and not value.endswith(')'):
        return UnclosedExpansion(
            f"syntax error: unclosed command substitution '{value}'", 'command')
    if name == 'COMMAND_SUB_BACKTICK' and value.count('`') == 1:
        return UnclosedExpansion(
            f"syntax error: unclosed backtick substitution '{value}'", 'backtick')
    if name == 'ARITH_EXPANSION' and not value.endswith('))'):
        return UnclosedExpansion(
            f"syntax error: unclosed arithmetic expansion '{value}'", 'arithmetic')
    if name in ('PROCESS_SUB_IN', 'PROCESS_SUB_OUT') and not value.endswith(')'):
        # An unclosed `<(`/`>(` swallows everything to end of input, like $(...);
        # its continuation kind is 'command' (a command list body).
        return UnclosedExpansion(
            f"syntax error: unclosed process substitution '{value}'", 'command')
    return None
