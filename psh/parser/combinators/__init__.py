"""Parser combinator module for PSH.

**Status: Experimental / Educational**

This module provides an alternative parser that uses functional composition
(parser combinators) instead of recursive descent. It is NOT the production
parser -- the recursive descent parser in ``recursive_descent/`` is the
default and handles all shell input in normal operation.

This implementation exists for two reasons:

1. **Educational contrast.** It demonstrates the same shell grammar parsed
   with a fundamentally different paradigm: immutable position passing and
   composable ``Parser[T]`` functions vs. mutable state and imperative
   control flow.

2. **Proof of concept.** It proves that parser combinators can handle
   real-world shell syntax (~95% feature coverage), which is a non-obvious
   result given the language's context-sensitivity.

There is no plan to converge the two parsers or to replace the recursive
descent parser.  The combinator parser may lag behind on new features and
edge-case fixes.  Use ``parser-select combinator`` in an interactive psh
session to experiment with it.
"""

from .commands import (
    CommandParsers,
    create_command_parsers,
    # Convenience functions
    parse_simple_command,
)
from .core import (
    ForwardParser,
    Parser,
    ParseResult,
    between,
    fail_with,
    keyword,
    # Enhanced combinators
    lazy,
    literal,
    many,
    many1,
    optional,
    separated_by,
    sequence,
    skip,
    # Basic combinators
    token,
    try_parse,
    with_error_context,
)
from .expansions import (
    ExpansionParsers,
    create_expansion_parsers,
    parse_arithmetic_expansion,
    parse_command_substitution,
    parse_process_substitution,
    # Convenience functions
    parse_variable_expansion,
)
from .tokens import (
    TokenParsers,
    create_token_parsers,
)

__all__ = [
    # Core classes
    'ParseResult',
    'Parser',
    'ForwardParser',
    # Basic combinators
    'token',
    'many',
    'many1',
    'optional',
    'sequence',
    'separated_by',
    # Enhanced combinators
    'lazy',
    'between',
    'skip',
    'fail_with',
    'try_parse',
    'keyword',
    'literal',
    'with_error_context',
    # Token parsers
    'TokenParsers',
    'create_token_parsers',
    # Expansion parsers
    'ExpansionParsers',
    'create_expansion_parsers',
    'parse_variable_expansion',
    'parse_command_substitution',
    'parse_arithmetic_expansion',
    'parse_process_substitution',
    # Command parsers
    'CommandParsers',
    'create_command_parsers',
    'parse_simple_command',
]
