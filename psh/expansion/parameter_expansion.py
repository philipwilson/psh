"""Advanced parameter expansion operations.

String operations behind the ``${var<op>...}`` operators (pattern removal,
substitution, substring, case modification, name matching). Parsing of the
``${...}`` syntax itself lives in param_parser.py.

Every pattern operator here routes through the ONE compiled pattern engine
(``pattern_engine``) and its four relations — ``matching_ends`` (prefix
removal), ``matching_starts`` (suffix removal), ``span_at`` / ``spanner``
(substitution), and ``full_match`` (case modification). No operator builds a
regex or does its own anchoring; plain globs and extglob share one linear,
memoized matcher (#20 H7), so a plain ``${x##*a*a…*b}`` can no longer backtrack
exponentially and semantics cannot drift from ``case`` / ``[[ == ]]``.

Substitution additionally implements bash's MEASURED consumer layer (slot
3.1; bash-5.2 ``subst.c`` mechanics, corpus-pinned in
``test_pattern_bash_composition_differential.py``), which sits ON TOP of the
engine's slice booleans:

1. **empty-subject single-shot** (``pat_subst``): on an empty subject every
   form reduces to one match decision — one replacement or nothing;
2. **the pre-test** (``match_upattern``): the pattern is wrapped in
   anchor-dependent ``*``\\ s and full-matched against the (remaining)
   subject first; failure suppresses the whole operation. The wrapper
   inherits the star∘extglob composition rules, which is exactly how
   ``${v/%!(a)/Z}`` on ``a`` substitutes nothing in bash;
3. **the end-position gate** (``match_pattern_char``): a scan position with
   nothing left to read is eligible only if the pattern TEXT starts with a
   ``*`` (wildcard star or ``*(`` group — a char-level rule in bash);
4. **the global-replace loop never scans the end-of-subject position**
   (``pat_subst``'s ``while (*str)``).

Removal has NO consumer layer (pure slice booleans) — measured, same corpus.
"""
from functools import lru_cache
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

from ..core.exceptions import ExpansionError
from .pattern_engine import (
    STRING,
    CompiledPattern,
    PatternCompiler,
    string_profile,
    sub_fast_eligible,
)

if TYPE_CHECKING:
    from ..protocols import ExpansionHost, LocaleAccess

# Sentinel marking "the matched text" in a prepared replacement template
# (bash 5.2 patsub_replacement: an unquoted & in the replacement).
PATSUB_MATCH = object()


