"""Canonical shell-pattern matching for the whole shell.

Every construct that matches a shell glob pattern against a string —
``case`` patterns, ``[[ string == pattern ]]``, and the parameter
operators ``${var#pat}`` / ``${var%pat}`` / ``${var/pat/repl}`` — uses
this module, so glob semantics (escapes, bracket classes, extglob)
cannot drift between constructs. Pathname expansion (psh/expansion/
glob.py) shares the same underlying converter in extglob.py.
"""

import re


class PatternMatcher:
    """Convert shell patterns to regex and perform matching."""

    def shell_pattern_to_regex(self, pattern: str, anchored: bool = False,
                               from_start: bool = True,
                               extglob_enabled: bool = False) -> str:
        """
        Convert shell glob pattern to Python regex.

        Args:
            pattern: Shell pattern with *, ?, [...]
            anchored: If True, pattern must match from start or end
            from_start: If anchored, whether to anchor at start (True) or end (False)
            extglob_enabled: If True and pattern contains extglob, use extglob converter

        A pattern whose regex cannot compile (e.g. the reversed range
        ``[z-a]``) yields the never-matching ``(?!)`` — bash quietly
        matches NOTHING for such patterns; a crash must never escape.
        This validation is the single chokepoint for every caller
        (parameter operators, ``case``, ``[[ == ]]``).
        """
        from .extglob import contains_extglob, extglob_to_regex, glob_to_regex_body
        if extglob_enabled and contains_extglob(pattern):
            regex = extglob_to_regex(pattern, anchored=anchored,
                                     from_start=from_start)
        else:
            # Plain glob: reuse the shared converter (extglob operators are
            # literal here). This also handles a leading ']' in a class
            # (e.g. [], [!]]), which the former inline loop produced an
            # invalid empty class for.
            regex = glob_to_regex_body(pattern, for_pathname=False,
                                       extglob=False)
            if anchored and from_start:
                regex = '^' + regex
                # (suffix matching: callers add the '$' themselves)

        try:
            re.compile(regex)
        except re.error:
            return '(?!)'
        return regex


def match_shell_pattern(string: str, pattern: str,
                        extglob_enabled: bool = False,
                        ignorecase: bool = False) -> bool:
    """Full-match ``string`` against a shell glob ``pattern``.

    Honors backslash escapes in the pattern (a ``\\*`` matches a literal
    asterisk — this is how quoted pattern text is kept literal), bracket
    classes, and extglob operators when enabled. When ``ignorecase`` is
    True (the ``nocasematch`` shopt), matching is case-insensitive — used
    by ``[[ == ]]`` and ``case`` matching.
    """
    from .extglob import _contains_negation, extglob_fullmatch
    if extglob_enabled and _contains_negation(pattern):
        # Negation isn't expressible as a Python regex; use the matcher.
        return extglob_fullmatch(pattern, string, ignorecase=ignorecase)

    regex = PatternMatcher().shell_pattern_to_regex(
        pattern, extglob_enabled=extglob_enabled)
    flags = re.IGNORECASE if ignorecase else 0
    return re.fullmatch(regex, string, flags) is not None
