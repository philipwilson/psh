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
        """
        from .extglob import contains_extglob, extglob_to_regex, glob_to_regex_body
        if extglob_enabled and contains_extglob(pattern):
            return extglob_to_regex(pattern, anchored=anchored,
                                    from_start=from_start)

        # Plain glob: reuse the shared converter (extglob operators are literal
        # here). This also handles a leading ']' in a class (e.g. [], [!]]),
        # which the former inline loop produced an invalid empty class for.
        regex = glob_to_regex_body(pattern, for_pathname=False, extglob=False)

        if anchored:
            if from_start:
                regex = '^' + regex
            else:
                # For suffix matching, we'll add $ later
                pass

        return regex


def match_shell_pattern(string: str, pattern: str,
                        extglob_enabled: bool = False) -> bool:
    """Full-match ``string`` against a shell glob ``pattern``.

    Honors backslash escapes in the pattern (a ``\\*`` matches a literal
    asterisk — this is how quoted pattern text is kept literal), bracket
    classes, and extglob operators when enabled.
    """
    regex = PatternMatcher().shell_pattern_to_regex(
        pattern, extglob_enabled=extglob_enabled)
    return re.fullmatch(regex, string) is not None
