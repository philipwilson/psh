"""Parser configuration for PSH.

The production grammar is NOT configurable. Compound-command dispatch calls
the specialized sub-parsers directly, so ``[[ ]]`` and ``(( ))`` are always
accepted. The former strict-POSIX / feature-gate fields were a façade, and the
error-collection fields (``collect_errors``/``max_errors``/``error_handling``)
drove an unsafe recovery mode that returned fabricated ASTs and whose collected
errors were never read — all removed.

``ParserConfig`` therefore carries no options today. It is retained as the
parser's single configuration object and extension point: it threads through
the factory, ``ParserContext``, and every sub-parser, so a genuinely
grammar-affecting option can be added here in one place if one is ever needed.
POSIX/bash behavior that IS honored lives in the lexer (``posix`` tokenize
mode) and runtime options, not here.
"""

from dataclasses import dataclass, replace


@dataclass
class ParserConfig:
    """Parser configuration options.

    Currently empty: the production parser has no grammar-affecting options.
    """

    def clone(self, **overrides) -> 'ParserConfig':
        """Return a copy with *overrides* applied.

        Delegates to :func:`dataclasses.replace`, so an unknown field name
        raises ``TypeError`` instead of being silently ignored.
        """
        return replace(self, **overrides)
