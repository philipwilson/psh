"""Compiled shell-pattern engine: one AST, parsed once, matched iteratively.

Historically psh matched shell patterns three ways, each wrong or fragile on a
different input (appraisal #6 and #20 H7):

* the **regex** backend (``extglob._convert_pattern`` → Python ``re``) blows up
  on ambiguous repetition with a forced-fail tail — ``*(a|aa)c`` on ``"a"*N+"b"``
  is catastrophic backtracking, and a plain ``*a*a…*b`` is exponential too;
* the **recursive backtracking matcher** re-parsed and fanned out exponentially;
* the compiled engine that replaced them was still **recursive** at the sequence
  level, so a ~1,500-literal pattern raised ``RecursionError``.

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
2. The **iterative** matcher (:class:`_Matcher`) evaluates each
   ``(sequence, element-index, subject-index)`` state at most once with an
   explicit worklist — no Python recursion, so pattern depth is bounded only by
   memory. Its reachable-end-position set natively serves the four relations
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
from typing import Iterator, List, Optional, Tuple

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
# The matcher is ITERATIVE: an explicit worklist evaluates each state at most
# once (memoized), so NO Python recursion is used — a pattern of any depth
# (thousands of literals) can no longer raise RecursionError (#20 H7). ``fp``
# (for_pathname) and ``ic`` are constant for one match, so they live on the
# Matcher rather than in the memo key.

# State kinds in the worklist memo:
#   ('S', id(seq), ei, si) -> frozenset of end positions matching seq[ei:] @ si
#   ('E', id(node), si)    -> set of end positions after ONE extglob element @ si


class _Matcher:
    """One reachable-position match of a compiled pattern against one subject.

    A fresh instance (and memo) is created per match call. ``states`` counts
    distinct evaluated sequence states (``'S'`` memo misses) — the
    polynomial-complexity guard the tests assert on.
    """

    __slots__ = ("s", "n", "fp", "ic", "memo", "states", "_node")

    def __init__(self, s: str, for_pathname: bool, ic: bool) -> None:
        self.s = s
        self.n = len(s)
        self.fp = for_pathname
        self.ic = ic
        self.memo: dict = {}
        self.states = 0
        self._node: dict = {}  # id(obj) -> obj, so ids stay resolvable

    def reach(self, seq: Sequence, si: int) -> frozenset:
        """Reachable end indices matching all of ``seq`` from ``s[si]``."""
        root = ('S', id(seq), 0, si)
        self._node[id(seq)] = seq
        if root in self.memo:
            return self.memo[root]
        stack: List[tuple] = [root]
        while stack:
            key = stack[-1]
            if key in self.memo:
                stack.pop()
                continue
            deps = self._deps(key)
            pending = [d for d in deps if d not in self.memo]
            if pending:
                stack.extend(pending)
            else:
                self.memo[key] = self._combine(key, deps)
                stack.pop()
        return self.memo[root]

    # -- dependency discovery (re-evaluated each visit; may grow as deps land)

    def _deps(self, key: tuple) -> List[tuple]:
        if key[0] == 'S':
            return self._seq_deps(key)
        return self._elem_deps(key)

    def _seq_deps(self, key: tuple) -> List[tuple]:
        _, seq_id, ei, si = key
        seq = self._node[seq_id]
        elements = seq.elements
        if ei == len(elements):
            return []
        node = elements[ei]
        s, n, fp = self.s, self.n, self.fp
        if isinstance(node, (Literal, AnyChar, Bracket)):
            if si < n and self._char_ok(node, s[si]):
                return [('S', seq_id, ei + 1, si + 1)]
            return []
        if isinstance(node, Star):
            out = []
            e = si
            while True:
                out.append(('S', seq_id, ei + 1, e))
                if e >= n or (fp and s[e] == '/'):
                    break
                e += 1
            return out
        if isinstance(node, Extglob):
            self._node[id(node)] = node
            ekey = ('E', id(node), si)
            if ekey not in self.memo:
                return [ekey]
            return [('S', seq_id, ei + 1, mid) for mid in self.memo[ekey]]
        raise TypeError(f"not a pattern node: {node!r}")  # pragma: no cover

    def _elem_deps(self, key: tuple) -> List[tuple]:
        _, node_id, si = key
        node = self._node[node_id]
        alts = node.alts
        for a in alts:
            self._node[id(a)] = a
        if node.op in ('@', '?', '!'):
            return [('S', id(a), 0, si) for a in alts]
        # '+' / '*': the closure can reach any position in [si..n].
        return [('S', id(a), 0, p) for a in alts for p in range(si, self.n + 1)]

    # -- state combination (all deps present in memo)

    def _combine(self, key: tuple, deps: List[tuple]) -> frozenset:
        if key[0] == 'S':
            return self._seq_combine(key)
        return frozenset(self._elem_combine(key))

    def _seq_combine(self, key: tuple) -> frozenset:
        _, seq_id, ei, si = key
        self.states += 1
        seq = self._node[seq_id]
        elements = seq.elements
        if ei == len(elements):
            return frozenset((si,))
        node = elements[ei]
        s, n, fp = self.s, self.n, self.fp
        if isinstance(node, (Literal, AnyChar, Bracket)):
            if si < n and self._char_ok(node, s[si]):
                return self.memo[('S', seq_id, ei + 1, si + 1)]
            return frozenset()
        if isinstance(node, Star):
            out: set = set()
            e = si
            while True:
                out |= self.memo[('S', seq_id, ei + 1, e)]
                if e >= n or (fp and s[e] == '/'):
                    break
                e += 1
            return frozenset(out)
        if isinstance(node, Extglob):
            ekey = ('E', id(node), si)
            out2: set = set()
            for mid in self.memo[ekey]:
                out2 |= self.memo[('S', seq_id, ei + 1, mid)]
            return frozenset(out2)
        raise TypeError(f"not a pattern node: {node!r}")  # pragma: no cover

    def _char_ok(self, node, ch: str) -> bool:
        if self.fp and ch == '/':
            return False
        if isinstance(node, Literal):
            return _eq(ch, node.char, self.ic)
        if isinstance(node, AnyChar):
            return True
        return _bracket_match(node.content, ch, self.ic)  # Bracket

    def _elem_combine(self, key: tuple) -> set:
        """End indices after matching ONE extglob element ``op(alts)`` @ si."""
        _, node_id, si = key
        node = self._node[node_id]
        op = node.op
        alts = node.alts

        def alt_ends(p: int) -> set:
            out: set = set()
            for a in alts:
                out |= self.memo[('S', id(a), 0, p)]
            return out

        if op == '@':
            return alt_ends(si)
        if op == '?':
            return {si} | alt_ends(si)
        if op == '!':
            # Every span s[si:e] that does NOT itself fully match one
            # alternative (the case a regex cannot express).
            positive = alt_ends(si)
            s, fp, n = self.s, self.fp, self.n
            out = set()
            for e in range(si, n + 1):
                if fp and '/' in s[si:e]:
                    break
                if e not in positive:
                    out.add(e)
            return out
        # '+' / '*': zero-or-more (+ : one-or-more) closure of alt matches.
        start = alt_ends(si) if op == '+' else {si}
        seen = set(start)
        frontier = set(start)
        while frontier:
            nxt: set = set()
            for p in frontier:
                for e in alt_ends(p):
                    if e not in seen and e != p:  # skip empty match (no loop)
                        seen.add(e)
                        nxt.add(e)
            frontier = nxt
        return seen


# --- free-function API (compatibility + primitives) ------------------------

def reachable_ends(root: Sequence, s: str, *, for_pathname: bool = False,
                   ic: bool = False) -> frozenset:
    """Every index ``k`` such that *root* fully matches ``s[:k]``."""
    return _Matcher(s, for_pathname, ic).reach(root, 0)


def fullmatch(root: Sequence, s: str, *, for_pathname: bool = False,
              ic: bool = False) -> bool:
    """Whether *root* matches the whole of *s*."""
    return len(s) in _Matcher(s, for_pathname, ic).reach(root, 0)


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
        m = _Matcher(text, profile.for_pathname, profile.ic)
        return len(text) in m.reach(self.root, 0)

    def matching_ends(self, text: str, start: int = 0,
                      profile: MatchProfile = STRING) -> frozenset:
        """Every end index ``k`` (``start <= k <= len(text)``) such that the
        pattern matches ``text[start:k]`` — prefix removal (``#`` = ``min``,
        ``##`` = ``max``)."""
        m = _Matcher(text, profile.for_pathname, profile.ic)
        return m.reach(self.root, start)

    def matching_starts(self, text: str, end: Optional[int] = None,
                        profile: MatchProfile = STRING) -> frozenset:
        """Every start index ``i`` (``0 <= i <= end``) such that the pattern
        matches ``text[i:end]`` — suffix removal (``%`` = ``max`` start / shortest
        suffix, ``%%`` = ``min`` start / longest suffix)."""
        if end is None:
            end = len(text)
        m = _Matcher(text, profile.for_pathname, profile.ic)
        out = set()
        for i in range(end + 1):
            if end in m.reach(self.root, i):
                out.add(i)
        return frozenset(out)

    def span_at(self, text: str, pos: int,
                profile: MatchProfile = STRING) -> Optional[int]:
        """Leftmost-longest match LENGTH at ``text[pos:]``, or ``None`` — the
        substitution primitive (``${v/}`` family). 0 is a zero-width match."""
        m = _Matcher(text, profile.for_pathname, profile.ic)
        ends = m.reach(self.root, pos)
        return (max(ends) - pos) if ends else None

    def matching_spans(self, text: str,
                       profile: MatchProfile = STRING) -> Iterator[Tuple[int, int]]:
        """Left-to-right leftmost-longest non-overlapping match spans
        ``(start, end)`` over *text* — the ``${v//}`` global-substitution walk.
        Zero-width matches advance by one; the consumer applies bash's
        end-of-subject empty-match policy."""
        pos = 0
        n = len(text)
        while pos <= n:
            length = self.span_at(text, pos, profile)
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
