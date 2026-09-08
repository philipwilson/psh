"""bash's ``legal_number`` for builtin NUMERIC OPERANDS.

Python's ``int()`` is not bash's operand parser, and every difference is a
silently-accepted operand where bash 5.3.15 reports ``numeric argument
required`` with the usage status.  ``int()`` accepts PEP 515 underscores
(``5_0``), every Unicode decimal digit (``٥``, ``１``), and integers of
unbounded width; bash's ``legal_number`` is ``strtoimax`` on base 10 plus a
"the whole string was consumed" check, so it accepts ASCII digits only and
must fit a C ``intmax_t``.

The gap is not cosmetic: before this validator existed, ``exit
99999999999999999999`` EXITED psh (255) where bash reports the error and
carries on, and it killed an INTERACTIVE psh outright.

Grammar accepted (empirical, bash 5.3.15, probed 2026-09-07 in -c,
script-file and stdin modes; no CHANGES/NEWS item — the operand parser did
not change in 5.3, only the STATUS the caller reports)::

    [ws] [ '+' | '-' ] DIGIT+ [ws]        ws = space \\t \\n \\v \\f \\r

with the value in ``[-2**63, 2**63-1]``.  So ``'  7  '``, ``+5``, ``-0``,
``007`` and ``9223372036854775807`` are numbers, while ``5_0``, ``٥``,
``0x10``, ``1e3``, ``1.5``, ``''``, ``+ 7``, ``++7``, ``7abc`` and
``9223372036854775808`` are not.

Reproduce a rejection::

    bash -c 'exit 5_0; echo rc=$?'                  # rc=2, shell lives
    bash -c 'exit 9223372036854775808; echo rc=$?'  # rc=2
    bash -c 'exit 9223372036854775807'              # accepted -> 255

The CALLER owns what a rejection means: it is the numeric-argument cell of
the usage-error family, so each consumer routes a ``None`` into
``core/internal_errors.py``'s operand outcome rather than inventing a status.
"""
import re
from typing import Optional

#: intmax_t on every platform psh targets; bash's ``legal_number`` fails
#: (rather than saturating) when ``strtoimax`` reports ERANGE.
INT64_MIN = -(2 ** 63)
INT64_MAX = 2 ** 63 - 1

#: The whole-string grammar. ``\s`` is deliberately NOT used: it also matches
#: Unicode separators that C's ``isspace`` does not, which would let
#: ``exit ' 5'`` through.
_LEGAL_NUMBER = re.compile(r'\A[ \t\n\v\f\r]*[+-]?[0-9]+[ \t\n\v\f\r]*\Z')


def legal_number(text: str) -> Optional[int]:
    """The operand's value, or ``None`` when bash would reject it.

    ``None`` means exactly "bash prints ``numeric argument required``" — it is
    never a value, so callers test for it explicitly rather than for falsity
    (``legal_number('0')`` is ``0``, a perfectly good operand).
    """
    if not _LEGAL_NUMBER.match(text):
        return None
    value = int(text.strip(' \t\n\v\f\r'))
    if not INT64_MIN <= value <= INT64_MAX:
        return None
    return value
