"""Compiled shell-pattern engine: one AST, parsed once, matched with memoization.

Historically psh matched shell patterns three ways, each wrong or fragile on a
different input (appraisal #6 and #20 H7):

* the **regex** backend (``extglob._convert_pattern`` → Python ``re``) blows up
  on ambiguous repetition with a forced-fail tail — ``*(a|aa)c`` on ``"a"*N+"b"``
  is catastrophic backtracking, and a plain ``*a*a…*b`` is exponential too;
* the **recursive backtracking matcher** re-parsed and fanned out exponentially;
* the compiled engine that replaced them recursed through every sequence
  element, so a ~1,500-literal pattern raised ``RecursionError``.

This module is the single relation for **every** consumer — ``case``,
``[[ == ]]``, ``${var#/%/##/%%}`` removal, ``${var/}`` substitution, case
modification, pathname components, and name filters (``HISTIGNORE``) — so glob /
extglob semantics cannot drift between them:

1. :func:`compile_pattern` (raw string, ``\\`` = escape) and
   :func:`PatternCompiler.compile_protected` (per-character ACTIVE/PROTECTED
   runs, consumed directly — the sole entry for quoted/escaped patterns) parse a
   shell glob/extglob pattern **once** into a small AST (:class:`Sequence` of
   :class:`Literal` / :class:`AnyChar` / :class:`Star` / :class:`Bracket` /
   :class:`Extglob`).
2. The matcher (:class:`_Matcher`) MEMOIZES each ``(sequence, element-index,
   subject-index)`` state, so adversarial repetition is ``O(nodes·positions)``,
   never exponential (#20 H7-c). A run of single-continuation nodes
   (``Literal``/``AnyChar``/``Bracket``) is consumed by an inner WHILE-loop, not
   recursion, so an arbitrarily long literal chain no longer raises
   ``RecursionError`` at the default limit (#20 H7-b); recursion depth is bounded
   by the number of ``Star``/``Extglob`` nodes actually traversed (the pattern's
   branch structure), well within psh's runtime limit. The reachable-end set
   natively serves the four relations :class:`CompiledPattern` exposes:
   ``full_match`` (short-circuiting), ``matching_ends`` (prefix removal),
   ``matching_starts`` (suffix removal), and ``span_at`` / ``matching_spans``
   (leftmost-longest substitution).

The compiled AST carries no locale or policy state: :class:`MatchProfile`
supplies ``for_pathname`` (whether ``*``/``?`` cross ``/``) and ``ic``
(``nocasematch``/``nocaseglob`` folding) at match time, so one compiled pattern
is reusable across contexts. Bracket membership still delegates to the shared,
locale-aware ``extglob._bracket_match`` (which resolves POSIX ``[:class:]`` via
the locale service), so class semantics are preserved byte-for-byte.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterator, List, Optional, Tuple, cast

# Reuse the scanning primitives AND the char-level predicates the legacy engine
# already shared, so the compiled engine cannot disagree with them on paren
# matching, alternative splitting, where a bracket expression ends, bracket
# membership (locale-aware POSIX classes), or case folding.
from .extglob import (
    _EXTGLOB_PREFIXES,
    _bracket_end,
    _bracket_match,
    _eq,
    _find_matching_paren,
    _split_pattern_list,
)

# --- AST node types --------------------------------------------------------
#
# Nodes are plain (mutable) dataclasses matched by object identity: the matcher
# memoizes on ``id(node)`` so each node created by one compile is a distinct
# state. ``eq=False`` keeps identity semantics and makes them hashable, which
# the round-trip tests and the matcher's memo rely on.

@dataclass(eq=False)
class Literal:
    """A single literal character (a plain char, or the target of a ``\\``)."""
    char: str


@dataclass(eq=False)
class AnyChar:
    """``?`` — matches exactly one character (not ``/`` when for_pathname)."""


@dataclass(eq=False)
class Star:
    """``*`` — matches zero or more characters (not ``/`` when for_pathname)."""


@dataclass(eq=False)
class Bracket:
    """``[...]`` — a bracket expression.

    ``content`` is the raw text between ``[`` and ``]`` (it may begin with
    ``!``/``^`` for negation and contain ``[:class:]`` names and ``\\``-escaped
    members). Membership is decided at match time by the shared, locale-aware
    ``extglob._bracket_match`` so POSIX-class / nocase / invalid-set semantics
    stay identical to the rest of the shell. A PROTECTED (quoted/escaped)
    class-special member is carried as a ``\\``-escaped char in ``content`` by
    :func:`PatternCompiler.compile_protected`, so ``[a"-"c]`` is the set
    ``{a,-,c}`` (a literal ``-``), not the range ``a-c`` (#20 H7 carry-2).
    """
    content: str


@dataclass(eq=False)
class Extglob:
    """An extended-glob group ``op(alt|alt|…)`` with ``op`` in ``?*+@!``.

    Each alternative is a fully compiled :class:`Sequence`. An empty group
    (``@()``) has a single empty-sequence alternative, matching bash.
    """
    op: str
    alts: Tuple["Sequence", ...]


@dataclass(eq=False)
class Sequence:
    """An ordered run of nodes; the compiled form of a whole pattern or one
    extglob alternative."""
    elements: Tuple[object, ...] = field(default_factory=tuple)


# --- compiler (raw string; ``\\`` is an escape) ----------------------------

def compile_pattern(pattern: str, *, extglob: bool = True,
                    for_pathname: bool = False) -> Sequence:
    """Parse a raw shell glob/extglob *pattern* string into a :class:`Sequence`.

    ``\\`` escapes the next character (standard glob string semantics — used for
    name filters and any consumer holding a raw pattern string). Quoted/escaped
    patterns whose protection is known per-character use
    :func:`PatternCompiler.compile_protected` instead.

    ``extglob`` False makes the prefixes ``?*+@!`` ordinary (only ``?`` and
    ``*`` keep their glob meaning). ``for_pathname`` is accepted for symmetry
    with the legacy API but is a match-time policy (it does not change the AST).
    """
    return _parse(pattern, 0, len(pattern), extglob)


def _parse(pattern: str, start: int, end: int, extglob: bool) -> Sequence:
    """Compile ``pattern[start:end]`` into a Sequence (``\\`` = escape)."""
    elements: List[object] = []
    i = start
    while i < end:
        ch = pattern[i]

        # Backslash escape: the next character is a literal.
        if ch == '\\' and i + 1 < end:
            elements.append(Literal(pattern[i + 1]))
            i += 2
            continue

        # Extglob operator: prefix in ?*+@! immediately followed by '('.
        if (extglob and ch in _EXTGLOB_PREFIXES and i + 1 < end
                and pattern[i + 1] == '('):
            close = _find_matching_paren(pattern, i + 1)
            if close is not None and close < end:
                inner = pattern[i + 2:close]
                alts = tuple(_parse_alt(a, extglob)
                             for a in _split_pattern_list(inner))
                elements.append(Extglob(ch, alts))
                i = close + 1
                continue
            # Unbalanced paren: the prefix char is a literal; reprocess '('.
            elements.append(Literal(ch))
            i += 1
            continue

        if ch == '*':
            elements.append(Star())
            i += 1
            continue
        if ch == '?':
            elements.append(AnyChar())
            i += 1
            continue
        if ch == '[':
            be = _bracket_end(pattern, i)
            if be is not None and be <= end:
                elements.append(Bracket(pattern[i + 1:be - 1]))
                i = be
                continue
            # Unterminated bracket: '[' is a literal.
            elements.append(Literal('['))
            i += 1
            continue

        elements.append(Literal(ch))
        i += 1

    return Sequence(tuple(elements))


def _parse_alt(alt: str, extglob: bool) -> Sequence:
    """Compile one extglob alternative (always with extglob enabled inside)."""
    return _parse(alt, 0, len(alt), extglob)


@lru_cache(maxsize=4096)
def compile_cached(pattern: str, extglob: bool = True) -> Sequence:
    """Memoized :func:`compile_pattern` for hot consumers (same pattern reused
    across a loop / many subjects)."""
    return compile_pattern(pattern, extglob=extglob)


# --- protection-direct compiler (per-character ACTIVE/PROTECTED runs) -------

#: Characters with glob/extglob significance SOMEWHERE (top level or inside a
#: bracket): the plain metacharacters, the extglob prefixes and grouping, and
#: the bracket-only specials ``-`` (range) / ``^`` (negation-at-start). A
#: PROTECTED occurrence of any of these must be ``\\``-escaped to become a
#: literal char / bracket member; every other character is already literal and
#: is left RAW — in particular ``/`` stays raw so a pathname pattern still
#: splits into components (a ``/`` is a separator regardless of quoting).
_GLOB_SIGNIFICANT = frozenset('*?[]()|@!+-^\\')


def runs_to_pattern_string(parts) -> str:
    """Normalize ``(text, protected)`` runs into ONE canonical pattern string.

    This is the single, correct protection encoding that replaces the two former
    ad-hoc ones (``word_expander._pattern_from_runs`` bracket-escaping and
    ``operands.glob_escape`` backslash-escaping): every glob-significant
    PROTECTED character is ``\\``-escaped so it is a literal char / bracket
    member wherever it appears (top level OR inside an active ``[...]`` — fixing
    #20 H7 carry-2), and an ACTIVE backslash is doubled so it stays a literal
    character (a residual ``\\`` reaching a pattern from an expansion is
    literal, as bash treats variable-value backslashes). ACTIVE glob
    metacharacters stay live. The result feeds :func:`compile_pattern`
    unchanged (``\\`` = escape), so all bracket / class / nesting handling is
    the one tested parser.
    """
    out: List[str] = []
    for text, protected in parts:
        if protected:
            for ch in text:
                if ch in _GLOB_SIGNIFICANT:
                    out.append('\\')
                out.append(ch)
        else:
            for ch in text:
                out.append('\\\\' if ch == '\\' else ch)
    return ''.join(out)


class PatternCompiler:
    """Compile a shell pattern into a :class:`CompiledPattern`.

    Two entry points, one AST:

    * :meth:`compile` — a raw pattern string (``\\`` = escape). Name filters and
      any consumer that only has a string.
    * :meth:`compile_protected` — per-character ACTIVE/PROTECTED runs, consumed
      directly. The sole entry for quoted/escaped patterns (pathname fields,
      ``${...}`` operands, ``case`` / ``[[ ]]`` word patterns), so a quoted
      metacharacter cannot glob and a quoted class-special character inside an
      active bracket stays a literal member.
    """

    @staticmethod
    def compile(pattern: str, *, extglob: bool = True) -> "CompiledPattern":
        return CompiledPattern(compile_cached(pattern, extglob))

    @staticmethod
    def compile_protected(parts, *, extglob: bool = True) -> "CompiledPattern":
        """Compile ``parts`` (a list of ``(text, protected)``) directly."""
        return CompiledPattern(
            compile_cached(runs_to_pattern_string(parts), extglob))


# --- match profile ---------------------------------------------------------

@dataclass(frozen=True)
class MatchProfile:
    """The match-time policy for one consumer (typed, not loose booleans).

    ``for_pathname`` — ``*``/``?``/``[`` and ``!(...)`` never cross ``/`` (the
    pathname consumer; slash-COMPONENT splitting and leading-dot policy are
    layered OVER the engine in ``glob.py``, never inside the matcher).
    ``ic`` — case-insensitive folding. The CALLER supplies it from the option
    that governs its consumer: ``nocasematch`` for ``case`` / ``[[ == ]]`` /
    substitution, ``nocaseglob`` for pathname, and always ``False`` for
    prefix/suffix removal, case modification, and name filters.
    """
    for_pathname: bool = False
    ic: bool = False


#: The plain string-matching profile (case / [[ ]] / removal / name filters).
STRING = MatchProfile(for_pathname=False, ic=False)
#: Case-insensitive string matching (nocasematch consumers).
STRING_IC = MatchProfile(for_pathname=False, ic=True)
#: One pathname component, case-sensitive.
PATHNAME = MatchProfile(for_pathname=True, ic=False)
#: One pathname component, case-insensitive (nocaseglob).
PATHNAME_IC = MatchProfile(for_pathname=True, ic=True)


def string_profile(ic: bool) -> MatchProfile:
    """String profile honoring *ic* (nocasematch)."""
    return STRING_IC if ic else STRING


def pathname_profile(ic: bool) -> MatchProfile:
    """Pathname-component profile honoring *ic* (nocaseglob)."""
    return PATHNAME_IC if ic else PATHNAME


# --- iterative matcher -----------------------------------------------------
#
# Reachable-end-position-set semantics: ``_reach(root, si)`` returns every index
# ``k`` such that the whole pattern fully matches ``s[si:k]``. This is the
# contract every consumer is built from:
#   * full match          -> len(s) in ends
#   * prefix removal (#/##) -> min/max of matching_ends
#   * suffix removal (%/%%) -> matching_starts (i where s[i:end] fully matches)
#   * leftmost-longest sub  -> span_at(pos) = max ends of s[pos:]
#   * pathname component    -> full_match(entry, for_pathname=True)
#
# The matcher MEMOIZES each ``(sequence, element-index, subject-index)`` state,
# so an adversarial repetition (``*(a|aa)c`` / plain ``*a*a…*b``) is
# O(nodes·positions), never the exponential backtracking of the old regex and
# recursive-backtracking backends (#20 H7-c). A consecutive run of
# single-continuation nodes (``Literal``/``AnyChar``/``Bracket``) is consumed by
# an inner WHILE-loop rather than by recursion, so a pattern that is a long
# literal chain (thousands of characters) can no longer raise ``RecursionError``
# at the default limit (#20 H7-b): recursion depth is bounded by the number of
# ``Star``/``Extglob`` nodes actually traversed (the pattern's branch structure),
# not by the subject or pattern length. ``fp`` (for_pathname) and ``ic`` are
# constant for one match, so they live on the Matcher rather than in the memo
# key. Memo keys use ``id(node)`` (nodes live for the whole match), and the
# node object is held in the frozen AST so the id stays valid.


class _Matcher:
    """One reachable-position match of a compiled pattern against one subject.

    A fresh instance (and memo) is created per match call. ``states`` counts
    distinct evaluated sequence states (memo misses) — the polynomial-complexity
    guard the tests assert on.
    """

    __slots__ = ("s", "n", "fp", "ic", "memo", "_fmemo", "states")

    def __init__(self, s: str, for_pathname: bool, ic: bool) -> None:
        self.s = s
        self.n = len(s)
        self.fp = for_pathname
        self.ic = ic
        self.memo: dict = {}
        self._fmemo: dict = {}
        self.states = 0

    def reach(self, seq: Sequence, si: int) -> frozenset:
        """Reachable end indices matching all of ``seq`` from ``s[si]``."""
        return self._match(seq, 0, si)

    def full_reaches(self, seq: Sequence, si: int) -> bool:
        """Whether ``seq`` matches EXACTLY ``s[si:n]`` — a short-circuiting
        boolean for the ``full_match`` consumers (case / [[ ]] / name filters /
        pathname component / one case-mod char), which do not need the whole
        reachable-end set. Memoized on ``(node, ei, si)`` so it stays polynomial
        on adversarial input, but returns True at the first success."""
        return self._full(seq, 0, si)

    def _full(self, seq: Sequence, ei: int, si: int) -> bool:
        key = (id(seq), ei, si)
        cached = self._fmemo.get(key)
        if cached is not None:
            return cached
        self.states += 1
        elements = seq.elements
        ne = len(elements)
        s, n, fp, ic = self.s, self.n, self.fp, self.ic
        while ei < ne:
            node = elements[ei]
            t = type(node)
            if t is Literal:
                ok = (si < n and (not fp or s[si] != '/')
                      and _eq(s[si], cast(Literal, node).char, ic))
            elif t is AnyChar:
                ok = si < n and (not fp or s[si] != '/')
            elif t is Bracket:
                ok = (si < n and (not fp or s[si] != '/')
                      and _bracket_match(cast(Bracket, node).content, s[si], ic))
            else:
                break
            if not ok:
                self._fmemo[key] = False
                return False
            ei += 1
            si += 1
        if ei == ne:
            result = si == n
        elif type(elements[ei]) is Star:
            result = False
            end = si
            while True:
                if self._full(seq, ei + 1, end):
                    result = True
                    break
                if end >= n or (fp and s[end] == '/'):
                    break
                end += 1
        else:  # Extglob
            result = False
            for mid in self._element_ends(cast(Extglob, elements[ei]), si):
                if self._full(seq, ei + 1, mid):
                    result = True
                    break
        self._fmemo[key] = result
        return result

    def _match(self, seq: Sequence, ei: int, si: int) -> frozenset:
        """Reachable end indices matching ``seq.elements[ei:]`` from ``s[si]``."""
        key = (id(seq), ei, si)
        cached = self.memo.get(key)
        if cached is not None:
            return cached
        self.states += 1
        elements = seq.elements
        ne = len(elements)
        s, n, fp, ic = self.s, self.n, self.fp, self.ic

        # Consume a run of single-continuation nodes iteratively (no recursion):
        # each Literal/AnyChar/Bracket advances (ei, si) by one on a match.
        while ei < ne:
            node = elements[ei]
            t = type(node)
            if t is Literal:
                if (si < n and (not fp or s[si] != '/')
                        and _eq(s[si], cast(Literal, node).char, ic)):
                    ei += 1
                    si += 1
                    continue
                self.memo[key] = _EMPTY
                return _EMPTY
            if t is AnyChar:
                if si < n and (not fp or s[si] != '/'):
                    ei += 1
                    si += 1
                    continue
                self.memo[key] = _EMPTY
                return _EMPTY
            if t is Bracket:
                if (si < n and (not fp or s[si] != '/')
                        and _bracket_match(cast(Bracket, node).content, s[si], ic)):
                    ei += 1
                    si += 1
                    continue
                self.memo[key] = _EMPTY
                return _EMPTY
            break  # Star or Extglob: handled below (the only recursion)

        if ei == ne:
            result = frozenset((si,))
        else:
            node = elements[ei]
            if type(node) is Star:
                out: set = set()
                end = si
                while True:
                    out |= self._match(seq, ei + 1, end)
                    if end >= n or (fp and s[end] == '/'):
                        break
                    end += 1
                result = frozenset(out)
            else:  # Extglob
                out2: set = set()
                for mid in self._element_ends(cast(Extglob, node), si):
                    out2 |= self._match(seq, ei + 1, mid)
                result = frozenset(out2)

        self.memo[key] = result
        return result

    def _element_ends(self, node: Extglob, si: int) -> set:
        """End indices after matching ONE extglob element ``op(alts)`` @ si."""
        op = node.op
        alts = node.alts
        if op == '@':
            return self._alt_ends(alts, si)
        if op == '?':
            return {si} | self._alt_ends(alts, si)
        if op == '+':
            return self._alt_closure(alts, self._alt_ends(alts, si))
        if op == '*':
            return self._alt_closure(alts, {si})
        # op == '!': every span s[si:e] that does NOT itself fully match one
        # alternative — the case a regex cannot express.
        positive = self._alt_ends(alts, si)
        s, fp = self.s, self.fp
        out = set()
        for e in range(si, self.n + 1):
            if fp and '/' in s[si:e]:
                break
            if e not in positive:
                out.add(e)
        return out

    def _alt_ends(self, alts: Tuple[Sequence, ...], si: int) -> set:
        """End indices where some alternative fully matches starting at s[si]."""
        out: set = set()
        for alt in alts:
            out |= self._match(alt, 0, si)
        return out

    def _alt_closure(self, alts: Tuple[Sequence, ...], start: set) -> set:
        """Zero-or-more closure of matching ``alts`` (for ``*(...)`` / ``+(...)``)."""
        seen = set(start)
        frontier = set(start)
        while frontier:
            nxt: set = set()
            for p in frontier:
                for end in self._alt_ends(alts, p):
                    if end not in seen and end != p:  # skip empty match (no loop)
                        seen.add(end)
                        nxt.add(end)
            frontier = nxt
        return seen


_EMPTY: frozenset = frozenset()


# --- free-function API (compatibility + primitives) ------------------------

def reachable_ends(root: Sequence, s: str, *, for_pathname: bool = False,
                   ic: bool = False) -> frozenset:
    """Every index ``k`` such that *root* fully matches ``s[:k]``."""
    return _Matcher(s, for_pathname, ic).reach(root, 0)


def fullmatch(root: Sequence, s: str, *, for_pathname: bool = False,
              ic: bool = False) -> bool:
    """Whether *root* matches the whole of *s* (short-circuiting)."""
    return _Matcher(s, for_pathname, ic).full_reaches(root, 0)


def match_at(root: Sequence, s: str, pos: int, *, for_pathname: bool = False,
             ic: bool = False) -> Optional[int]:
    """Leftmost-longest match LENGTH of *root* at ``s[pos:]``, or None.

    bash takes the longest match at the leftmost position (substitution), so
    this returns ``max`` of the reachable ends of ``s[pos:]`` minus ``pos``.
    """
    m = _Matcher(s, for_pathname, ic)
    ends = m.reach(root, pos)
    return (max(ends) - pos) if ends else None


def count_states(root: Sequence, s: str, *, for_pathname: bool = False,
                 ic: bool = False) -> int:
    """Number of distinct sequence states evaluated for a full-pattern match of
    *s* — the polynomial-complexity guard for tests."""
    m = _Matcher(s, for_pathname, ic)
    m.reach(root, 0)
    return m.states


# --- the four relations on a compiled pattern ------------------------------

class CompiledPattern:
    """One parse of a shell pattern; exposes the four relations its consumers
    need. Compiled once (via :class:`PatternCompiler`), reused across subjects
    and profiles (the AST carries no policy — :class:`MatchProfile` does)."""

    __slots__ = ("root",)

    def __init__(self, root: Sequence) -> None:
        self.root = root

    def full_match(self, text: str, profile: MatchProfile = STRING) -> bool:
        """Whether the pattern matches the WHOLE of *text*
        (``case`` / ``[[ == ]]`` / name filter / one pathname component /
        one character for case modification)."""
        return _Matcher(text, profile.for_pathname, profile.ic)._full(
            self.root, 0, 0)

    def matching_ends(self, text: str, start: int = 0,
                      profile: MatchProfile = STRING) -> frozenset:
        """Every end index ``k`` (``start <= k <= len(text)``) such that the
        pattern matches ``text[start:k]`` — prefix removal (``#`` = ``min``,
        ``##`` = ``max``)."""
        m = _Matcher(text, profile.for_pathname, profile.ic)
        return m._match(self.root, 0, start)

    def matching_starts(self, text: str, end: Optional[int] = None,
                        profile: MatchProfile = STRING) -> frozenset:
        """Every start index ``i`` (``0 <= i <= end``) such that the pattern
        matches ``text[i:end]`` — suffix removal (``%`` = ``max`` start / shortest
        suffix, ``%%`` = ``min`` start / longest suffix)."""
        if end is None:
            end = len(text)
        m = _Matcher(text, profile.for_pathname, profile.ic)
        match = m._match
        root = self.root
        out = set()
        for i in range(end + 1):
            if end in match(root, 0, i):
                out.add(i)
        return frozenset(out)

    def span_at(self, text: str, pos: int,
                profile: MatchProfile = STRING) -> Optional[int]:
        """Leftmost-longest match LENGTH at ``text[pos:]``, or ``None`` — the
        substitution primitive (``${v/}`` family). 0 is a zero-width match."""
        m = _Matcher(text, profile.for_pathname, profile.ic)
        ends = m._match(self.root, 0, pos)
        return (max(ends) - pos) if ends else None

    def spanner(self, text: str, profile: MatchProfile = STRING):
        """Return a ``pos -> Optional[int]`` leftmost-longest-length callable
        bound to ONE reused matcher, so a left-to-right substitution scan over
        *text* shares one memo across all positions (a single pass, not one
        matcher per position)."""
        m = _Matcher(text, profile.for_pathname, profile.ic)
        match = m._match
        root = self.root

        def span_at(pos: int) -> Optional[int]:
            ends = match(root, 0, pos)
            return (max(ends) - pos) if ends else None

        return span_at

    def matching_spans(self, text: str,
                       profile: MatchProfile = STRING) -> Iterator[Tuple[int, int]]:
        """Left-to-right leftmost-longest non-overlapping match spans
        ``(start, end)`` over *text* — the ``${v//}`` global-substitution walk.
        Zero-width matches advance by one; the consumer applies bash's
        end-of-subject empty-match policy."""
        span_at = self.spanner(text, profile)
        pos = 0
        n = len(text)
        while pos <= n:
            length = span_at(pos)
            if length is None:
                pos += 1
                continue
            yield (pos, pos + length)
            pos += length if length > 0 else 1


# --- unparse (for round-trip tests / debugging) ----------------------------

_LITERAL_SPECIAL = set('*?[\\')


def unparse(node: object) -> str:
    """Regenerate pattern text from an AST node.

    Round-trips semantically: ``compile_pattern(unparse(compile_pattern(p)))``
    yields an AST equal in structure to ``compile_pattern(p)`` (verified by the
    unit tests). Literal metacharacters are re-escaped with ``\\`` so they
    recompile as literals rather than operators.
    """
    if isinstance(node, Sequence):
        return ''.join(unparse(e) for e in node.elements)
    if isinstance(node, Literal):
        return ('\\' + node.char) if node.char in _LITERAL_SPECIAL else node.char
    if isinstance(node, AnyChar):
        return '?'
    if isinstance(node, Star):
        return '*'
    if isinstance(node, Bracket):
        return '[' + node.content + ']'
    if isinstance(node, Extglob):
        return node.op + '(' + '|'.join(unparse(a) for a in node.alts) + ')'
    raise TypeError(f"not a pattern node: {node!r}")


def structure(node: object) -> object:
    """A hashable, identity-free structural view of an AST (for test equality).

    Returns nested tuples of node-type names and payloads, so two ASTs with the
    same shape compare equal even though nodes are identity-based objects.
    """
    if isinstance(node, Sequence):
        return ('Seq', tuple(structure(e) for e in node.elements))
    if isinstance(node, Literal):
        return ('Lit', node.char)
    if isinstance(node, AnyChar):
        return ('Any',)
    if isinstance(node, Star):
        return ('Star',)
    if isinstance(node, Bracket):
        return ('Brk', node.content)
    if isinstance(node, Extglob):
        return ('Ext', node.op, tuple(structure(a) for a in node.alts))
    raise TypeError(f"not a pattern node: {node!r}")
