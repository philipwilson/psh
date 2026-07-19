"""Canonical shell-pattern matching for the whole shell.

Every construct that matches a shell glob pattern against a string —
``case`` patterns, ``[[ string == pattern ]]``, the parameter operators
``${var#pat}`` / ``${var%pat}`` / ``${var/pat/repl}``, pathname components,
and name filters (``HISTIGNORE``) — routes through the ONE compiled pattern
engine (``pattern_engine``), so glob/extglob semantics (escapes, bracket
classes, extglob) cannot drift between constructs and no construct backtracks
exponentially or raises ``RecursionError`` (#20 H7).
"""
from .pattern_engine import PatternCompiler, string_profile


def match_shell_pattern(string: str, pattern: str,
                        extglob_enabled: bool = False,
                        ignorecase: bool = False) -> bool:
    """Full-match ``string`` against a shell glob ``pattern``.

    Honors backslash escapes in the pattern (a ``\\*`` matches a literal
    asterisk — this is how quoted pattern text is kept literal), bracket
    classes, and extglob operators when enabled. When ``ignorecase`` is
    True (the ``nocasematch`` shopt), matching is case-insensitive — used
    by ``[[ == ]]`` and ``case`` matching (the shared ``[:upper:]`` /
    ``[:lower:]`` case-sensitivity under ``nocasematch`` is handled by the
    engine's locale-aware bracket membership).

    ``pattern`` is a raw pattern string (``\\`` = escape). Consumers that know
    protection per-character (pathname fields, ``${...}`` operands) compile via
    ``PatternCompiler.compile_protected`` instead.
    """
    return PatternCompiler.compile(pattern, extglob=extglob_enabled).full_match(
        string, string_profile(ignorecase))
