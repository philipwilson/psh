"""Parser configuration for PSH.

The production grammar is NOT feature-configurable: compound-command dispatch
calls the specialized sub-parsers directly, so ``[[ ]]`` and ``(( ))`` are
always accepted regardless of configuration. The former strict-POSIX and
feature-gate fields (``parsing_mode``, ``enable_arithmetic``,
``allow_bash_conditionals``, ``allow_bash_arithmetic``) were a façade —
bypassed on every live path — and were removed. POSIX/bash behavior that IS
honored lives in the lexer (``posix`` tokenize mode) and runtime options, not
here.

Only the error-collection fields below remain; they are read by
``ParserContext``.
"""

from dataclasses import dataclass, replace
from enum import Enum


class ErrorHandlingMode(Enum):
    """Error handling strategies."""
    STRICT = "strict"                # Stop on first error
    COLLECT = "collect"              # Collect multiple errors


@dataclass
class ParserConfig:
    """Parser configuration options.

    Fields present here are actually read by parser code. Feature gates and
    strict-POSIX modes were removed because production dispatch bypassed them.
    """

    # === Error Handling ===
    error_handling: ErrorHandlingMode = ErrorHandlingMode.STRICT
    max_errors: int = 10
    collect_errors: bool = False

    def clone(self, **overrides) -> 'ParserConfig':
        """Return a copy with *overrides* applied.

        Delegates to :func:`dataclasses.replace`, so an unknown field name
        raises ``TypeError`` instead of being silently ignored (the previous
        custom implementation dropped typos without any signal).
        """
        return replace(self, **overrides)
