"""Compiled shell-pattern engine: one AST, parsed once, matched with memoization.

Historically psh matched shell patterns two ways, each exponential on a
different adversarial input (expansion appraisal finding #6):

* the **regex** backend (``extglob._convert_pattern`` → Python ``re``) blows up
  on ambiguous repetition with a forced-fail tail — ``*(a|aa)c`` on ``"a"*N+"b"``
  is catastrophic backtracking;
* the **backtracking matcher** (``extglob._match_from``) recomputes
  ``(pattern-position, subject-index)`` states with no memo and re-parses the
  pattern string on every visit — ``?(a)…?(a)!(z)`` fans out exponentially.

This module replaces both with a single design:

1. :func:`compile_pattern` parses a shell glob/extglob pattern **once** into a
   small AST (:class:`Sequence` of :class:`Literal` / :class:`AnyChar` /
   :class:`Star` / :class:`Bracket` / :class:`Extglob` nodes). Parsing reuses
   the same scanning primitives the old engines shared (matching-paren finder,
   ``|``-splitter, bracket-end finder), so bracket/escape/nesting semantics
   cannot drift.
2. :func:`reachable_ends` (this file's matcher, added alongside) evaluates each
   ``(node, subject-index)`` state at most once, returning the set of subject
   positions a node can consume to — which natively serves full match, prefix
   and suffix removal, leftmost-longest substitution, and negation.

The compiled AST carries no locale or policy state: ``for_pathname`` (whether
``*``/``?`` cross ``/``) and ``ic`` (``nocasematch`` folding) are supplied at
match time, exactly as the legacy matcher took them, so one compiled pattern is
reusable across contexts. Bracket membership still delegates to the shared,
locale-aware ``extglob._bracket_match`` (which resolves POSIX ``[:class:]`` via
the locale service), so v0.655 class semantics are preserved byte-for-byte.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Tuple

# Reuse the scanning primitives AND the char-level predicates the two legacy
# engines already shared, so the compiled engine cannot disagree with them on
# paren matching, alternative splitting, where a bracket expression ends,
# bracket membership (locale-aware POSIX classes), or case folding.
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
    stay identical to the rest of the shell.
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


# --- compiler --------------------------------------------------------------

def compile_pattern(pattern: str, *, extglob: bool = True,
                    for_pathname: bool = False) -> Sequence:
    """Parse a shell glob/extglob *pattern* into a :class:`Sequence` AST.

    ``extglob`` False makes the prefixes ``?*+@!`` ordinary (only ``?`` and
    ``*`` keep their glob meaning), matching ``extglob._convert_pattern``'s
    ``extglob=False`` mode used when the shopt is off. ``for_pathname`` is
    accepted for symmetry with the legacy API but is a match-time policy (it
    does not change the AST), so it is not stored here.
    """
    return _parse(pattern, 0, len(pattern), extglob)


def _parse(pattern: str, start: int, end: int, extglob: bool) -> Sequence:
    """Compile ``pattern[start:end]`` into a Sequence."""
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
    across a loop / many subjects). ``for_pathname`` is not a key because it
    does not affect the AST (it is a match-time policy)."""
    return compile_pattern(pattern, extglob=extglob)


# --- memoized matcher ------------------------------------------------------
#
# Reachable-end-position-set semantics: ``reachable_ends(root, s)`` returns every
# index ``k`` such that the whole pattern fully matches ``s[:k]``. This is the
# same contract the legacy backtracking matcher (extglob._extglob_consume)
# exposed, and it directly serves every consumer:
#   * full match          -> len(s) in reachable_ends(root, s)
#   * prefix removal (#/##) -> min/max of reachable_ends(root, s)
#   * suffix removal (%/%%) -> scan start i, test fullmatch of s[i:]
#   * leftmost-longest sub  -> match_at(root, s, pos) = max ends of s[pos:]
#   * pathname component    -> fullmatch(root, entry, for_pathname=True)
#
# The single change from the legacy matcher that kills the exponential blow-up
# is MEMOIZATION: each (sequence, element-index, subject-index) state is
# evaluated at most once. ``for_pathname`` and ``ic`` are constant for one match
# call, so they live on the Matcher rather than in the memo key.


