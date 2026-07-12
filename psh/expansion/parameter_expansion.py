"""Advanced parameter expansion operations.

String operations behind the ``${var<op>...}`` operators (pattern removal,
substitution, substring, case modification, name matching). Parsing of the
``${...}`` syntax itself lives in param_parser.py.
"""
import re
from typing import TYPE_CHECKING, List, Optional, Union

# Case mapping for ^ ^^ , ,, ~ ~~ routes through the locale service
# (self.state.locale.upper/lower/toggle): length-safe AND locale-gated.
# Canonical pattern engine lives in pattern.py; re-exported here because
# many call sites import PatternMatcher from this module.
from .pattern import PatternMatcher

if TYPE_CHECKING:
    from ..shell import Shell

# Sentinel marking "the matched text" in a prepared replacement template
# (bash 5.2 patsub_replacement: an unquoted & in the replacement).
PATSUB_MATCH = object()


def _end_anchored(regex: str) -> str:
    """Append the true-end-of-string anchor ``\\Z`` to *regex* (idempotent).

    NOT ``$``: ``$`` also matches just before a *trailing newline*, so an
    end-anchored prefix/suffix regex built with ``$`` over-matches a subject
    that ends in ``\\n`` — ``${x%b}`` on ``$'ab\\n'`` must NOT strip the ``b``
    (there is no ``b`` at the real end of the string). The shared glob→regex
    converter (``extglob.extglob_to_regex``) already ends an anchored body with
    ``\\Z``; a plain-glob body (``glob_to_regex_body``) is unanchored, so this
    adds exactly one ``\\Z``. Unlike the former ``rstrip('$') + '$'`` shaping it
    never disturbs a literal ``\\$`` (an escaped ``$``) inside the body.
    """
    return regex if regex.endswith(r'\Z') else regex + r'\Z'


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
        """Whether *pattern* contains an extglob negation ``!(...)`` group.

        Standalone OR embedded (``${v#x!(o)}``, ``${v/a!(b)c/r}``). Retained for
        the two operators whose behaviour is negation-*specific*: case-modifier
        single-char matching (``_char_matches``) and the empty-match suppression
        in ``substitute_first``. Prefix/suffix removal and substitution route on
        ``_use_matcher`` (any extglob group) instead — see below.
        """
        if not self._extglob:
            return False
        from .extglob import _contains_negation
        return _contains_negation(pattern)

    def _use_matcher(self, pattern: str) -> bool:
        """Whether an operator must use the compiled engine rather than a regex.

        True for ANY extglob group (negation or alternation) when extglob is on.
        Two independent reasons the regex path is wrong or dangerous here:

        * **Correctness:** the unanchored substitution operators need the
          leftmost match's LONGEST extent, but Python ``re`` alternation is
          leftmost-*match* — ``${v/#@(a|aa)/Z}`` on ``aaX`` gives ``ZaX`` not
          ``ZX``. The engine enumerates every reachable end index and takes the
          max (POSIX leftmost-longest).
        * **Complexity:** ambiguous repetition with a forced-fail tail
          (``${v##*(a|aa)c}``) makes the regex backtrack catastrophically
          (seconds at ~40 chars); the memoized engine is linear-state.

        So prefix/suffix REMOVAL and all SUBSTITUTION operators route any extglob
        group through the engine; plain globs keep the fast regex path.
        """
        if not self._extglob:
            return False
        from .extglob import contains_extglob
        return contains_extglob(pattern)

    # Pattern removal
    def _prefix_match_regex(self, pattern: str):
        """Compiled regex that FULL-matches a candidate prefix.

        Mirrors the suffix path's ``\\Z`` shaping but anchors at the START: the
        result must match an entire candidate prefix so the position scan below
        can pick the shortest / longest matching prefix. Using a per-prefix full
        match (rather than one greedy/non-greedy pass over the whole value)
        makes extglob quantifiers behave correctly — the old ``.*`` → ``.*?``
        rewrite never touched ``+(o)``/``*(o)`` and the extglob converter
        additionally anchored the pattern, so ``#`` behaved like ``##``.
        """
        regex = self.pattern_matcher.shell_pattern_to_regex(
            pattern, anchored=True, from_start=True,
            extglob_enabled=self._extglob)
        # Anchor the END too (``\Z``, not ``$``) so the regex matches a WHOLE
        # candidate prefix: the extglob converter already appends ``\Z``; the
        # plain-glob path does not — _end_anchored normalises both.
        return re.compile(_end_anchored(regex))

    def remove_shortest_prefix(self, value: str, pattern: str) -> str:
        """Remove shortest matching prefix."""
        if self._use_matcher(pattern):
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
        if self._use_matcher(pattern):
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
        if self._use_matcher(pattern):
            from .extglob import extglob_fullmatch
            # Shortest suffix removed = the largest start index whose suffix
            # matches the pattern.
            for i in range(len(value), -1, -1):
                if extglob_fullmatch(pattern, value[i:]):
                    return value[:i]
            return value
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=True, from_start=False, extglob_enabled=self._extglob)
        # Convert to end-anchored regex (``\Z``: a real end-of-string, so a
        # trailing newline in *value* is not treated as a suffix boundary),
        # compiled ONCE — the scan below matches at every position.
        compiled = re.compile(_end_anchored(regex))

        # Find shortest match from end
        for i in range(len(value), -1, -1):
            if compiled.match(value[i:]):
                return value[:i]
        return value

    def remove_longest_suffix(self, value: str, pattern: str) -> str:
        """Remove longest matching suffix."""
        if self._use_matcher(pattern):
            from .extglob import extglob_fullmatch
            # Longest suffix removed = the smallest start index whose suffix
            # matches the pattern.
            for i in range(len(value) + 1):
                if extglob_fullmatch(pattern, value[i:]):
                    return value[:i]
            return value
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=True, from_start=False, extglob_enabled=self._extglob)
        # Convert to end-anchored regex (``\Z``: a real end-of-string, so a
        # trailing newline in *value* is not treated as a suffix boundary),
        # compiled ONCE — the scan below matches at every position.
        compiled = re.compile(_end_anchored(regex))

        # Find longest match from end
        for i in range(len(value) + 1):
            if compiled.match(value[i:]):
                return value[:i]
        return value

    # Pattern substitution
    def substitute_first(self, value: str, pattern: str,
                         replacement: Union[str, list]) -> str:
        """Replace first match."""
        ic = self._nocasematch
        if self._use_matcher(pattern):
            from .extglob import extglob_match_at
            n = len(value)
            # A zero-width match at end-of-subject (i.e. an empty value) is
            # dropped by bash for negation !(x) but emitted for *(x)/plain *;
            # only negation suppresses it. (bash's separate suppression of the
            # empty match for ?(x) on an empty value is a per-quantifier quirk
            # not derivable from the extent; the plain-regex path diverged there
            # too — left as-is.)
            suppress_end_empty = self._neg(pattern)
            for p in range(n + 1):
                length = extglob_match_at(pattern, value, p, ignorecase=ic)
                if length is None:
                    continue
                if length == 0 and p == n and suppress_end_empty:
                    continue
                return (value[:p]
                        + self.render_replacement(replacement, value[p:p + length])
                        + value[p + length:])
            return value
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=False, extglob_enabled=self._extglob, ignorecase=ic)
        return re.sub(regex,
                      lambda m: self.render_replacement(replacement, m.group(0)),
                      value, count=1, flags=re.IGNORECASE if ic else 0)

    def substitute_all(self, value: str, pattern: str,
                       replacement: Union[str, list]) -> str:
        """Replace all matches."""
        ic = self._nocasematch
        if self._neg(pattern):
            return self._substitute_all_negation(value, pattern, replacement, ic)
        if self._use_matcher(pattern):
            # Non-negation extglob: the matcher gives leftmost-LONGEST extents
            # (Python re alternation is leftmost-match). Empty-match semantics
            # match the regex empty-aware scan used for plain globs below.
            return self._substitute_all_matcher(value, pattern, replacement, ic)
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=False, extglob_enabled=self._extglob, ignorecase=ic)
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

    def _substitute_scan(self, value: str, replacement: Union[str, list],
                         match_at, *, negation: bool = False) -> str:
        """One left-to-right global-substitution scan (all three ``//`` paths).

        ``match_at(pos)`` returns the leftmost-LONGEST match length at ``pos``
        (0 for a zero-width match, ``None`` for no match); the backend — regex
        for plain globs, the compiled engine for extglob (with or without
        negation) — is entirely behind that callable.

        ``negation`` selects the sole behavioural difference between the paths:
        the end-of-subject zero-width policy (bash). The non-negation forms
        suppress a zero-width match at the very end of a NON-empty subject but
        still emit one on an EMPTY subject (``${x//*(q)/-}`` on '' -> '-');
        negation suppresses the end-of-subject empty match ALWAYS, even on an
        empty subject (``${x//!(x)/-}`` on '' -> '') — the old
        ``_substitute_all_negation`` encoded this with a ``pos < n`` bound
        instead of ``pos <= n``.
        """
        out: List[str] = []
        pos = 0
        n = len(value)
        while pos <= n:
            length = match_at(pos)
            if length is not None and length > 0:
                out.append(self.render_replacement(
                    replacement, value[pos:pos + length]))
                pos += length
            elif length is not None and not (pos == n and (negation or n > 0)):
                # Zero-width match, allowed: NOT the suppressed end-of-subject
                # match (suppressed for a non-empty subject, and — for negation
                # — even for an empty subject).
                out.append(self.render_replacement(replacement, ''))
                if pos < n:
                    out.append(value[pos])
                pos += 1
            else:
                if pos < n:
                    out.append(value[pos])
                pos += 1
        return ''.join(out)

    def _substitute_all_empty_aware(self, compiled, value: str,
                                    replacement: Union[str, list]) -> str:
        """Global substitution with bash empty-match semantics (regex backend).

        The plain-glob path: patterns that can match empty (``*(q)`` after
        conversion, ``x*``) need bash's zero-width policy, which Python's
        re.sub gets wrong at end-of-subject. Delegates to ``_substitute_scan``
        with a regex ``match_at``.
        """
        def match_at(pos: int):
            m = compiled.match(value, pos)
            return (m.end() - pos) if m else None
        return self._substitute_scan(value, replacement, match_at)

    def _substitute_all_matcher(self, value: str, pattern: str,
                                replacement: Union[str, list],
                                ignorecase: bool = False) -> str:
        """Global substitution for non-negation extglob patterns.

        Uses the extglob backtracking matcher (``extglob_match_at`` →
        leftmost-longest extent) rather than a regex, because Python ``re``
        alternation is leftmost-*match* (``${v//@(a|aa)/Z}`` on ``aaX`` must
        give ``ZX`` not ``ZaX``). The scan and empty-match policy are shared
        with the plain-glob regex path via ``_substitute_scan``.
        """
        from .extglob import extglob_match_at
        return self._substitute_scan(
            value, replacement,
            lambda pos: extglob_match_at(pattern, value, pos,
                                         ignorecase=ignorecase))

    def _substitute_all_negation(self, value: str, pattern: str,
                                 replacement: Union[str, list],
                                 ignorecase: bool = False) -> str:
        """Global substitution for negation patterns (matcher, not regex).

        Same left-to-right, leftmost-longest scan as the other two forms via
        ``_substitute_scan``, with ``negation=True`` selecting bash's rule that
        negation never emits an end-of-subject empty match (even on an empty
        subject). Negation can't be a regex, so it uses the extglob matcher.
        """
        from .extglob import extglob_match_at
        return self._substitute_scan(
            value, replacement,
            lambda pos: extglob_match_at(pattern, value, pos,
                                         ignorecase=ignorecase),
            negation=True)

    def substitute_prefix(self, value: str, pattern: str,
                          replacement: Union[str, list]) -> str:
        """Replace prefix match."""
        ic = self._nocasematch
        if self._use_matcher(pattern):
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
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=False, extglob_enabled=self._extglob, ignorecase=ic)
        match = re.match(regex, value, re.IGNORECASE if ic else 0)
        if match:
            return (self.render_replacement(replacement, match.group(0))
                    + value[match.end():])
        return value

    def substitute_suffix(self, value: str, pattern: str,
                          replacement: Union[str, list]) -> str:
        """Replace suffix match."""
        ic = self._nocasematch
        if self._use_matcher(pattern):
            from .extglob import extglob_fullmatch
            # Any extglob group routes through the engine (like ${v/#}), not the
            # end-anchored regex below: ambiguous repetition (${v/%*(a|aa)c/R})
            # backtracks catastrophically there. Longest matching suffix =
            # smallest start index whose suffix fully matches.
            for i in range(len(value) + 1):
                if extglob_fullmatch(pattern, value[i:], ignorecase=ic):
                    return (value[:i]
                            + self.render_replacement(replacement, value[i:]))
            return value
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=True, from_start=False, extglob_enabled=self._extglob, ignorecase=ic)
        # Convert to end-anchored regex (``\Z``: a real end-of-string, so a
        # trailing newline in *value* is not treated as a suffix boundary).
        regex = _end_anchored(regex)

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
    def _char_predicate(self, pattern: str):
        """Compile a single-char match predicate for a case-mod pattern ONCE.

        The ``^ ^^ , ,, ~ ~~`` operators test the pattern against EVERY
        character; building the glob→regex conversion per character (the old
        per-call ``_char_matches``) was O(len(value)) conversions for a
        ``${v^^pat}`` on a long value. This converts/compiles the matcher a
        single time and returns a closure applied to each char (the ``_first``
        variants call it for one char — same result, negligible cost).
        """
        if self._neg(pattern):
            from .pattern_engine import compile_cached, fullmatch
            compiled = compile_cached(pattern)
            return lambda ch: fullmatch(compiled, ch)
        regex = self.pattern_matcher.shell_pattern_to_regex(
            pattern, anchored=False, extglob_enabled=self._extglob)
        compiled_re = re.compile(regex)
        return lambda ch: compiled_re.fullmatch(ch) is not None

    def _char_matches(self, char: str, pattern: str) -> bool:
        return self._char_predicate(pattern)(char)

    # ^ ^^ , ,, ~ ~~ route their per-char case mapping through the locale
    # service: length-safe (ß stays ß) AND locale-gated (ASCII-only under the C
    # locale, Unicode under UTF-8) — see LocaleService.upper/lower/toggle.
    def uppercase_first(self, value: str, pattern: str = '?') -> str:
        """Uppercase the first char if it matches the pattern."""
        if value and self._char_matches(value[0], pattern):
            return self.state.locale.upper(value[0]) + value[1:]
        return value

    def uppercase_all(self, value: str, pattern: str = '?') -> str:
        """Uppercase every char matching the pattern."""
        loc = self.state.locale
        matches = self._char_predicate(pattern)
        return ''.join(loc.upper(c) if matches(c) else c for c in value)

    def lowercase_first(self, value: str, pattern: str = '?') -> str:
        """Lowercase the first char if it matches the pattern."""
        if value and self._char_matches(value[0], pattern):
            return self.state.locale.lower(value[0]) + value[1:]
        return value

    def lowercase_all(self, value: str, pattern: str = '?') -> str:
        """Lowercase every char matching the pattern."""
        loc = self.state.locale
        matches = self._char_predicate(pattern)
        return ''.join(loc.lower(c) if matches(c) else c for c in value)

    def toggle_first(self, value: str, pattern: str = '?') -> str:
        """Toggle the case of the first char if it matches the pattern (${x~})."""
        if value and self._char_matches(value[0], pattern):
            return self.state.locale.toggle(value[0]) + value[1:]
        return value

    def toggle_all(self, value: str, pattern: str = '?') -> str:
        """Toggle the case of every char matching the pattern (${x~~})."""
        loc = self.state.locale
        matches = self._char_predicate(pattern)
        return ''.join(loc.toggle(c) if matches(c) else c for c in value)