@lru_cache(maxsize=512)
def _sub_machinery_cached(pattern: str, anchor: str, extglob: bool
                          ) -> Tuple[CompiledPattern, CompiledPattern, bool,
                                     bool]:
    """Cached body of ``ParameterExpansionOps._sub_machinery`` (see it for
    the semantics; round-1 nit N3, round-2 B2-1/B2-2). Semantics-neutral
    memo: identical results for equal ``(pattern, anchor, extglob)`` keys;
    it amortizes wrapper construction — the dominant matching cost is
    unchanged (measured, slot ledger).

    The wrapper follows bash ``match_upattern``'s npat rules EXACTLY
    (subst.c; MEASURED on the slot's backslash-axis corpus, round 2):

    * OUTER GUARD — a RAW-CHAR test on both ends of the pattern TEXT:
      if the head is a raw ``*`` (not a ``*(`` group with extglob) AND the
      last char is a raw ``*`` — EVEN an escaped ``\\*`` — bash builds NO
      wrapper: the pre-test is the raw pattern itself, which is why
      ``${v/*a\\*/Z}`` substitutes nothing unless the subject full-matches
      the pattern (the round-2 45-cell family).
    * Otherwise npat is built as a STRING: ``*`` prepended unless
      (anchor 'beg', or raw-``*`` non-group head); ``*`` appended unless
      (anchor 'end', or the last char is a ``*`` that is NOT escaped by an
      ODD backslash run — an odd-escaped ``\\*`` tail DOES get the append).
      The string is then compiled, preserving bash's paren pun: prepending
      ``*`` to a ``(``-headed pattern forms a ``*(...)`` GROUP (measured:
      ``${v/%(a)/Z}`` on ``(a)`` substitutes nothing in bash because its
      pre-test parses as the group ``*(a)``).

    ``end_eligible`` is bash ``match_pattern_char``'s empty-position rule,
    also a RAW-CHAR test: the pattern TEXT begins with ``*`` (wildcard or
    ``*(`` group head both pass; an escaped ``\\*`` head fails).

    ``fast_ok`` (4th element) gates the Path-A linear fast path (round-2
    B2-2): the AST eligibility (``pattern_engine.sub_fast_eligible``) AND
    wrapper REDUNDANCY — two raw-char shapes make the pre-test a REAL
    suppressor that the fast path must not skip (found by the battery's
    own backslash rows): (a) the outer-guard case with an ODD-escaped
    ``\\*`` tail (the pre-test is the raw pattern, a full-match
    constraint), and (b) a ``(``-headed pattern under extglob (the
    string-built wrapper's paren pun). Everything else reduces the
    pre-test to "a substring match exists" — proven by the corpus-union +
    backslash-axis equivalence measurements (0 disagreements)."""
    compiled = PatternCompiler.compile(pattern, extglob=extglob)
    end_eligible = pattern.startswith('*')
    head_raw_star = end_eligible and not (
        extglob and pattern[1:2] == '(')

    def _odd_escaped_star_tail() -> bool:
        if not pattern.endswith('*'):
            return False
        k = len(pattern) - 2
        nback = 0
        while k >= 0 and pattern[k] == '\\':
            nback += 1
            k -= 1
        return nback % 2 == 1

    fast_ok = (sub_fast_eligible(compiled.root)
               and not (head_raw_star and _odd_escaped_star_tail())
               and not (extglob and pattern.startswith('(')))
    if head_raw_star and pattern.endswith('*'):
        # outer guard: NO wrapper (the raw pattern is the pre-test)
        return compiled, compiled, end_eligible, fast_ok
    parts: List[str] = []
    if anchor != 'beg' and not head_raw_star:
        parts.append('*')
    parts.append(pattern)
    if anchor != 'end' and pattern:
        if pattern.endswith('*'):
            if _odd_escaped_star_tail():
                parts.append('*')  # odd-escaped \\* tail: literal, append
        else:
            parts.append('*')
    elif anchor != 'end' and not pattern:
        parts.append('*')
    wrap_str = ''.join(parts)
    if wrap_str == pattern:
        wrapped = compiled
    else:
        wrapped = PatternCompiler.compile(wrap_str, extglob=extglob)
    return compiled, wrapped, end_eligible, fast_ok