class _Matcher:
    """One reachable-position match of a compiled pattern against one subject.

    A fresh instance (and memo) is created per match call. ``states`` counts
    distinct evaluated ``(sequence, index, position)`` states (memo misses) —
    the polynomial-complexity guard the performance tests assert on.
    """

    __slots__ = ("s", "n", "fp", "ic", "memo", "states")

    def __init__(self, s: str, for_pathname: bool, ic: bool) -> None:
        self.s = s
        self.n = len(s)
        self.fp = for_pathname
        self.ic = ic
        self.memo: dict = {}
        self.states = 0

    def match_seq(self, seq: Sequence, ei: int, si: int) -> frozenset:
        """Reachable end indices matching ``seq.elements[ei:]`` from ``s[si]``."""
        key = (id(seq), ei, si)
        cached = self.memo.get(key)
        if cached is not None:
            return cached
        self.states += 1
        elements = seq.elements
        if ei == len(elements):
            result = frozenset((si,))
            self.memo[key] = result
            return result

        node = elements[ei]
        s, n, fp, ic = self.s, self.n, self.fp, self.ic
        out: set = set()

        if isinstance(node, Literal):
            if si < n and _eq(s[si], node.char, ic):
                out |= self.match_seq(seq, ei + 1, si + 1)
        elif isinstance(node, AnyChar):
            if si < n and (not fp or s[si] != '/'):
                out |= self.match_seq(seq, ei + 1, si + 1)
        elif isinstance(node, Star):
            end = si
            while True:
                out |= self.match_seq(seq, ei + 1, end)
                if end >= n or (fp and s[end] == '/'):
                    break
                end += 1
        elif isinstance(node, Bracket):
            if (si < n and (not fp or s[si] != '/')
                    and _bracket_match(node.content, s[si], ic)):
                out |= self.match_seq(seq, ei + 1, si + 1)
        elif isinstance(node, Extglob):
            for mid in self._element_ends(node, si):
                out |= self.match_seq(seq, ei + 1, mid)
        else:  # pragma: no cover - defensive
            raise TypeError(f"not a pattern node: {node!r}")

        result = frozenset(out)
        self.memo[key] = result
        return result

    def _element_ends(self, node: Extglob, si: int) -> set:
        """End indices after matching ONE extglob element ``op(alts)`` from si."""
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
        # alternative. This is the case a regex cannot express.
        positive = self._alt_ends(alts, si)
        out = set()
        s, fp = self.s, self.fp
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
            out |= self.match_seq(alt, 0, si)
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


def reachable_ends(root: Sequence, s: str, *, for_pathname: bool = False,
                   ic: bool = False) -> frozenset:
    """Every index ``k`` such that *root* fully matches ``s[:k]``."""
    return _Matcher(s, for_pathname, ic).match_seq(root, 0, 0)


def fullmatch(root: Sequence, s: str, *, for_pathname: bool = False,
              ic: bool = False) -> bool:
    """Whether *root* matches the whole of *s*."""
    return len(s) in reachable_ends(root, s, for_pathname=for_pathname, ic=ic)


def match_at(root: Sequence, s: str, pos: int, *, for_pathname: bool = False,
             ic: bool = False):
    """Leftmost-longest match LENGTH of *root* at ``s[pos:]``, or None.

    Used by the substitution operators (``${v/pat/r}``): bash takes the longest
    match at the leftmost position, so this returns ``max`` of the reachable
    ends of ``s[pos:]``.
    """
    ends = reachable_ends(root, s[pos:], for_pathname=for_pathname, ic=ic)
    return max(ends) if ends else None


def count_states(root: Sequence, s: str, *, for_pathname: bool = False,
                 ic: bool = False) -> int:
    """Number of distinct ``(sequence, index, position)`` states evaluated for a
    full-pattern match of *s* — the polynomial-complexity guard for tests."""
    m = _Matcher(s, for_pathname, ic)
    m.match_seq(root, 0, 0)
    return m.states


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
