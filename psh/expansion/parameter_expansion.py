"""Advanced parameter expansion operations.

String operations behind the ``${var<op>...}`` operators (pattern removal,
substitution, substring, case modification, name matching). Parsing of the
``${...}`` syntax itself lives in param_parser.py.

Every pattern operator here routes through the ONE compiled pattern engine
(``pattern_engine``) and its four relations — ``matching_ends`` (prefix
removal), ``matching_starts`` (suffix removal), ``span_at`` / ``matching_spans``
(substitution), and ``full_match`` (case modification). No operator builds a
regex or does its own anchoring; plain globs and extglob share one linear,
memoized matcher (#20 H7), so a plain ``${x##*a*a…*b}`` can no longer backtrack
exponentially and semantics cannot drift from ``case`` / ``[[ == ]]``.
"""
from typing import TYPE_CHECKING, List, Optional, Union

from .pattern_engine import STRING, CompiledPattern, PatternCompiler, string_profile

if TYPE_CHECKING:
    from ..shell import Shell

# Sentinel marking "the matched text" in a prepared replacement template
# (bash 5.2 patsub_replacement: an unquoted & in the replacement).
PATSUB_MATCH = object()


class ParameterExpansionOps:
    """Advanced parameter expansion operations.

    The string-operation *engine* behind the ``${...}`` operators, named to
    disambiguate it from the ``ParameterExpansion`` **AST node**
    (``ast_nodes/words.py``) whose operator/word it evaluates.
    """

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

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

    def _compile(self, pattern: str) -> CompiledPattern:
        """Compile a (glob-escaped) operand pattern string ONCE.

        The pattern operand string carries quoted/escaped text as backslash
        escapes (``operands.glob_escape``), so ``\\`` is an escape here — the raw
        ``compile`` entry. The compiled pattern is reused across every position
        the operator scans."""
        return PatternCompiler.compile(pattern, extglob=self._extglob)

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

        The one negation-specific behaviour left after the engine unification:
        bash's substitution never emits an end-of-subject zero-width match for a
        negation pattern (``${x//!(x)/-}`` on '' -> ''), even on an empty
        subject, while non-negation forms do (``${x//*(q)/-}`` on '' -> '-').
        """
        if not self._extglob:
            return False
        from .extglob import _contains_negation
        return _contains_negation(pattern)

    # ---- Pattern removal: matching_ends (prefix) / matching_starts (suffix).
    # Removal is always case-SENSITIVE (bash): the STRING profile.

    def remove_shortest_prefix(self, value: str, pattern: str) -> str:
        """Remove shortest matching prefix (``${v#pat}``)."""
        ends = self._compile(pattern).matching_ends(value, 0, STRING)
        return value[min(ends):] if ends else value

    def remove_longest_prefix(self, value: str, pattern: str) -> str:
        """Remove longest matching prefix (``${v##pat}``)."""
        ends = self._compile(pattern).matching_ends(value, 0, STRING)
        return value[max(ends):] if ends else value

    def remove_shortest_suffix(self, value: str, pattern: str) -> str:
        """Remove shortest matching suffix (``${v%pat}``).

        Shortest suffix = the LARGEST start index whose suffix matches."""
        starts = self._compile(pattern).matching_starts(value, len(value), STRING)
        return value[:max(starts)] if starts else value

    def remove_longest_suffix(self, value: str, pattern: str) -> str:
        """Remove longest matching suffix (``${v%%pat}``).

        Longest suffix = the SMALLEST start index whose suffix matches."""
        starts = self._compile(pattern).matching_starts(value, len(value), STRING)
        return value[:min(starts)] if starts else value

    # ---- Pattern substitution: span_at / matching_spans (leftmost-longest).

    def substitute_first(self, value: str, pattern: str,
                         replacement: Union[str, list]) -> str:
        """Replace first match (``${v/pat/repl}``)."""
        profile = string_profile(self._nocasematch)
        compiled = self._compile(pattern)
        n = len(value)
        # A zero-width match at end-of-subject is dropped for negation !(x) but
        # emitted for *(x)/plain *; only negation suppresses it.
        suppress_end_empty = self._neg(pattern)
        for p in range(n + 1):
            length = compiled.span_at(value, p, profile)
            if length is None:
                continue
            if length == 0 and p == n and suppress_end_empty:
                continue
            return (value[:p]
                    + self.render_replacement(replacement, value[p:p + length])
                    + value[p + length:])
        return value

    def substitute_all(self, value: str, pattern: str,
                       replacement: Union[str, list]) -> str:
        """Replace all matches (``${v//pat/repl}``)."""
        profile = string_profile(self._nocasematch)
        compiled = self._compile(pattern)
        return self._substitute_scan(
            value, replacement,
            lambda pos: compiled.span_at(value, pos, profile),
            negation=self._neg(pattern))

    def _substitute_scan(self, value: str, replacement: Union[str, list],
                         match_at, *, negation: bool = False) -> str:
        """One left-to-right global-substitution scan (all ``//`` paths).

        ``match_at(pos)`` returns the leftmost-LONGEST match length at ``pos``
        (0 for a zero-width match, ``None`` for no match) — the engine's
        ``span_at`` relation for plain globs AND extglob (with or without
        negation), so there is one scanner behind every substitution.

        ``negation`` selects the sole behavioural difference between the paths:
        the end-of-subject zero-width policy (bash). The non-negation forms
        suppress a zero-width match at the very end of a NON-empty subject but
        still emit one on an EMPTY subject (``${x//*(q)/-}`` on '' -> '-');
        negation suppresses the end-of-subject empty match ALWAYS, even on an
        empty subject (``${x//!(x)/-}`` on '' -> '').
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

    def substitute_prefix(self, value: str, pattern: str,
                          replacement: Union[str, list]) -> str:
        """Replace an anchored prefix match (``${v/#pat/repl}``)."""
        profile = string_profile(self._nocasematch)
        length = self._compile(pattern).span_at(value, 0, profile)
        if length is not None:
            return (self.render_replacement(replacement, value[:length])
                    + value[length:])
        return value

    def substitute_suffix(self, value: str, pattern: str,
                          replacement: Union[str, list]) -> str:
        """Replace an anchored suffix match (``${v/%pat/repl}``).

        Longest matching suffix = the SMALLEST start index whose suffix matches
        (``matching_starts`` min)."""
        profile = string_profile(self._nocasematch)
        starts = self._compile(pattern).matching_starts(value, len(value), profile)
        if starts:
            i = min(starts)
            return (value[:i]
                    + self.render_replacement(replacement, value[i:]))
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
        character via the engine's ``full_match`` relation (case modification is
        case-SENSITIVE, so the STRING profile). Compiling once and reusing the
        closure keeps ``${v^^pat}`` on a long value O(len) matches, not O(len)
        compiles.
        """
        compiled = self._compile(pattern)
        return lambda ch: compiled.full_match(ch, STRING)

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