class ParameterExpansionOps:
    """Advanced parameter expansion operations.

    The string-operation *engine* behind the ``${...}`` operators, named to
    disambiguate it from the ``ParameterExpansion`` **AST node**
    (``ast_nodes/words.py``) whose operator/word it evaluates.
    """

    def __init__(self, host: 'ExpansionHost') -> None:
        #: Narrowed from the whole ``Shell`` in remediation 5C.1. The field is
        #: kept (nothing outside reads it, but a dead-field sweep is 5C.2's
        #: subject, not this slot's) and renamed so it does not claim to hold
        #: a shell it no longer holds.
        self.host = host
        self.state = host.state

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

    # ---- Pattern substitution: the engine's slice booleans under bash's
    # measured consumer layer (module docstring, mechanisms 1-4; slot 3.1).

    def _sub_machinery(self, pattern: str, anchor: str
                       ) -> Tuple[CompiledPattern, CompiledPattern, bool,
                                  bool]:
        """Compile *pattern* plus its bash ``match_upattern`` machinery.

        Returns ``(compiled, wrapped, end_eligible, fast_ok)`` for
        ``anchor`` in ``'any'``/``'beg'``/``'end'``. The measured wrapper
        and gate rules — bash's RAW-CHAR outer guard on both pattern ends
        (no wrapper at all for a raw-``*``-head/raw-``*``-tail pattern,
        even when the tail star is escaped), the odd-backslash-escaped-tail
        append, the string-built wrapper with its ``(``-head paren pun, the
        raw-char empty-position gate, and the Path-A ``fast_ok`` gate —
        live on :func:`_sub_machinery_cached` (round-2 B2-1/B2-2)."""
        return _sub_machinery_cached(pattern, anchor, self._extglob)

    @staticmethod
    def _any_match_from(pre_test, span_at, end_eligible: bool, n: int,
                        pos: int) -> Optional[Tuple[int, int]]:
        """bash ``match_upattern`` MATCH_ANY on the suffix ``value[pos:]``,
        in ABSOLUTE coordinates: the ``(start, end)`` of the leftmost-longest
        ELIGIBLE match, or ``None``.

        Pre-test first (mechanism 2); then the leftmost scan, where the
        empty-remainder position ``n`` is gated by ``end_eligible``
        (mechanism 3). Longest-at-position is the engine's ``spanner``.

        This is the SINGLE body of the MATCH_ANY rule. ``pre_test`` and
        ``span_at`` are per-subject callables (``CompiledPattern.suffix_matcher``
        / ``.spanner``) built ONCE and reused across every scan position, so
        the global-replace loop no longer rebuilds a matcher — nor re-copies
        the subject — per remaining suffix."""
        if not pre_test(pos):
            return None
        limit = n + 1 if end_eligible else n
        for p in range(pos, limit):
            length = span_at(p)
            if length is not None:
                return (p, p + length)
        return None

    def _any_match(self, compiled: CompiledPattern, wrapped: CompiledPattern,
                   end_eligible: bool, value: str,
                   profile) -> Optional[Tuple[int, int]]:
        """MATCH_ANY on the whole of *value* — :meth:`_any_match_from` at
        position 0 (one rule, one body)."""
        return self._any_match_from(wrapped.suffix_matcher(value, profile),
                                    compiled.spanner(value, profile),
                                    end_eligible, len(value), 0)

    def substitute_first(self, value: str, pattern: str,
                         replacement: Union[str, list]) -> str:
        """Replace first match (``${v/pat/repl}``)."""
        profile = string_profile(self._nocasematch)
        compiled, wrapped, end_eligible, fast_ok = self._sub_machinery(
            pattern, 'any')
        if not compiled.root.elements:
            # Empty pattern: one zero-width match at position 0.
            return self.render_replacement(replacement, '') + value
        if fast_ok:
            return self._substitute_first_fast(value, compiled, replacement,
                                               profile)
        m = self._any_match(compiled, wrapped, end_eligible, value, profile)
        if m is None:
            return value
        s, e = m
        return (value[:s] + self.render_replacement(replacement, value[s:e])
                + value[e:])

    def _substitute_first_fast(self, value, compiled, replacement, profile):
        """Path-A linear scan for fast_ok patterns (see
        ``_sub_machinery_cached``): leftmost-longest match via one spanner —
        the bash machinery is vacuous/reducible on this class (corpus-union
        + backslash-axis equivalence proof: 0 disagreements)."""
        span_at = compiled.spanner(value, profile)
        for p in range(len(value) + 1):
            length = span_at(p)
            if length is not None:
                return (value[:p]
                        + self.render_replacement(replacement,
                                                  value[p:p + length])
                        + value[p + length:])
        return value

    def substitute_all(self, value: str, pattern: str,
                       replacement: Union[str, list]) -> str:
        """Replace all matches (``${v//pat/repl}``).

        bash's ``pat_subst`` loop: one MATCH_ANY per REMAINING SUFFIX (the
        pre-test and end gate apply per suffix), a zero-width match copies
        one character forward, and the loop runs only while characters
        remain — the end-of-subject position is never scanned on a
        non-empty subject (mechanism 4). An empty subject is the
        single-shot decision (mechanism 1). fast_ok patterns take the
        equivalent LINEAR scan instead."""
        profile = string_profile(self._nocasematch)
        compiled, wrapped, end_eligible, fast_ok = self._sub_machinery(
            pattern, 'any')
        if not compiled.root.elements:
            # Empty pattern: zero-width before every char (none at the end).
            rep = self.render_replacement(replacement, '')
            if not value:
                return rep
            return ''.join(rep + ch for ch in value)
        if fast_ok:
            return self._substitute_all_fast(value, compiled, replacement,
                                             profile)
        if not value:
            m = self._any_match(compiled, wrapped, end_eligible, '', profile)
            return self.render_replacement(replacement, '') if m else value
        out: List[str] = []
        n = len(value)
        pos = 0
        # ONE pre-test matcher and ONE spanner for the whole scan: bash's
        # mechanics are per-remaining-suffix, but the suffix is a WINDOW on
        # the subject, not a new string (measured identity — see
        # CompiledPattern.suffix_matcher). Rebuilding them per suffix cost an
        # O(n) copy and a discarded memo at every match.
        pre_test = wrapped.suffix_matcher(value, profile)
        span_at = compiled.spanner(value, profile)
        while pos < n:
            m = self._any_match_from(pre_test, span_at, end_eligible, n, pos)
            if m is None:
                break
            s, e = m
            out.append(value[pos:s])
            out.append(self.render_replacement(replacement, value[s:e]))
            if s == e:  # zero-width: copy one character to make progress
                out.append(value[e])
                e += 1
            pos = e
        out.append(value[pos:])
        return ''.join(out)

    def _substitute_all_fast(self, value, compiled, replacement, profile):
        """Path-A linear global scan for fast_ok patterns: one spanner,
        left-to-right leftmost-longest, zero-width advances by one and the
        end-of-subject empty match is emitted only on an EMPTY subject
        (the observable bash behaviour on this class — corpus-union +
        backslash-axis equivalence proof: 0 disagreements)."""
        span_at = compiled.spanner(value, profile)
        out: List[str] = []
        pos = 0
        n = len(value)
        while pos <= n:
            length = span_at(pos)
            if length is not None and length > 0:
                out.append(self.render_replacement(
                    replacement, value[pos:pos + length]))
                pos += length
            elif length is not None and not (pos == n and n > 0):
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
        compiled, wrapped, end_eligible, fast_ok = self._sub_machinery(
            pattern, 'beg')
        if not compiled.root.elements:
            # bash pat_subst special case 1: null pattern prefixes REP.
            return self.render_replacement(replacement, '') + value
        if fast_ok:
            length = compiled.span_at(value, 0, profile)
            if length is not None:
                return (self.render_replacement(replacement, value[:length])
                        + value[length:])
            return value
        if not wrapped.full_match(value, profile):
            return value
        if not value and not end_eligible:
            return value  # match_pattern_char gate at position 0 of ''
        length = compiled.span_at(value, 0, profile)
        if length is not None:
            return (self.render_replacement(replacement, value[:length])
                    + value[length:])
        return value

    def substitute_suffix(self, value: str, pattern: str,
                          replacement: Union[str, list]) -> str:
        """Replace an anchored suffix match (``${v/%pat/repl}``).

        Longest matching suffix = the SMALLEST start index whose suffix
        matches (``matching_starts`` min). No position gate (bash MATCH_END
        has none) — but the pre-test applies, with only the PREPENDED star
        (so ``${v/%!(a)/Z}`` on ``a`` is suppressed by the wrapped
        ``*!(a)`` failing, exactly as measured). fast_ok patterns skip the
        pre-test (equivalence-proven)."""
        profile = string_profile(self._nocasematch)
        compiled, wrapped, _end_eligible, fast_ok = self._sub_machinery(
            pattern, 'end')
        if not compiled.root.elements:
            # bash pat_subst special case 2: null pattern appends REP.
            return value + self.render_replacement(replacement, '')
        if not fast_ok:
            if not wrapped.full_match(value, profile):
                return value
        starts = compiled.matching_starts(value, len(value), profile)
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
                    # TYPED at the detection point (MEDIUM-12b): this is a
                    # user-syntax failure, not an internal defect, so it is an
                    # ExpansionError (discard-line family) rather than a bare
                    # ValueError the caller has to re-interpret. The callers
                    # (operators.py#_slice_scalar_subscript / the ':off:len'
                    # arm) own the location prefix and $?, so they print and
                    # re-raise; the message text is unchanged (bash parity).
                    raise ExpansionError(f"{length}: substring expression < 0")
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
            loc: 'LocaleAccess' = self.state.locale
            return loc.upper(value[0]) + value[1:]
        return value

    def uppercase_all(self, value: str, pattern: str = '?') -> str:
        """Uppercase every char matching the pattern."""
        loc: 'LocaleAccess' = self.state.locale
        matches = self._char_predicate(pattern)
        return ''.join(loc.upper(c) if matches(c) else c for c in value)

    def lowercase_first(self, value: str, pattern: str = '?') -> str:
        """Lowercase the first char if it matches the pattern."""
        if value and self._char_matches(value[0], pattern):
            loc: 'LocaleAccess' = self.state.locale
            return loc.lower(value[0]) + value[1:]
        return value

    def lowercase_all(self, value: str, pattern: str = '?') -> str:
        """Lowercase every char matching the pattern."""
        loc: 'LocaleAccess' = self.state.locale
        matches = self._char_predicate(pattern)
        return ''.join(loc.lower(c) if matches(c) else c for c in value)

    def toggle_first(self, value: str, pattern: str = '?') -> str:
        """Toggle the case of the first char if it matches the pattern (${x~})."""
        if value and self._char_matches(value[0], pattern):
            loc: 'LocaleAccess' = self.state.locale
            return loc.toggle(value[0]) + value[1:]
        return value

    def toggle_all(self, value: str, pattern: str = '?') -> str:
        """Toggle the case of every char matching the pattern (${x~~})."""
        loc: 'LocaleAccess' = self.state.locale
        matches = self._char_predicate(pattern)
        return ''.join(loc.toggle(c) if matches(c) else c for c in value)
