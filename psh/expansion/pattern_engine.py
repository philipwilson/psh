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
2. The matcher (:class:`_Matcher`) handles stars and literal chains
   ITERATIVELY: the boolean full match for extglob-free sequences is the
   classic two-pointer backtrack (zero recursion, one backtrack point per
   star), and the reachable-end set is a forward position-set DP that
   processes each element once (a Star becomes an interval union). Star and
   literal COUNT therefore never consume recursion frames — a 50,000-star
   pattern matches at any recursion limit (#20 H7-b + bounce ruling) — and the
   DP is its own memoization, so adversarial repetition stays
   ``O(nodes·positions)``, never exponential (#20 H7-c). The ONLY recursion is
   into extglob alternatives — bounded by extglob NESTING depth, a compile-time
   structural property; past the interpreter limit that raises
   ``RecursionError``, an EXPECTED shell error under strict-errors. The
   reachable-end set natively serves the four relations
   :class:`CompiledPattern` exposes: ``full_match``, ``matching_ends`` (prefix
   removal), ``matching_starts`` (suffix removal), and ``span_at`` /
   ``matching_spans`` (leftmost-longest substitution).

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

    ``enclosed`` records whether this group was parsed INSIDE some outer
    group's alternative — a compile-time property that decides bash's
    end-of-string negation rule (slot 3.1): a ``!(...)`` reached with an
    empty subject remainder directly after a wildcard run matches
    UNCONDITIONALLY at top level but NEVER when enclosed (bash 5.2's
    NUL-driven ``glob_patscan`` escapes an alternative slice and finds the
    enclosing ``)``, flipping the inverted EXTMATCH result — measured and
    corpus-pinned, see ``test_pattern_bash_composition_differential.py``).
    """
    op: str
    alts: Tuple["Sequence", ...]
    enclosed: bool = False


@dataclass(eq=False)
class Sequence:
    """An ordered run of nodes; the compiled form of a whole pattern or one
    extglob alternative.

    ``has_extglob`` is a lazily computed routing hint (see
    :func:`_seq_has_extglob`): a sequence with no :class:`Extglob` element is
    matched by the fully iterative fast paths (two-pointer boolean / forward
    DP), never recursing at all.

    ``bash_quirk`` is the lazily computed bash-composition routing flag (see
    :func:`_seq_bash_quirk`): only a sequence in which an extglob group sits
    directly after a wildcard run (here or in any nested alternative) routes
    to the measured-composition matcher (:class:`_BashMatcher`); every other
    pattern keeps the fast paths unchanged."""
    elements: Tuple[object, ...] = field(default_factory=tuple)
    has_extglob: Optional[bool] = None
    bash_quirk: Optional[bool] = None


def _seq_has_extglob(seq: Sequence) -> bool:
    """Whether *seq* contains an :class:`Extglob` element (lazily cached)."""
    he = seq.has_extglob
    if he is None:
        he = any(type(e) is Extglob for e in seq.elements)
        seq.has_extglob = he
    return he


def _seq_bash_quirk(seq: Sequence) -> bool:
    """Whether *seq* needs the measured bash-composition matcher.

    True iff an :class:`Extglob` element follows a wildcard run containing a
    :class:`Star` — directly, or with intervening ``?``/``*`` wildcards —
    at this level or inside any nested alternative. Exactly these shapes are
    where bash 5.2's measured semantics diverge from the reachability DP
    (slot 3.1 corpus: 0 divergence outside them in 65,625 measured cells):
    the star case's strict continuation bounds, its ``?(``/``*(``
    try-then-skip branches, and the end-of-string negation rule are all
    slice-end-relative, so they cannot ride one forward reachability pass.
    Lazily cached on the node (same pattern as ``has_extglob``).

    This flag is also the EXACT exclusion predicate for the regex-oracle
    agreement corpus in ``test_pattern_engine_matcher.py`` (the regex model
    cannot express bash's star∘group composition) — one decider, imported
    there, never re-derived (R3).
    """
    q = seq.bash_quirk
    if q is None:
        q = False
        star_run = False
        for e in seq.elements:
            t = type(e)
            if t is Star:
                star_run = True
            elif t is AnyChar:
                pass  # a '?' rides an active wildcard run (bash collapses it)
            elif t is Extglob:
                eg = cast(Extglob, e)
                if star_run or any(_seq_bash_quirk(alt) for alt in eg.alts):
                    q = True
                    break
                star_run = False
            else:
                star_run = False
        seq.bash_quirk = q
    return q


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


def _parse(pattern: str, start: int, end: int, extglob: bool,
           enclosed: bool = False) -> Sequence:
    """Compile ``pattern[start:end]`` into a Sequence (``\\`` = escape).

    ``enclosed`` is True while parsing INSIDE any extglob group's alternative;
    it stamps :attr:`Extglob.enclosed` (the compile-time input to bash's
    end-of-string negation rule)."""
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
                elements.append(Extglob(ch, alts, enclosed))
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
    """Compile one extglob alternative (always with extglob enabled inside).

    Everything inside an alternative is ``enclosed`` — including any nested
    groups' own alternatives (the flag only deepens, never resets)."""
    return _parse(alt, 0, len(alt), extglob, enclosed=True)


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


# --- the matcher: iterative stars, recursion only for extglob nesting -------
#
# Reachable-end-position-set semantics: ``_ends(seq, ei, si)`` returns every
# index ``k`` such that ``seq.elements[ei:]`` fully matches ``s[si:k]``. This is
# the contract every consumer is built from:
#   * full match          -> len(s) in ends
#   * prefix removal (#/##) -> min/max of matching_ends
#   * suffix removal (%/%%) -> matching_starts (i where s[i:end] fully matches)
#   * leftmost-longest sub  -> span_at(pos) = max ends of s[pos:]
#   * pathname component    -> full_match(entry, for_pathname=True)
#
# STAR COUNT NEVER CONSUMES RECURSION FRAMES (bounce ruling, 2026-07-19):
#   * ``_full_simple`` — the boolean full match for sequences WITHOUT extglob
#     (every plain glob) — is the classic two-pointer backtrack algorithm: one
#     backtrack point per star, O(n*m) worst case, ZERO recursion. 50,000
#     consecutive stars or a ``*a*a…`` x50k chain match at any recursion limit.
#   * ``_ends`` walks the sequence with a forward position-set DP: each element
#     transforms the reachable-position set once (a Star turns it into a union
#     of intervals), so the DP itself IS the memoization — adversarial
#     repetition (``*(a|aa)c``, ``?(a)…!(z)``, plain ``*a*a…*b``) stays
#     O(nodes*positions), never exponential (#20 H7-c), and literal chains /
#     stars never recurse (#20 H7-b).
#   * The ONLY recursion is ``_ends`` -> ``_element_ends`` -> alternative
#     ``_ends`` — one level per extglob NESTING depth, a compile-time structural
#     property (the compiler itself recurses per nesting level, so the matcher
#     can never out-recurse the pattern that compiled). Past the interpreter
#     limit this raises ``RecursionError``, which is an EXPECTED shell error
#     under strict-errors (see the taxonomy in ``psh/core/CLAUDE.md``) — pinned
#     by ``test_pattern_relations.py``.
#
# ``fp`` (for_pathname) and ``ic`` are constant for one match, so they live on
# the Matcher rather than in any key.


class _Matcher:
    """One match of a compiled pattern against one subject.

    A fresh instance is created per relation call (``matching_starts`` and the
    substitution ``spanner`` reuse one across entry positions). ``states``
    counts (element, position) evaluations in the forward DP — the
    polynomial-complexity guard the tests assert on.
    """

    __slots__ = ("s", "n", "fp", "ic", "states", "_nslash")

    def __init__(self, s: str, for_pathname: bool, ic: bool) -> None:
        self.s = s
        self.n = len(s)
        self.fp = for_pathname
        self.ic = ic
        self.states = 0
        self._nslash: Optional[List[int]] = None

    # -- shared precompute ---------------------------------------------------

    def _next_slash(self) -> List[int]:
        """``ns[p]`` = index of the first ``/`` at or after ``p``, else ``n``.

        Lazily built once per matcher; only the for_pathname Star transition
        needs it (a star's reachable interval ends at the next slash)."""
        ns = self._nslash
        if ns is None:
            s, n = self.s, self.n
            ns = [n] * (n + 1)
            nxt = n
            for p in range(n - 1, -1, -1):
                if s[p] == '/':
                    nxt = p
                ns[p] = nxt
            self._nslash = ns
        return ns

    # -- boolean full match: iterative two-pointer (no extglob) --------------

    def _full(self, seq: Sequence, ei: int, si: int) -> bool:
        """Whether ``seq.elements[ei:]`` matches EXACTLY ``s[si:n]``."""
        if _seq_has_extglob(seq):
            return self.n in self._ends(seq, ei, si)
        return self._full_simple(seq.elements, ei, si)

    def _full_simple(self, elements: Tuple[object, ...], ei: int,
                     si: int) -> bool:
        """Classic glob two-pointer backtrack (Literal/AnyChar/Bracket/Star
        only): greedy advance, on mismatch re-extend the MOST RECENT star by
        one subject character. One backtrack point suffices for plain globs
        (the standard fnmatch algorithm); a star never consumes ``/`` under
        for_pathname, and literal ``/`` elements force slash alignment, so the
        per-component argument carries over. O(n*m) worst case, no recursion,
        no allocation."""
        s, n, fp, ic = self.s, self.n, self.fp, self.ic
        ne = len(elements)
        p, i = ei, si
        star_p = -1
        star_i = si
        while i < n:
            if p < ne:
                node = elements[p]
                t = type(node)
                if t is Star:
                    star_p = p
                    star_i = i
                    p += 1
                    continue
                if t is Literal:
                    if _eq(s[i], cast(Literal, node).char, ic):
                        p += 1
                        i += 1
                        continue
                elif t is AnyChar:
                    if not fp or s[i] != '/':
                        p += 1
                        i += 1
                        continue
                else:  # Bracket
                    if ((not fp or s[i] != '/')
                            and _bracket_match(cast(Bracket, node).content,
                                               s[i], ic)):
                        p += 1
                        i += 1
                        continue
            # Mismatch (or pattern exhausted with subject left): backtrack.
            if star_p < 0:
                return False
            if fp and s[star_i] == '/':
                return False  # the star cannot consume the '/'
            star_i += 1
            i = star_i
            p = star_p + 1
        # Subject exhausted: any trailing stars match empty.
        while p < ne and type(elements[p]) is Star:
            p += 1
        return p == ne

    # -- reachable-end set: forward position-set DP --------------------------

    def _ends(self, seq: Sequence, ei: int, si: int) -> frozenset:
        """Every ``k`` such that ``seq.elements[ei:]`` matches ``s[si:k]``.

        A forward DP over the elements: ``positions`` is the set of subject
        indices reachable after consuming the elements so far. Each element is
        processed ONCE (Star expands the set to a union of intervals — no
        recursion), so 50,000 stars are 50,000 iterations of this loop. Only an
        Extglob element recurses (into its alternatives' ``_ends``), bounding
        recursion by extglob NESTING depth."""
        elements = seq.elements
        s, n, fp, ic = self.s, self.n, self.fp, self.ic
        positions = {si}
        for idx in range(ei, len(elements)):
            if not positions:
                return _EMPTY
            self.states += len(positions)
            node = elements[idx]
            t = type(node)
            if t is Literal:
                ch = cast(Literal, node).char
                positions = {p + 1 for p in positions
                             if p < n and _eq(s[p], ch, ic)}
            elif t is AnyChar:
                positions = {p + 1 for p in positions
                             if p < n and (not fp or s[p] != '/')}
            elif t is Bracket:
                content = cast(Bracket, node).content
                positions = {p + 1 for p in positions
                             if p < n and (not fp or s[p] != '/')
                             and _bracket_match(content, s[p], ic)}
            elif t is Star:
                if not fp:
                    positions = set(range(min(positions), n + 1))
                else:
                    # Union of intervals [p, next_slash(p)] — a star reaches
                    # any position up to (and including the index of) the next
                    # '/', which it cannot consume.
                    ns = self._next_slash()
                    new: set = set()
                    covered = -1
                    for p in sorted(positions):
                        limit = ns[p]
                        if limit <= covered:
                            continue  # interval fully covered already
                        start = p if p > covered else covered + 1
                        new.update(range(start, limit + 1))
                        covered = limit
                    positions = new
            else:  # Extglob: the one recursive element (nesting depth only)
                eg = cast(Extglob, node)
                new2: set = set()
                for p in positions:
                    new2 |= self._element_ends(eg, p)
                positions = new2
        return frozenset(positions)

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
        for end in range(si, self.n + 1):
            if fp and '/' in s[si:end]:
                break
            if end not in positive:
                out.add(end)
        return out

    def _alt_ends(self, alts: Tuple[Sequence, ...], si: int) -> set:
        """End indices where some alternative fully matches starting at s[si]."""
        out: set = set()
        for alt in alts:
            out |= self._ends(alt, 0, si)
        return out

    def _alt_closure(self, alts: Tuple[Sequence, ...], start: set) -> set:
        """Zero-or-more closure of matching ``alts`` (for ``*(...)``/``+(...)``);
        iterative frontier expansion."""
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

    # -- public wrappers -----------------------------------------------------

    def reach(self, seq: Sequence, si: int) -> frozenset:
        """Reachable end indices matching all of ``seq`` from ``s[si]``."""
        return self._ends(seq, 0, si)

    def full_reaches(self, seq: Sequence, si: int) -> bool:
        """Whether ``seq`` matches EXACTLY ``s[si:n]``."""
        return self._full(seq, 0, si)


_EMPTY: frozenset = frozenset()


# --- measured bash-composition matcher (slot 3.1) ---------------------------
#
# bash 5.2 composes a wildcard run with a FOLLOWING extglob group by rules
# that are relative to where the matched slice ENDS (sm_loop.c star case),
# so for exactly those shapes (_seq_bash_quirk) "pattern matches text[i:k]"
# is a per-(i,k) boolean and cannot ride the forward reachability DP. This
# matcher is a faithful port of the MEASURED model (65,625 corpus cells vs
# live bash 5.2.26, 0 mismatches — slot 3.1 ledger A4; enforced by
# test_pattern_bash_composition_differential.py). Non-quirk patterns never
# reach it. The rules, in bash sm_loop.c terms:
#
#   * star case, after collapsing consecutive wildcards: the continuation is
#     tried at every position STRICTLY before the slice end (an
#     empty-remainder match of an @/+-headed rest is impossible);
#   * a `?(...)` inside the wildcard run: extmatch ONCE at the current
#     position, else the group is SKIPPED and the run continues;
#   * a `*(...)` inside the run: extmatch at every position strictly before
#     the slice end, else SKIPPED;
#   * the run reaching the end of the pattern (including via skips) matches;
#   * empty remainder with the next element `!(...)`: matches
#     unconditionally iff the group is NOT enclosed (Extglob.enclosed) —
#     anything after the group is ignored;
#   * EXTMATCH: '@' = alt-span + continuation over all splits; '?' adds the
#     zero-instance try; '*'/'+' = closure over nonempty alt spans (+ the
#     zero/one-instance seeds) with continuation at every closure point;
#     '!' = per-split complement AND continuation.
#
# Recursion here is bounded by the PATTERN structure (one frame per group
# dispatch / star-run in a sequence, plus alt nesting) — never by subject
# length or star count; the per-(sequence, element, si, se) memo keeps the
# evaluation polynomial (guarded by count_states via `states`).


class _BashMatcher:
    """One subject × one profile evaluation of a bash-quirk pattern.

    ``match(seq, ei, si, se)`` — do ``seq.elements[ei:]`` match exactly
    ``s[si:se]`` under the measured bash-5.2 composition semantics. One
    instance is shared across a whole relation call (all slice bounds), so
    the memo carries across the per-k loops. ``states`` counts uncached
    evaluations — the deterministic complexity guard."""

    __slots__ = ("s", "fp", "ic", "memo", "states")

    def __init__(self, s: str, for_pathname: bool, ic: bool) -> None:
        self.s = s
        self.fp = for_pathname
        self.ic = ic
        self.memo: dict = {}
        self.states = 0

    def match(self, seq: Sequence, ei: int, si: int, se: int) -> bool:
        key = (id(seq), ei, si, se)
        r = self.memo.get(key)
        if r is None:
            self.states += 1
            r = self._match(seq, ei, si, se)
            self.memo[key] = r
        return r

    def _match(self, seq: Sequence, ei: int, si: int, se: int) -> bool:
        s, fp, ic = self.s, self.fp, self.ic
        elements = seq.elements
        ne = len(elements)
        i, n = ei, si
        while i < ne:
            node = elements[i]
            t = type(node)
            if t is Extglob:
                # main-loop dispatch: the group + rest decide (returns).
                return self._extmatch(cast(Extglob, node), seq, i, n, se)
            if t is Literal:
                if n < se and _eq(s[n], cast(Literal, node).char, ic):
                    n += 1
                    i += 1
                    continue
                return False
            if t is AnyChar:
                if n < se and (not fp or s[n] != '/'):
                    n += 1
                    i += 1
                    continue
                return False
            if t is Bracket:
                if (n < se and (not fp or s[n] != '/')
                        and _bracket_match(cast(Bracket, node).content,
                                           s[n], ic)):
                    n += 1
                    i += 1
                    continue
                return False
            # Star: the bash star case.
            i += 1
            if i >= ne:
                return True  # trailing star swallows the remainder
            # Collapse loop: wildcards and ?(/*( groups ride the run.
            while True:
                node2 = elements[i]
                t2 = type(node2)
                if t2 is Star:
                    if fp and n < se and s[n] == '/':
                        return False
                elif t2 is AnyChar:
                    if fp and n < se and s[n] == '/':
                        return False
                    if n >= se:
                        return False
                    n += 1
                elif t2 is Extglob and cast(Extglob, node2).op == '?':
                    if fp and n < se and s[n] == '/':
                        return False
                    if self._extmatch(cast(Extglob, node2), seq, i, n, se):
                        return True
                    # group failed: SKIP it, continue the run
                elif t2 is Extglob and cast(Extglob, node2).op == '*':
                    if fp and n < se and s[n] == '/':
                        return False
                    for n2 in range(n, se):  # strictly before slice end
                        if self._extmatch(cast(Extglob, node2), seq, i, n2,
                                          se):
                            return True
                else:
                    break  # first element the run cannot absorb
                i += 1
                if i >= ne:
                    return True  # run (incl. skips) consumed the pattern
            # node2 = first non-run element, at index i.
            if (t2 is Extglob and cast(Extglob, node2).op == '!'
                    and n == se):
                # end-of-string negation rule: unconditional, rest ignored.
                return not cast(Extglob, node2).enclosed
            if fp and t2 is Literal and cast(Literal, node2).char == '/':
                # [star]/rest: consume up to a slash, then match the rest.
                m2 = s.find('/', n, se)
                if m2 != -1:
                    return self.match(seq, i + 1, m2 + 1, se)
                return False
            bound = se
            if fp:
                m2 = s.find('/', n, se)
                if m2 != -1:
                    bound = m2  # a star never crosses '/'
            for n2 in range(n, bound):  # strictly before the slice end
                if self.match(seq, i, n2, se):
                    return True
            return False
        return n == se

    # -- extglob group + continuation (bash EXTMATCH) ------------------------

    def _extmatch(self, node: Extglob, seq: Sequence, gi: int, si: int,
                  se: int) -> bool:
        """Group at ``seq.elements[gi]`` matched at ``s[si:]``, then the rest
        of *seq*, all within the slice ending at *se*."""
        op = node.op
        alts = node.alts

        def rest_ok(pos: int) -> bool:
            return self.match(seq, gi + 1, pos, se)

        if op == '@':
            for split in range(si, se + 1):
                if self._alt_span(alts, si, split) and rest_ok(split):
                    return True
            return False
        if op == '?':
            if rest_ok(si):
                return True
            for split in range(si, se + 1):
                if self._alt_span(alts, si, split) and rest_ok(split):
                    return True
            return False
        if op == '*':
            return any(rest_ok(pos)
                       for pos in self._closure(alts, {si}, se))
        if op == '+':
            seed = {split for split in range(si, se + 1)
                    if self._alt_span(alts, si, split)}
            return any(rest_ok(pos) for pos in self._closure(alts, seed, se))
        # op == '!': per-split complement AND continuation.
        for split in range(si, se + 1):
            if not self._alt_span(alts, si, split) and rest_ok(split):
                return True
        return False

    def _alt_span(self, alts: Tuple[Sequence, ...], a: int, b: int) -> bool:
        """Whether some alternative fully matches the span ``s[a:b]``."""
        return any(self.match(alt, 0, a, b) for alt in alts)

    def _closure(self, alts: Tuple[Sequence, ...], seed: set,
                 se: int) -> set:
        """Positions reachable from *seed* by zero or more NONEMPTY alt
        spans (iterative frontier expansion — no per-instance recursion)."""
        seen = set(seed)
        frontier = list(seed)
        while frontier:
            nxt = []
            for pos in frontier:
                for end in range(pos + 1, se + 1):
                    if end not in seen and self._alt_span(alts, pos, end):
                        seen.add(end)
                        nxt.append(end)
            frontier = nxt
        return seen


# --- free-function API (compatibility + primitives) ------------------------

def reachable_ends(root: Sequence, s: str, *, for_pathname: bool = False,
                   ic: bool = False) -> frozenset:
    """Every index ``k`` such that *root* fully matches ``s[:k]``.

    For bash-quirk patterns (:func:`_seq_bash_quirk`) membership is
    slice-end-relative, so each ``k`` is evaluated as its own slice boolean
    (one shared memoized matcher); everything else keeps the forward DP."""
    if _seq_bash_quirk(root):
        bm = _BashMatcher(s, for_pathname, ic)
        return frozenset(k for k in range(len(s) + 1)
                         if bm.match(root, 0, 0, k))
    return _Matcher(s, for_pathname, ic).reach(root, 0)


def fullmatch(root: Sequence, s: str, *, for_pathname: bool = False,
              ic: bool = False) -> bool:
    """Whether *root* matches the whole of *s* (iterative for plain globs)."""
    if _seq_bash_quirk(root):
        return _BashMatcher(s, for_pathname, ic).match(root, 0, 0, len(s))
    return _Matcher(s, for_pathname, ic).full_reaches(root, 0)


def match_at(root: Sequence, s: str, pos: int, *, for_pathname: bool = False,
             ic: bool = False) -> Optional[int]:
    """Leftmost-longest match LENGTH of *root* at ``s[pos:]``, or None.

    bash takes the longest match at the leftmost position (substitution), so
    this returns the largest ``k - pos`` with a full match of ``s[pos:k]``.
    """
    if _seq_bash_quirk(root):
        bm = _BashMatcher(s, for_pathname, ic)
        for k in range(len(s), pos - 1, -1):
            if bm.match(root, 0, pos, k):
                return k - pos
        return None
    m = _Matcher(s, for_pathname, ic)
    ends = m.reach(root, pos)
    return (max(ends) - pos) if ends else None


def count_states(root: Sequence, s: str, *, for_pathname: bool = False,
                 ic: bool = False) -> int:
    """Number of distinct sequence states evaluated for a full-pattern match of
    *s* — the polynomial-complexity guard for tests (both matcher paths)."""
    if _seq_bash_quirk(root):
        bm = _BashMatcher(s, for_pathname, ic)
        bm.match(root, 0, 0, len(s))
        return bm.states
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
        if _seq_bash_quirk(self.root):
            return _BashMatcher(text, profile.for_pathname, profile.ic).match(
                self.root, 0, 0, len(text))
        return _Matcher(text, profile.for_pathname, profile.ic)._full(
            self.root, 0, 0)

    def matching_ends(self, text: str, start: int = 0,
                      profile: MatchProfile = STRING) -> frozenset:
        """Every end index ``k`` (``start <= k <= len(text)``) such that the
        pattern matches ``text[start:k]`` — prefix removal (``#`` = ``min``,
        ``##`` = ``max``).

        bash-quirk patterns (:func:`_seq_bash_quirk`) have slice-end-relative
        semantics, so each ``k`` is its own slice boolean (one shared
        memoized matcher); all other patterns keep the one-pass DP."""
        if _seq_bash_quirk(self.root):
            bm = _BashMatcher(text, profile.for_pathname, profile.ic)
            root = self.root
            return frozenset(k for k in range(start, len(text) + 1)
                             if bm.match(root, 0, start, k))
        m = _Matcher(text, profile.for_pathname, profile.ic)
        return m._ends(self.root, 0, start)

    def matching_starts(self, text: str, end: Optional[int] = None,
                        profile: MatchProfile = STRING) -> frozenset:
        """Every start index ``i`` (``0 <= i <= end``) such that the pattern
        matches ``text[i:end]`` — suffix removal (``%`` = ``max`` start / shortest
        suffix, ``%%`` = ``min`` start / longest suffix)."""
        if end is None:
            end = len(text)
        if _seq_bash_quirk(self.root):
            bm = _BashMatcher(text, profile.for_pathname, profile.ic)
            root = self.root
            return frozenset(i for i in range(end + 1)
                             if bm.match(root, 0, i, end))
        m = _Matcher(text, profile.for_pathname, profile.ic)
        match = m._ends
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
        if _seq_bash_quirk(self.root):
            bm = _BashMatcher(text, profile.for_pathname, profile.ic)
            root = self.root
            for k in range(len(text), pos - 1, -1):
                if bm.match(root, 0, pos, k):
                    return k - pos
            return None
        m = _Matcher(text, profile.for_pathname, profile.ic)
        ends = m._ends(self.root, 0, pos)
        return (max(ends) - pos) if ends else None

    def spanner(self, text: str, profile: MatchProfile = STRING):
        """Return a ``pos -> Optional[int]`` leftmost-longest-length callable
        bound to ONE reused matcher, so a left-to-right substitution scan over
        *text* shares the matcher's per-subject precompute (the next-slash
        table / the bash-composition memo) instead of building one matcher
        per position."""
        root = self.root
        if _seq_bash_quirk(root):
            bm = _BashMatcher(text, profile.for_pathname, profile.ic)
            n = len(text)

            def bash_span_at(pos: int) -> Optional[int]:
                for k in range(n, pos - 1, -1):
                    if bm.match(root, 0, pos, k):
                        return k - pos
                return None

            return bash_span_at
        m = _Matcher(text, profile.for_pathname, profile.ic)
        match = m._ends

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
