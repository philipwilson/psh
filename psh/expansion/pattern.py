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
                               extglob_enabled: bool = False,
                               ignorecase: bool = False) -> str:
        """
        Convert shell glob pattern to Python regex.

        Args:
            pattern: Shell pattern with *, ?, [...]
            anchored: If True, pattern must match from start or end
            from_start: If anchored, whether to anchor at start (True) or end (False)
            extglob_enabled: If True and pattern contains extglob, use extglob converter
            ignorecase: If True (``nocasematch``), keep ``[:upper:]``/
                ``[:lower:]`` case-sensitive even though the caller applies
                ``re.IGNORECASE`` — bash folds literals/ranges/sets but not
                those two classes (see ``_bracket_to_regex``).

        A pattern whose regex cannot compile (e.g. the reversed range
        ``[z-a]``) yields the never-matching ``(?!)`` — bash quietly
        matches NOTHING for such patterns; a crash must never escape.
        This validation is the single chokepoint for every caller
        (parameter operators, ``case``, ``[[ == ]]``).
        """
        from .extglob import contains_extglob, extglob_to_regex, glob_to_regex_body
        if extglob_enabled and contains_extglob(pattern):
            regex = extglob_to_regex(pattern, anchored=anchored,
                                     from_start=from_start, ic=ignorecase)
        else:
            # Plain glob: reuse the shared converter (extglob operators are
            # literal here). This also handles a leading ']' in a class
            # (e.g. [], [!]]), which the former inline loop produced an
            # invalid empty class for.
            regex = glob_to_regex_body(pattern, for_pathname=False,
                                       extglob=False, ic=ignorecase)
            if anchored and from_start:
                regex = '^' + regex
                # (end anchoring: callers append the \Z anchor themselves —
                # see parameter_expansion._end_anchored; never '$', which
                # also matches before a trailing newline)

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
    by ``[[ == ]]`` and ``case`` matching. ``ignorecase`` is forwarded to
    the regex builder (not only applied as ``re.IGNORECASE``) so that
    ``[[:upper:]]``/``[[:lower:]]`` stay case-sensitive under
    ``nocasematch``, matching bash (see ``_bracket_to_regex``).
    """
    from .extglob import contains_extglob, extglob_fullmatch
    if extglob_enabled and contains_extglob(pattern):
        # ANY extglob group routes through the compiled memoized engine, not a
        # regex: negation was never regex-expressible, and ambiguous repetition
        # (``*(a|aa)c``) makes Python ``re`` backtrack catastrophically. The
        # engine is linear-state and returns the same full-match result
        # (verified vs the former regex backend over thousands of cases).
        # Plain globs (no extglob group) keep the fast, well-tested regex path.
        return extglob_fullmatch(pattern, string, ignorecase=ignorecase)

    regex = PatternMatcher().shell_pattern_to_regex(
        pattern, extglob_enabled=extglob_enabled, ignorecase=ignorecase)
    flags = re.IGNORECASE if ignorecase else 0
    return re.fullmatch(regex, string, flags) is not None
