"""Advanced parameter expansion operations.

String operations behind the ``${var<op>...}`` operators (pattern removal,
substitution, substring, case modification, name matching). Parsing of the
``${...}`` syntax itself lives in param_parser.py.
"""
import re
from typing import TYPE_CHECKING, List, Optional, Union

# Canonical pattern engine lives in pattern.py; re-exported here because
# many call sites import PatternMatcher from this module.
from .pattern import PatternMatcher

if TYPE_CHECKING:
    from ..shell import Shell

# Sentinel marking "the matched text" in a prepared replacement template
# (bash 5.2 patsub_replacement: an unquoted & in the replacement).
PATSUB_MATCH = object()


class ParameterExpansion:
    """Advanced parameter expansion operations."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state
        self.pattern_matcher = PatternMatcher()

    @property
    def _extglob(self) -> bool:
        """Whether extglob is currently enabled."""
        return self.state.options.get('extglob', False)

    @property
    def _nocasematch(self) -> bool:
        """Whether ``shopt -s nocasematch`` is active.

        bash applies nocasematch to pattern *substitution* (``${v/pat/r}`` and
        its ``/#`` /``/%`` forms) but NOT to prefix/suffix *removal* (``#``/``%``)
        or case modification — so only the ``substitute_*`` helpers consult it.
        """
        return self.state.options.get('nocasematch', False)

    @staticmethod
    def render_replacement(replacement: Union[str, list], matched: str) -> str:
        """Render the replacement text for one match.

        A prepared template (list built by VariableExpander) may contain
        PATSUB_MATCH entries standing for the matched text; a plain string
        is inserted literally (never interpreted as a regex template).
        """
        if isinstance(replacement, str):
            return replacement
        return ''.join(matched if part is PATSUB_MATCH else part
                       for part in replacement)

    # Length operations
    def get_length(self, value: str) -> str:
        """Get the length of a string."""
        return str(len(value))

    def _neg(self, pattern: str) -> bool:
        """Whether *pattern* needs the backtracking matcher rather than a regex.

        Extglob negation ``!(...)`` — standalone OR embedded (``${v#x!(o)}``,
        ``${v/a!(b)c/r}``) — cannot be expressed as a Python regex (see
        ``extglob._extglob_consume``), so those operators match span-by-span via
        the matcher. Non-negation patterns keep the fast regex path unchanged.
        """
        if not self._extglob:
            return False
        from .extglob import _contains_negation
        return _contains_negation(pattern)

    # Pattern removal
    def _prefix_match_regex(self, pattern: str):
        """Compiled regex that FULL-matches a candidate prefix.

        Mirrors the suffix path's ``rstrip('$') + '$'`` shaping but anchors
        at the START: the result must match an entire candidate prefix so the
        position scan below can pick the shortest / longest matching prefix.
        Using a per-prefix full match (rather than one greedy/non-greedy pass
        over the whole value) makes extglob quantifiers behave correctly —
        the old ``.*`` → ``.*?`` rewrite never touched ``+(o)``/``*(o)`` and
        the extglob converter additionally ``$``-anchored the pattern, so
        ``#`` behaved like ``##``.
        """
        regex = self.pattern_matcher.shell_pattern_to_regex(
            pattern, anchored=True, from_start=True,
            extglob_enabled=self._extglob)
        # Anchor the END too so the regex matches a WHOLE candidate prefix
        # (the extglob converter already appends '$'; the plain-glob path
        # does not — normalise both).
        if not regex.endswith('$'):
            regex = regex + '$'
        return re.compile(regex)

    def remove_shortest_prefix(self, value: str, pattern: str) -> str:
        """Remove shortest matching prefix."""
        if self._neg(pattern):
            from .extglob import _extglob_consume
            lengths = _extglob_consume(pattern, value)
            return value[min(lengths):] if lengths else value
        compiled = self._prefix_match_regex(pattern)
        # Shortest matching prefix: scan from the front.
        for i in range(len(value) + 1):
            if compiled.match(value[:i]):
                return value[i:]
        return value

    def remove_longest_prefix(self, value: str, pattern: str) -> str:
        """Remove longest matching prefix."""
        if self._neg(pattern):
            from .extglob import _extglob_consume
            lengths = _extglob_consume(pattern, value)
            return value[max(lengths):] if lengths else value
        compiled = self._prefix_match_regex(pattern)
        # Longest matching prefix: scan from the back.
        for i in range(len(value), -1, -1):
            if compiled.match(value[:i]):
                return value[i:]
        return value

    def remove_shortest_suffix(self, value: str, pattern: str) -> str:
        """Remove shortest matching suffix."""
        if self._neg(pattern):
            from .extglob import extglob_fullmatch
            # Shortest suffix removed = the largest start index whose suffix
            # matches the pattern.
            for i in range(len(value), -1, -1):
                if extglob_fullmatch(pattern, value[i:]):
                    return value[:i]
            return value
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=True, from_start=False, extglob_enabled=self._extglob)
        # Convert to end-anchored regex
        regex = regex.rstrip('$') + '$'

        # Find shortest match from end
        for i in range(len(value), -1, -1):
            if re.match(regex, value[i:]):
                return value[:i]
        return value

    def remove_longest_suffix(self, value: str, pattern: str) -> str:
        """Remove longest matching suffix."""
        if self._neg(pattern):
            from .extglob import extglob_fullmatch
            # Longest suffix removed = the smallest start index whose suffix
            # matches the pattern.
            for i in range(len(value) + 1):
                if extglob_fullmatch(pattern, value[i:]):
                    return value[:i]
            return value
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=True, from_start=False, extglob_enabled=self._extglob)
        # Convert to end-anchored regex
        regex = regex.rstrip('$') + '$'

        # Find longest match from end
        for i in range(len(value) + 1):
            if re.match(regex, value[i:]):
                return value[:i]
        return value

    # Pattern substitution
    def substitute_first(self, value: str, pattern: str,
                         replacement: Union[str, list]) -> str:
        """Replace first match."""
        ic = self._nocasematch
        if self._neg(pattern):
            from .extglob import extglob_match_at
            n = len(value)
            for p in range(n + 1):
                length = extglob_match_at(pattern, value, p, ignorecase=ic)
                if length is not None and not (length == 0 and p == n):
                    return (value[:p]
                            + self.render_replacement(replacement, value[p:p + length])
                            + value[p + length:])
            return value
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=False, extglob_enabled=self._extglob)
        return re.sub(regex,
                      lambda m: self.render_replacement(replacement, m.group(0)),
                      value, count=1, flags=re.IGNORECASE if ic else 0)

    def substitute_all(self, value: str, pattern: str,
                       replacement: Union[str, list]) -> str:
        """Replace all matches."""
        ic = self._nocasematch
        if self._neg(pattern):
            return self._substitute_all_negation(value, pattern, replacement, ic)
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=False, extglob_enabled=self._extglob)
        compiled = re.compile(regex, re.IGNORECASE if ic else 0)
        # Patterns that can match the empty string (e.g. extglob *(q), ?(q))
        # need bash's empty-match semantics: Python's re.sub emits an extra
        # zero-width match at end-of-string where bash does not
        # (${v//*(q)/-} on "xyz" → "-x-y-z", not "-x-y-z-"). Only the
        # zero-width-capable case takes the manual scan; ordinary patterns
        # keep the fast re.sub path unchanged.
        if compiled.match('') is not None:
            return self._substitute_all_empty_aware(compiled, value, replacement)
        return compiled.sub(
            lambda m: self.render_replacement(replacement, m.group(0)),
            value)

    def _substitute_all_empty_aware(self, compiled, value: str,
                                    replacement: Union[str, list]) -> str:
        """Global substitution with bash empty-match semantics.

        Scans left to right matching at each position (longest match), and
        suppresses a zero-width match at the very end of a non-empty string —
        the one place Python's re.sub diverges from bash for patterns that
        can match empty.
        """
        out: List[str] = []
        pos = 0
        n = len(value)
        while pos <= n:
            m = compiled.match(value, pos)
            if m and m.end() > pos:
                out.append(self.render_replacement(replacement, m.group(0)))
                pos = m.end()
            elif m and not (pos == n and n > 0):
                # zero-width match, allowed (not the suppressed end-of-string
                # match of a non-empty subject)
                out.append(self.render_replacement(replacement, ''))
                if pos < n:
                    out.append(value[pos])
                pos += 1
            else:
                if pos < n:
                    out.append(value[pos])
                pos += 1
        return ''.join(out)

    def _substitute_all_negation(self, value: str, pattern: str,
                                 replacement: Union[str, list],
                                 ignorecase: bool = False) -> str:
        """Global substitution for negation patterns (matcher, not regex).

        Same left-to-right, leftmost-longest, empty-match-suppressed-at-end
        semantics as ``_substitute_all_empty_aware``, but using the extglob
        backtracking matcher because negation can't be a regex.
        """
        from .extglob import extglob_match_at
        out: List[str] = []
        pos = 0
        n = len(value)
        while pos < n:
            length = extglob_match_at(pattern, value, pos, ignorecase=ignorecase)
            if length is None:
                out.append(value[pos])
                pos += 1
            elif length == 0:
                out.append(self.render_replacement(replacement, ''))
                out.append(value[pos])
                pos += 1
            else:
                out.append(self.render_replacement(replacement, value[pos:pos + length]))
                pos += length
        return ''.join(out)

    def substitute_prefix(self, value: str, pattern: str,
                          replacement: Union[str, list]) -> str:
        """Replace prefix match."""
        ic = self._nocasematch
        if self._neg(pattern):
            from .extglob import extglob_match_at
            length = extglob_match_at(pattern, value, 0, ignorecase=ic)
            if length is not None:
                return (self.render_replacement(replacement, value[:length])
                        + value[length:])
            return value
        # Anchor at the START only: re.match already anchors at position 0, so
        # the unanchored body matches a prefix. (An end-anchored regex — which
        # the extglob converter would produce for from_start=True — wrongly
        # demanded a full-string match, so /# behaved like a whole-value match.)
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=False, extglob_enabled=self._extglob)
        match = re.match(regex, value, re.IGNORECASE if ic else 0)
        if match:
            return (self.render_replacement(replacement, match.group(0))
                    + value[match.end():])
        return value

    def substitute_suffix(self, value: str, pattern: str,
                          replacement: Union[str, list]) -> str:
        """Replace suffix match."""
        ic = self._nocasematch
        if self._neg(pattern):
            from .extglob import extglob_fullmatch
            # Longest suffix that matches = smallest start index.
            for i in range(len(value) + 1):
                if extglob_fullmatch(pattern, value[i:], ignorecase=ic):
                    return (value[:i]
                            + self.render_replacement(replacement, value[i:]))
            return value
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=True, from_start=False, extglob_enabled=self._extglob)
        # Convert to end-anchored regex
        regex = regex.rstrip('$') + '$'

        # Find match at end
        match = re.search(regex, value, re.IGNORECASE if ic else 0)
        if match:
            return (value[:match.start()]
                    + self.render_replacement(replacement, match.group(0)))
        return value

    # Substring extraction
    def extract_substring(self, value: str, offset: int, length: Optional[int] = None) -> str:
        """Extract substring with offset and optional length."""
        # Handle negative offset
        if offset < 0:
            # Negative offset counts from end. If it is still negative after
            # adjusting, bash yields the empty string (not the whole value).
            offset = len(value) + offset
            if offset < 0:
                return ''

        # Handle out of bounds
        if offset >= len(value):
            return ''

        if length is None:
            # No length specified, return from offset to end
            return value[offset:]
        else:
            # Handle negative length
            if length < 0:
                # Negative length means "up to N chars from the end". If the
                # endpoint falls before the offset, bash treats it as an error
                # (e.g. `${x:0:-5}` on a short string).
                end = len(value) + length
                if end < offset:
                    raise ValueError(f"{length}: substring expression < 0")
                return value[offset:end]
            else:
                # Normal positive length
                return value[offset:offset + length]

    # Variable name matching
    def match_variable_names(self, prefix: str) -> List[str]:
        """Find all variable names starting with prefix (for ${!prefix@})."""
        # Get all variables from both shell variables and environment
        all_vars = set(self.state.variables.keys()) | set(self.state.env.keys())

        # Filter by prefix
        return sorted([var for var in all_vars if var.startswith(prefix)])

    # Case modification. bash matches the pattern against individual
    # characters: ${v^^pat} examines each char, ${v^pat} only the first.
    def _char_matches(self, char: str, pattern: str) -> bool:
        if self._neg(pattern):
            from .extglob import extglob_fullmatch
            return extglob_fullmatch(pattern, char)
        regex = self.pattern_matcher.shell_pattern_to_regex(
            pattern, anchored=False, extglob_enabled=self._extglob)
        return re.fullmatch(regex, char) is not None

    def uppercase_first(self, value: str, pattern: str = '?') -> str:
        """Uppercase the first char if it matches the pattern."""
        if value and self._char_matches(value[0], pattern):
            return value[0].upper() + value[1:]
        return value

    def uppercase_all(self, value: str, pattern: str = '?') -> str:
        """Uppercase every char matching the pattern."""
        return ''.join(c.upper() if self._char_matches(c, pattern) else c
                       for c in value)

    def lowercase_first(self, value: str, pattern: str = '?') -> str:
        """Lowercase the first char if it matches the pattern."""
        if value and self._char_matches(value[0], pattern):
            return value[0].lower() + value[1:]
        return value

    def lowercase_all(self, value: str, pattern: str = '?') -> str:
        """Lowercase every char matching the pattern."""
        return ''.join(c.lower() if self._char_matches(c, pattern) else c
                       for c in value)
