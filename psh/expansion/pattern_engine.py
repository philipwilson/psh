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
   reachable-end set serves ``full_match``, ``matching_ends`` (prefix
   removal), and ``span_at`` / ``spanner`` (leftmost-longest substitution;
   ``matching_spans`` is a labelled PERMANENT test-pinned relation oracle with
   no production caller — see its docstring). ``matching_starts`` (suffix
   removal) is the ONE relation the forward set cannot serve in one pass — it
   asks about every START, not every end — so it runs the BACKWARD twin,
   :meth:`_Matcher._starts`, a single right-to-left fold that answers all
   start positions at once instead of one forward DP per start. ``spanner``
   uses the same backward pass as a pre-filter for extglob-free patterns, so
   a subject with no match costs one pass rather than one DP per position.
3. EXCEPT for bash-composition patterns (slot 3.1): where an extglob group
   sits directly after a wildcard run, bash 5.2's measured semantics are
   SLICE-END-RELATIVE (the star case's strict continuation bounds, its
   ``?(``/``*(`` try-then-skip branches, and the unenclosed-negation
   end-of-string rule — ``lib/glob/sm_loop.c``), so "matches ``text[i:k]``"
   is a per-``(i, k)`` boolean that no single forward pass can produce.
   These patterns also see bash's glibc star-JUMP (the star scan's inner
   walk stops at the next wildcard star and COMMITS that position, placing
   a simple-element segment between stars at its LEFTMOST match — earlier
   stars never retry), which decides the entry position those rules see.
   :func:`_seq_bash_quirk` routes exactly those patterns to
   :class:`_BashMatcher` (a memoized port of the measured model; exactness
   is SCOPED to the measured corpus — 437,811 cells over the slot's three
   deterministic corpora incl. a disjoint-alphabet mirror, 0 mismatches —
   permanently locked by ``test_pattern_bash_composition_differential.py``'s
   grammar-v2 battery), and the relations evaluate them as per-slice
   booleans. Every other pattern keeps the fast paths above unchanged.
   Flagged-pattern recursion is bounded by PATTERN structure (group
   dispatches + nesting; star-run scanning and jump commits are iterative),
   never subject length.

The compiled AST carries no locale or policy state: :class:`MatchProfile`
supplies ``for_pathname`` (whether ``*``/``?`` cross ``/``) and ``ic``
(``nocasematch``/``nocaseglob`` folding) at match time, so one compiled pattern
is reusable across contexts. Bracket membership still delegates to the shared,
locale-aware ``extglob._bracket_match`` (which resolves POSIX ``[:class:]`` via
the locale service), so class semantics are preserved byte-for-byte.

The compiled AST is also IMMUTABLE (#20 MEDIUM-6). Every node is a frozen
dataclass and the four routing bits are derived at construction, because
compiles are CACHED: one compile's result is handed to every later caller with
the same key, so a caller that mutated a node poisoned every subsequent cache
hit. THREAT MODEL: the freeze prevents HONEST-CALLER ACCIDENT, not adversarial
bypass — a normal attribute write raises ``FrozenInstanceError``, while
``object.__setattr__`` and module-attribute rebinding remain possible and are
deliberately out of scope (Python freezing is leaky by construction, so
pinning their impossibility would pin a falsehood). Pinned by
``tests/unit/expansion/test_pattern_engine_immutability.py``.
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
# Nodes are FROZEN dataclasses matched by object identity: the matcher memoizes
# on ``id(node)`` so each node created by one compile is a distinct state.
# ``eq=False`` keeps identity semantics and leaves ``__hash__`` as object's,
# which the round-trip tests and the matcher's memo rely on.
#
# WHY FROZEN (#20 MEDIUM-6): compiles are CACHED (:func:`compile_cached`, and
# ``parameter_expansion._sub_machinery_cached`` above it), so one compile's
# result is handed to every later caller with the same key. While nodes were
# mutable, a caller that wrote to one — ``node.char = 'z'``, or a routing bit
# like ``seq.bash_quirk`` — POISONED every subsequent cache hit, observable
# through ordinary shell execution (``${v//abc/HIT}`` silently ceasing to
# match its own subject). Freezing makes that write raise instead.
#
# THREAT MODEL (ruled): the freeze prevents HONEST-CALLER ACCIDENT, not
# adversarial bypass. A normal attribute write raises ``FrozenInstanceError``;
# ``object.__setattr__`` and module-attribute rebinding remain possible and are
# deliberately OUT OF SCOPE — Python freezing is leaky by construction, and
# pinning "no adversarial bypass" would pin a falsehood. The behavioral
# criterion pinned is: a caller CANNOT mutate the result of one compile and
# affect a later match (``test_pattern_engine_immutability.py``).

@dataclass(frozen=True, eq=False, slots=True)
class Literal:
    """A single literal character (a plain char, or the target of a ``\\``)."""
    char: str


@dataclass(frozen=True, eq=False, slots=True)
class AnyChar:
    """``?`` — matches exactly one character (not ``/`` when for_pathname)."""


@dataclass(frozen=True, eq=False, slots=True)
class Star:
    """``*`` — matches zero or more characters (not ``/`` when for_pathname)."""


@dataclass(frozen=True, eq=False, slots=True)
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


@dataclass(frozen=True, eq=False, slots=True)
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


@dataclass(frozen=True, eq=False, slots=True)
class Sequence:
    """An ordered run of nodes; the compiled form of a whole pattern or one
    extglob alternative.

    The four routing bits are DERIVED AT CONSTRUCTION, not lazily on first
    query: the node is frozen, so there is nowhere to cache a late answer, and
    a write-once slot would only re-introduce the mutable surface the freeze
    exists to remove. They are pure functions of ``elements`` (see the
    ``_derive_*`` helpers), so computing them eagerly cannot change any
    answer — an equivalence guard in the slot's proof asserts precomputed ==
    the former lazy derivation over the whole corpus.

    The derivation is NON-RECURSIVE: a child Sequence is fully constructed
    before its parent, so each bit is read from the children in O(1) rather
    than recursing into them. Construction therefore costs O(len(elements))
    per node regardless of extglob NESTING depth — which is what keeps
    ``test_pattern_relations.py``'s iteratively-built 2,000-deep AST
    constructible while still raising ``RecursionError`` at MATCH time.

    ``has_extglob`` — routing hint: a sequence with no :class:`Extglob`
    element is matched by the fully iterative fast paths (two-pointer boolean
    / forward DP), never recursing at all.

    ``bash_quirk`` — bash-composition routing flag: only a sequence in which
    an extglob group sits directly after a wildcard run (here or in any nested
    alternative) routes to the measured-composition matcher
    (:class:`_BashMatcher`); every other pattern keeps the fast paths.

    ``sub_fast`` — substitution Path-A eligibility (see
    :func:`sub_fast_eligible`). ``nullable`` — whether the sequence can match
    the empty string (see :func:`_derive_nullable`); it is a stored bit only
    so that ``sub_fast`` can be derived without recursion.
    """
    elements: Tuple[object, ...] = field(default_factory=tuple)
    has_extglob: bool = field(init=False, default=False)
    bash_quirk: bool = field(init=False, default=False)
    sub_fast: bool = field(init=False, default=False)
    nullable: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        # The documented frozen-dataclass idiom for derived fields. This is
        # the class's OWN constructor, not a caller reaching in: the freeze
        # it establishes is exactly what the threat model promises callers.
        setattr_ = object.__setattr__
        elements = self.elements
        setattr_(self, 'has_extglob', _derive_has_extglob(elements))
        setattr_(self, 'nullable', _derive_nullable(elements))
        setattr_(self, 'bash_quirk', _derive_bash_quirk(elements))
        setattr_(self, 'sub_fast', _derive_sub_fast(elements))


# --- construction-time derivations of the four routing bits ----------------
#
# Each reads its children's ALREADY-DERIVED bits instead of recursing, so the
# cost is O(len(elements)) per node and independent of nesting depth.

def _derive_has_extglob(elements: Tuple[object, ...]) -> bool:
    """Whether *elements* contains an :class:`Extglob` element."""
    return any(type(e) is Extglob for e in elements)


def _seq_has_extglob(seq: Sequence) -> bool:
    """Whether *seq* contains an :class:`Extglob` element (derived at
    construction; this is the stable read-side name every consumer uses)."""
    return seq.has_extglob


def _derive_nullable(elements: Tuple[object, ...]) -> bool:
    """Whether *elements* can match the empty string.

    Star is nullable; Literal/AnyChar/Bracket are not; an Extglob is
    nullable iff its op is ``?``/``*`` or (``@``/``+``) with a nullable
    alternative; ``!`` is treated as nullable (its complement usually
    admits the empty span) — callers that need ``!`` excluded do so
    separately (see :func:`sub_fast_eligible`). Alternatives are read via
    their own already-derived ``nullable`` bit, never re-walked."""
    for e in elements:
        t = type(e)
        if t is Star:
            continue
        if t is Extglob:
            eg = cast(Extglob, e)
            if eg.op in '?*!':
                continue
            if any(a.nullable for a in eg.alts):
                continue
            return False
        return False
    return True


# ``_seq_nullable(seq)`` was RETIRED here: once the bit moved to construction
# time its body was ``return seq.nullable``, with zero callers and zero tests
# (its one remaining mention was a docstring cross-reference, now pointing at
# :func:`_derive_nullable`). Read ``seq.nullable`` directly. Its sibling
# :func:`_seq_has_extglob` KEEPS its wrapper — that one still has a live
# caller, so the name is load-bearing there and not here.


def sub_fast_eligible(seq: Sequence) -> bool:
    """Round-2 Path A eligibility (R10 B2-2): every extglob group in *seq*
    — at any nesting depth — is NON-NEGATION and NON-NULLABLE.

    For such patterns the substitution consumer layer's mechanisms are
    vacuous or reducible (no zero-width group matches exist, so the
    empty-position gate, the empty-subject single-shot and the end-of-
    subject policy cannot fire differently, and the ``*pat*`` pre-test
    reduces to "a substring match exists"), so the consumer may run the
    LINEAR direct scan instead of the per-suffix bash machinery.
    Equivalence is not argued from this docstring: it is MEASURED — the
    slot's corpus-union equivalence proof (0 disagreements over every
    eligible cell x four operators) and the battery's boundary test.
    Derived from compiled-node properties only, at construction
    (``Sequence.sub_fast``)."""
    return seq.sub_fast


def _derive_sub_fast(elements: Tuple[object, ...]) -> bool:
    """Construction-time derivation of :func:`sub_fast_eligible`.

    "At any nesting depth" is carried by the children's OWN already-derived
    ``sub_fast``/``nullable`` bits rather than by recursion."""
    for e in elements:
        if type(e) is Extglob:
            eg = cast(Extglob, e)
            if (eg.op == '!' or eg.op in '?*'
                    or any(a.nullable for a in eg.alts)
                    or not all(a.sub_fast for a in eg.alts)):
                return False
    return True


def _seq_bash_quirk(seq: Sequence) -> bool:
    """Whether *seq* needs the measured bash-composition matcher.

    True iff an :class:`Extglob` element follows a wildcard run containing a
    :class:`Star` — directly, or with intervening ``?``/``*`` wildcards —
    at this level or inside any nested alternative. Exactly these shapes are
    where bash 5.2's measured semantics diverge from the reachability DP
    (measured scope: see below):
    the star case's strict continuation bounds, its ``?(``/``*(``
    try-then-skip branches, and the end-of-string negation rule are all
    slice-end-relative, so they cannot ride one forward reachability pass.
    Derived at construction (same as ``has_extglob``).

    "Exactly these shapes" is a claim SCOPED to the slot's measured corpora
    (437,811 cells across the three deterministic corpora + the widened
    grammar-v2 battery): zero divergence was measured outside the flagged
    class there; the battery keeps that scope pinned.

    This flag is also the EXACT exclusion predicate for the regex-oracle
    agreement corpus in ``test_pattern_engine_matcher.py`` (the regex model
    cannot express bash's star∘group composition) — one decider, imported
    there, never re-derived (R3).
    """
    return seq.bash_quirk


def _derive_bash_quirk(elements: Tuple[object, ...]) -> bool:
    """Construction-time derivation of :func:`_seq_bash_quirk`.

    Nested alternatives contribute through their OWN already-derived
    ``bash_quirk`` bit ("or inside any nested alternative"), not recursion."""
    star_run = False
    for e in elements:
        t = type(e)
        if t is Star:
            star_run = True
        elif t is AnyChar:
            pass  # a '?' rides an active wildcard run (bash collapses it)
        elif t is Extglob:
            eg = cast(Extglob, e)
            if star_run or any(a.bash_quirk for a in eg.alts):
                return True
            star_run = False
        else:
            star_run = False
    return False


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
# TWO DUAL POSITION-SET PASSES, forward and backward.
#
# Forward — ``_ends(seq, ei, si)`` returns every index ``k`` such that
# ``seq.elements[ei:]`` fully matches ``s[si:k]``. It serves the relations that
# fix a START and ask about ends:
#   * full match            -> len(s) in ends
#   * prefix removal (#/##) -> min/max of matching_ends
#   * leftmost-longest sub  -> span_at(pos) = max ends of s[pos:]
#   * pathname component    -> full_match(entry, for_pathname=True)
#
# Backward — ``_starts(seq, end)`` returns every index ``i`` such that *seq*
# fully matches ``s[i:end]``. Suffix removal fixes the END and asks about
# STARTS, which the forward pass can only answer one start at a time; running
# it per start is what made ``%``/``%%`` quadratic (and CUBIC on quirk-flagged
# patterns) before #20 HIGH-7's perf half:
#   * suffix removal (%/%%) -> matching_starts = one _starts pass
# ``spanner`` also uses ``_starts`` as an all-start PRE-FILTER, but only for
# extglob-free patterns — see its docstring for why the gate is about cost.
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


class _Instrumentation:
    """Process-wide counters for complexity pins (test instrumentation).

    ``matchers`` counts matcher CONSTRUCTIONS. It exists because the
    substitution consumer's linearity is a SHARING property, not a per-call
    one: bash's mechanics are per-remaining-suffix, and the cheap way to get
    them wrong is to build a fresh matcher (and copy the subject) for every
    suffix — which no per-call transition count can see, since each individual
    call stays small. Counting constructions makes "one matcher for the whole
    scan" directly assertable (mutation class M7).

    ``record``/``instances`` support :func:`operation_transitions`, which
    totals the work of a WHOLE consumer operation. A relation-level counter
    cannot stand in for that: :func:`count_transitions`'s ``'scan'`` mode walks
    EVERY position, whereas ``${v//pat/r}`` JUMPS past each match — so on a
    MATCHING subject the two measure different things, and the scan mode
    reports the no-match cost. Recording is off by default and costs a branch.
    """

    __slots__ = ("matchers", "record", "instances")

    def __init__(self) -> None:
        self.matchers = 0
        self.record = False
        self.instances: List[object] = []


#: Shared counter object; tests read and reset it, production only increments.
INSTRUMENTATION = _Instrumentation()


class _Matcher:
    """One match of a compiled pattern against one subject.

    A fresh instance is created per relation call (the substitution
    ``spanner`` reuses one across entry positions). ``states`` counts
    (element, position) evaluations in the forward DP — the
    polynomial-complexity guard the tests assert on. ``transitions`` counts
    DP transitions in both directions and is the counter the LINEARITY pins
    assert on; see :func:`count_transitions` for why the two differ.
    """

    __slots__ = ("s", "n", "fp", "ic", "states", "transitions", "_nslash")

    def __init__(self, s: str, for_pathname: bool, ic: bool) -> None:
        self.s = s
        self.n = len(s)
        self.fp = for_pathname
        self.ic = ic
        self.states = 0
        self.transitions = 0
        self._nslash: Optional[List[int]] = None
        INSTRUMENTATION.matchers += 1
        if INSTRUMENTATION.record:
            INSTRUMENTATION.instances.append(self)

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
            self.transitions += 1
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
            self.transitions += len(positions)
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

    # -- all-start relation: ONE backward pass over the elements -------------

    def _starts(self, seq: Sequence, end: int) -> frozenset:
        """Every ``i`` such that *seq* matches EXACTLY ``s[i:end]``.

        The BACKWARD twin of :meth:`_ends`, and the reason suffix removal is
        no longer quadratic: ``cur`` is the characteristic vector of
        ``S_j = { p : elements[j:] matches s[p:end] }``, seeded ``S_ne={end}``
        and folded right-to-left, so ONE pass answers every start position at
        once instead of running a forward DP per start (#20 HIGH-7 perf
        half). Each plain element is a single O(end) scan; a non-pathname
        Star is the downward closure ``[0, max(S_{j+1})]`` (a star reaches any
        later position), and under for_pathname it stops at the next ``/``,
        which it cannot consume. Only an Extglob element still pays the
        per-position :meth:`_element_ends` — the recursion bound and the
        extglob cost model are unchanged.
        """
        elements = seq.elements
        s, fp, ic = self.s, self.fp, self.ic
        cur = bytearray(end + 1)
        cur[end] = 1
        for idx in range(len(elements) - 1, -1, -1):
            node = elements[idx]
            t = type(node)
            nxt = bytearray(end + 1)
            self.transitions += end + 1
            if t is Literal:
                ch = cast(Literal, node).char
                for p in range(end):
                    if cur[p + 1] and _eq(s[p], ch, ic):
                        nxt[p] = 1
            elif t is AnyChar:
                for p in range(end):
                    if cur[p + 1] and (not fp or s[p] != '/'):
                        nxt[p] = 1
            elif t is Bracket:
                content = cast(Bracket, node).content
                for p in range(end):
                    if (cur[p + 1] and (not fp or s[p] != '/')
                            and _bracket_match(content, s[p], ic)):
                        nxt[p] = 1
            elif t is Star:
                if not fp:
                    hi = -1
                    for q in range(end, -1, -1):
                        if cur[q]:
                            hi = q
                            break
                    if hi >= 0:
                        for p in range(hi + 1):
                            nxt[p] = 1
                else:
                    ns = self._next_slash()
                    for p in range(end + 1):
                        limit = ns[p]
                        if limit > end:
                            limit = end
                        for q in range(p, limit + 1):
                            if cur[q]:
                                nxt[p] = 1
                                break
            else:  # Extglob: per-position element ends (unchanged cost model)
                for p in range(end + 1):
                    for q in self._element_ends(cast(Extglob, node), p):
                        if q <= end and cur[q]:
                            nxt[p] = 1
                            break
            cur = nxt
            if 1 not in cur:
                return _EMPTY
        return frozenset(i for i in range(end + 1) if cur[i])

    def _element_ends(self, node: Extglob, si: int) -> set:
        """End indices after matching ONE extglob element ``op(alts)`` @ si.

        This is PER-POSITION work, and it is where an extglob element's real
        cost lives: a caller that asks it at every subject position (the
        backward pass's Extglob branch, or a per-position scan) pays whatever
        this costs, n times over. It is therefore COUNTED — the negation
        branch's span walk especially. Leaving it uncounted let the counter
        certify `!(a)b` as linear while its wall time was quadratic, which is
        the same blindness ``count_states`` already demonstrates one level up.
        """
        self.transitions += 1
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
            self.transitions += 1
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
                self.transitions += 1
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
# matcher is a faithful port of the MEASURED model; exactness is SCOPED to
# the slot's measured corpora (437,811 cells vs live bash 5.2.26 across
# corpus1/2/3 incl. a disjoint-alphabet mirror, 0 mismatches — ledger A4 +
# C-2; permanently enforced by the grammar-v2 battery in
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
#     '!' = per-split complement AND continuation;
#   * the glibc star-JUMP (round 1): the general scan's inner walk
#     (_segment, = GMATCH-with-&end) STOPS at the next wildcard star and
#     COMMITS that position — a simple-element segment between stars is
#     placed at its LEFTMOST match and earlier stars never retry; groups
#     are jump-opaque (EXTMATCH passes NULL ends). Invisible to plain
#     patterns; decisive for the entry position the rules above see.
#
# Recursion here is bounded by the PATTERN structure (one frame per group
# dispatch, plus alt nesting; star-run scanning and jump commits are
# iterative) — never by subject length or star count.
#
# TWO memos keep the evaluation polynomial, and they guard different things.
# The per-(sequence, element, si, se) memo bounds how many distinct states are
# ever EVALUATED. It does NOT bound how often they are RE-WALKED, and that gap
# was a real cubic: the `*`/`+` closure used to be rebuilt from scratch at
# every star entry position, O(n^2) of re-walking per entry over O(n) entries,
# with every lookup inside it already a memo hit. `_ok_table` memoizes that
# closure per (group, element, slice-end), which is what returns the
# `**(a)b` class to a quadratic bound.
#
# Consequently `count_states` (which counts memo MISSES) is NOT the complexity
# guard for this matcher — it was quadratic-by-construction while the running
# time was cubic, and its pin passed with ~50% headroom throughout. The guard
# is `count_transitions`, which counts work including memo HITS; `states`
# remains as a memo-coverage guard only.


class _BashMatcher:
    """One subject × one profile evaluation of a bash-quirk pattern.

    ``match(seq, ei, si, se)`` — do ``seq.elements[ei:]`` match exactly
    ``s[si:se]`` under the measured bash-5.2 composition semantics. One
    instance is shared across a whole relation call (all slice bounds), so
    the memo carries across the per-k loops. ``states`` counts uncached
    evaluations; ``transitions`` counts WORK (loop steps, including steps that
    end in a memo HIT) — the two differ by a whole complexity class here, see
    :func:`count_transitions`."""

    __slots__ = ("s", "fp", "ic", "memo", "states", "transitions", "_ok")

    def __init__(self, s: str, for_pathname: bool, ic: bool) -> None:
        self.s = s
        self.fp = for_pathname
        self.ic = ic
        self.memo: dict = {}
        self.states = 0
        self.transitions = 0
        self._ok: dict = {}
        INSTRUMENTATION.matchers += 1
        if INSTRUMENTATION.record:
            INSTRUMENTATION.instances.append(self)

    def match(self, seq: Sequence, ei: int, si: int, se: int) -> bool:
        # Counted on EVERY call, hit or miss. Re-walking positions whose
        # answers are already memoized is the cost that made this matcher
        # cubic, and counting only misses (``states``) cannot see it. Counting
        # at the one door every evaluation strategy must pass through also
        # keeps the pin honest against a REWRITE of the loops above: an
        # implementation that re-queries more must report more, whatever shape
        # its loops take (mutation class M3).
        self.transitions += 1
        key = (id(seq), ei, si, se)
        r = self.memo.get(key)
        if r is None:
            self.states += 1
            r = self._match(seq, ei, si, se)
            self.memo[key] = r
        return r

    # -- closure reachability, computed ONCE per (group, gi, se) -------------

    def _ok_table(self, node: Extglob, seq: Sequence, gi: int,
                  se: int) -> bytearray:
        """``ok[p]`` — can the REST of *seq* match, entering the closure of
        ``node``'s alternatives at *p* and ending at *se*?

        ``ok(p) = rest(p) or ∃q>p: alt_span(p,q) ∧ ok(q)`` — the same relation
        the former ``_closure`` built as an explicit position set, unrolled as
        a backward DP. The point is the MEMO: the star case dispatches a group
        at O(n) entry positions, and each dispatch used to rebuild the whole
        closure — O(n²) of re-walking per entry, O(n³) overall, even though
        every ``alt_span`` inside it was already a memo hit. Keyed by
        ``(group, gi, se)``, the table is built once and read O(1) thereafter,
        which is what returns the ``**(a)b`` class to a polynomial bound.
        ``+`` reuses the same table behind its nonempty-seed test.
        """
        key = (id(node), gi, se)
        tbl = self._ok.get(key)
        if tbl is None:
            alts = node.alts
            tbl = bytearray(se + 2)
            for p in range(se, -1, -1):
                self.transitions += 1
                r = self.match(seq, gi + 1, p, se)
                if not r:
                    for q in range(p + 1, se + 1):
                        self.transitions += 1
                        if tbl[q] and self._alt_span(alts, p, q):
                            r = True
                            break
                tbl[p] = 1 if r else 0
            self._ok[key] = tbl
        return tbl

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
            # Star: the bash star case. The outer loop below is the glibc
            # star-JUMP (sm_loop.c L150-155/L313/L324-329, found in round 1):
            # the general scan's inner walk STOPS at the next wildcard star
            # and COMMITS that position — a simple-element segment between
            # stars is placed at its LEFTMOST match and earlier stars never
            # retry. Invisible to plain patterns; decisive for which entry
            # position a later wildcard-run's rules (the end-of-string
            # negation special, the ?(/*( branches) see.
            i += 1
            while True:  # star-entry loop; re-entered on a jump commit
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
                        if self._extmatch(cast(Extglob, node2), seq, i, n,
                                          se):
                            return True
                        # group failed: SKIP it, continue the run
                    elif t2 is Extglob and cast(Extglob, node2).op == '*':
                        if fp and n < se and s[n] == '/':
                            return False
                        for n2 in range(n, se):  # strictly before slice end
                            if self._extmatch(cast(Extglob, node2), seq, i,
                                              n2, se):
                                return True
                    else:
                        break  # first element the run cannot absorb
                    i += 1
                    if i >= ne:
                        return True  # run (incl. skips) consumed the pattern
                # node2 = first non-run element, at index i.
                if (t2 is Extglob and cast(Extglob, node2).op == '!'
                        and n == se):
                    # End-of-string negation rule at THIS (jump-committed)
                    # entry position: unconditional, rest ignored.
                    return not cast(Extglob, node2).enclosed
                if fp and t2 is Literal and cast(Literal, node2).char == '/':
                    # [star]/rest: consume up to a slash, match the rest.
                    m2 = s.find('/', n, se)
                    if m2 != -1:
                        return self.match(seq, i + 1, m2 + 1, se)
                    return False
                bound = se
                if fp:
                    m2 = s.find('/', n, se)
                    if m2 != -1:
                        bound = m2  # a star never crosses '/'
                jump = None
                for n2 in range(n, bound):  # strictly before the slice end
                    self.transitions += 1
                    verdict, jn, jj = self._segment(seq, i, n2, se)
                    if verdict == 1:
                        return True
                    if verdict == 2:
                        jump = (jn, jj)
                        break
                    # verdict 0: this start fails; try the next
                if jump is None:
                    return False
                n, i = jump
                i += 1  # past the committed star; re-enter the entry loop
        return n == se

    def _segment(self, seq: Sequence, j: int, m: int, se: int):
        """The star general-scan's inner walk (GMATCH with ``&end`` in C).

        Walk ``seq.elements[j:]`` matching ``s`` at *m*. Returns
        ``(verdict, n, j)``: 1 = matched through to both ends; 2 = reached
        a wildcard :class:`Star` — the JUMP, with the committed subject
        position and the star's element index; 0 = mismatch (the caller
        tries the next start position). An :class:`Extglob` dispatches
        ``_extmatch`` with the full continuation and is FINAL for this
        start (EXTMATCH passes NULL ends in C — no jump through groups)."""
        s, fp, ic = self.s, self.fp, self.ic
        elements = seq.elements
        ne = len(elements)
        while j < ne:
            self.transitions += 1
            node = elements[j]
            t = type(node)
            if t is Extglob:
                return ((1 if self._extmatch(cast(Extglob, node), seq, j, m,
                                             se) else 0), m, j)
            if t is Star:
                return (2, m, j)
            if t is Literal:
                if m < se and _eq(s[m], cast(Literal, node).char, ic):
                    m += 1
                    j += 1
                    continue
                return (0, m, j)
            if t is AnyChar:
                if m < se and (not fp or s[m] != '/'):
                    m += 1
                    j += 1
                    continue
                return (0, m, j)
            # Bracket
            if (m < se and (not fp or s[m] != '/')
                    and _bracket_match(cast(Bracket, node).content,
                                       s[m], ic)):
                m += 1
                j += 1
                continue
            return (0, m, j)
        return ((1 if m == se else 0), m, j)

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
                self.transitions += 1
                if self._alt_span(alts, si, split) and rest_ok(split):
                    return True
            return False
        if op == '?':
            if rest_ok(si):
                return True
            for split in range(si, se + 1):
                self.transitions += 1
                if self._alt_span(alts, si, split) and rest_ok(split):
                    return True
            return False
        if op == '*':
            return bool(self._ok_table(node, seq, gi, se)[si])
        if op == '+':
            # One-or-more: SOME first instance, then the closure from there.
            # The first instance may be EMPTY when an alternative matches the
            # empty string — ``split`` starts at ``si``, matching the retired
            # ``_closure`` seed, which was built from the same inclusive
            # ``range(si, se + 1)``. It is the closure's own steps that are
            # constrained to be nonempty.
            tbl = self._ok_table(node, seq, gi, se)
            for split in range(si, se + 1):
                self.transitions += 1
                if tbl[split] and self._alt_span(alts, si, split):
                    return True
            return False
        # op == '!': per-split complement AND continuation.
        for split in range(si, se + 1):
            self.transitions += 1
            if not self._alt_span(alts, si, split) and rest_ok(split):
                return True
        return False

    def _alt_span(self, alts: Tuple[Sequence, ...], a: int, b: int) -> bool:
        """Whether some alternative fully matches the span ``s[a:b]``."""
        return any(self.match(alt, 0, a, b) for alt in alts)

    # ``_closure`` (explicit reachable-position set, rebuilt per group
    # dispatch) was RETIRED in favour of :meth:`_ok_table`, which decides the
    # same relation — "some position reachable from p by zero-or-more nonempty
    # alternative spans satisfies the continuation" — memoized per
    # ``(group, gi, se)`` instead of recomputed per entry position. Its two
    # callers were the ``*`` and ``+`` branches of :meth:`_extmatch`, both
    # rewritten above; the equivalence is corpus-proven, not argued.


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
    *s* — the polynomial-complexity guard for tests (both matcher paths).

    This counts MEMO KEYS (uncached evaluations). It is the right guard for
    "the memo still covers the state space", which is what its pins assert —
    but see :func:`count_transitions` for why it is NOT a work counter."""
    if _seq_bash_quirk(root):
        bm = _BashMatcher(s, for_pathname, ic)
        bm.match(root, 0, 0, len(s))
        return bm.states
    m = _Matcher(s, for_pathname, ic)
    m.reach(root, 0)
    return m.states


def operation_transitions(fn) -> int:
    """Total DP transitions across EVERY matcher one consumer operation builds.

    The end-to-end companion to :func:`count_transitions`. A relation-level
    count cannot certify a CONSUMER: ``${v//pat/r}`` on a MATCHING subject
    jumps past each match instead of probing every position, so
    ``count_transitions(..., relation='scan')`` — which does walk every
    position — reports that operation's NO-MATCH cost rather than its real
    one. This runs *fn* with matcher recording on and sums the work actually
    done, so a claim like "global substitution on this shape is linear" is
    asserted against the operation the claim is about.
    """
    INSTRUMENTATION.instances = []
    INSTRUMENTATION.record = True
    try:
        fn()
        return sum(m.transitions                            # type: ignore[attr-defined]
                   for m in INSTRUMENTATION.instances)
    finally:
        INSTRUMENTATION.record = False
        INSTRUMENTATION.instances = []


def count_transitions(root: Sequence, s: str, *, for_pathname: bool = False,
                      ic: bool = False, relation: str = 'full') -> int:
    """Number of DP TRANSITIONS (units of loop work) for one relation call.

    Distinct from :func:`count_states`, and the distinction is the whole
    point. ``count_states`` counts memo MISSES, so work spent re-walking
    positions whose answers are already memoized is INVISIBLE to it. At the
    time this counter was added, ``_BashMatcher`` on ``**(a)b`` had a
    quadratic key count and a CUBIC running time — and the shipped
    state-count pin, being quadratic-bounded, passed at every size with ~50%
    headroom while the cubic went unnoticed. A complexity pin that cannot
    fail for the defect it names is not a pin, so the linearity guarantees
    are asserted on THIS counter, which increments per loop step including
    steps that end in a memo hit.

    ``relation`` selects what is measured: ``'full'`` (whole-subject match),
    ``'starts'`` (the all-start backward pass behind suffix removal),
    ``'ends'`` (the forward reachable-end pass behind prefix removal), or
    ``'scan'`` (ONE spanner evaluated at every position — the substitution
    consumer's leftmost scan, whose no-match case the linearity criterion
    names).
    """
    n = len(s)
    if relation == 'scan':
        # Drive the REAL consumer scan (one shared spanner, every position),
        # and read the counter off the matcher that scan actually used.
        profile = MatchProfile(for_pathname=for_pathname, ic=ic)
        span_at = CompiledPattern(root).spanner(s, profile)
        for pos in range(n + 1):
            span_at(pos)
        return int(span_at.matcher.transitions)
    profile = MatchProfile(for_pathname=for_pathname, ic=ic)
    if relation == 'starts':
        return _relation_starts(root, s, n, profile)[1].transitions
    if relation == 'ends':
        return _relation_ends(root, s, 0, profile)[1].transitions
    return _relation_full(root, s, profile)[1].transitions


# --- relation bodies: ONE implementation, shared by the API and the counter -
#
# Each returns ``(result, matcher)``. The public :class:`CompiledPattern`
# method takes the result; :func:`count_transitions` takes the matcher. They
# are the SAME evaluation, which is the point: a complexity counter that
# re-derives the relation instead of observing it measures a path no consumer
# takes, and will happily stay green while the real path regresses. That is
# not hypothetical — an earlier draft of this module counted a re-derived
# suffix scan, and reverting the all-start pass to per-start evaluation did
# not move the number at all (mutation class M1).


def _relation_starts(root: Sequence, text: str, end: int,
                     profile: MatchProfile):
    """``({i : root matches text[i:end]}, matcher)`` — suffix removal."""
    if _seq_bash_quirk(root):
        bm = _BashMatcher(text, profile.for_pathname, profile.ic)
        return (frozenset(i for i in range(end + 1)
                          if bm.match(root, 0, i, end)), bm)
    m = _Matcher(text, profile.for_pathname, profile.ic)
    return m._starts(root, end), m


def _relation_ends(root: Sequence, text: str, start: int,
                   profile: MatchProfile):
    """``({k : root matches text[start:k]}, matcher)`` — prefix removal."""
    if _seq_bash_quirk(root):
        bm = _BashMatcher(text, profile.for_pathname, profile.ic)
        return (frozenset(k for k in range(start, len(text) + 1)
                          if bm.match(root, 0, start, k)), bm)
    m = _Matcher(text, profile.for_pathname, profile.ic)
    return m._ends(root, 0, start), m


def _relation_full(root: Sequence, text: str, profile: MatchProfile):
    """``(root matches the whole of text, matcher)``."""
    if _seq_bash_quirk(root):
        bm = _BashMatcher(text, profile.for_pathname, profile.ic)
        return bm.match(root, 0, 0, len(text)), bm
    m = _Matcher(text, profile.for_pathname, profile.ic)
    return m._full(root, 0, 0), m


# --- the four relations on a compiled pattern ------------------------------

@dataclass(frozen=True, eq=False, slots=True)
class CompiledPattern:
    """One parse of a shell pattern; exposes the four relations its consumers
    need. Compiled once (via :class:`PatternCompiler`), reused across subjects
    and profiles (the AST carries no policy — :class:`MatchProfile` does).

    Frozen for the same reason the nodes are: ``_sub_machinery_cached`` hands
    the SAME ``CompiledPattern`` objects to every later caller, so a rebound
    ``root`` would poison the cache (MEDIUM-6 demo 7)."""

    root: Sequence

    def full_match(self, text: str, profile: MatchProfile = STRING) -> bool:
        """Whether the pattern matches the WHOLE of *text*
        (``case`` / ``[[ == ]]`` / name filter / one pathname component /
        one character for case modification)."""
        return _relation_full(self.root, text, profile)[0]

    def matching_ends(self, text: str, start: int = 0,
                      profile: MatchProfile = STRING) -> frozenset:
        """Every end index ``k`` (``start <= k <= len(text)``) such that the
        pattern matches ``text[start:k]`` — prefix removal (``#`` = ``min``,
        ``##`` = ``max``).

        bash-quirk patterns (:func:`_seq_bash_quirk`) have slice-end-relative
        semantics, so each ``k`` is its own slice boolean (one shared
        memoized matcher); all other patterns keep the one-pass DP."""
        return _relation_ends(self.root, text, start, profile)[0]

    def matching_starts(self, text: str, end: Optional[int] = None,
                        profile: MatchProfile = STRING) -> frozenset:
        """Every start index ``i`` (``0 <= i <= end``) such that the pattern
        matches ``text[i:end]`` — suffix removal (``%`` = ``max`` start / shortest
        suffix, ``%%`` = ``min`` start / longest suffix)."""
        if end is None:
            end = len(text)
        return _relation_starts(self.root, text, end, profile)[0]

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

    def suffix_matcher(self, text: str, profile: MatchProfile = STRING):
        """Return a ``pos -> bool`` "matches ``text[pos:]`` exactly" callable
        bound to ONE reused matcher — the all-start form of ``full_match``.

        The substitution pre-test asks this question once per remaining
        suffix. Asking it as ``full_match(text[pos:])`` materialises a fresh
        string AND a fresh matcher at every scan position — O(n) copy plus a
        discarded memo, O(n) times — which is the whole residual quadratic on
        subjects with many matches. Evaluated in place against the original
        string it is the same relation (measured: 29,088 cells over both
        matcher routes, both profiles, every anchor and position, 0
        disagreements) at O(1) amortized cost."""
        root = self.root
        n = len(text)
        if _seq_bash_quirk(root):
            bm = _BashMatcher(text, profile.for_pathname, profile.ic)

            def bash_suffix_match(pos: int) -> bool:
                return bm.match(root, 0, pos, n)

            return bash_suffix_match
        m = _Matcher(text, profile.for_pathname, profile.ic)

        def suffix_match(pos: int) -> bool:
            return m._full(root, 0, pos)

        return suffix_match

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

            # The matcher doing the work, exposed so :func:`count_transitions`
            # measures THIS scan rather than a re-derived copy of it — a
            # complexity counter that does not observe the real path is the
            # failure mode ``count_states`` already demonstrates.
            bash_span_at.matcher = bm                       # type: ignore[attr-defined]
            return bash_span_at
        m = _Matcher(text, profile.for_pathname, profile.ic)
        match = m._ends

        # The pre-filter below is SOUND for every non-pathname pattern but only
        # CHEAP for some, so it is gated on cost, not on correctness.
        if profile.for_pathname or root.has_extglob:
            def unfiltered_span_at(pos: int) -> Optional[int]:
                ends = match(root, 0, pos)
                return (max(ends) - pos) if ends else None

            unfiltered_span_at.matcher = m                  # type: ignore[attr-defined]
            return unfiltered_span_at

        # ALL-START PRE-FILTER (the substitution scan's linearity).
        # The consumer walks every position asking "does a match start here?",
        # and each ask used to run a full forward DP — so a subject with NO
        # match cost one DP per position. The startable set is one BACKWARD
        # pass instead, because ``P*`` matches ``text[p:]`` EXACTLY iff ``P``
        # matches ``text[p:k]`` for some k >= p (the trailing star absorbs the
        # remainder) — so ``_starts`` of the star-extended pattern IS the set
        # of positions a match can start at. A no-match subject is then ONE
        # pass, and the forward DP runs only where a match really begins.
        #
        # GATED ON TWO CONDITIONS, both about COST:
        #  * non-pathname — under for_pathname a star cannot cross '/', so the
        #    trailing star would not absorb an arbitrary remainder and the
        #    identity above would not hold (this one IS correctness);
        #  * NO Extglob element — ``_starts`` is a single O(nodes*n) backward
        #    pass for every element type EXCEPT Extglob, whose branch pays
        #    per-position ``_element_ends``. Building the filter for an
        #    extglob-bearing pattern therefore costs O(n^2) BEFORE the first
        #    span_at, which is a net loss and, inside the substitution fast
        #    path, turned linear eligible-pattern substitutions quadratic
        #    (``${v//+([[:space:]])/-}`` on ' '*3200: 0.008s -> 11.9s). Top-
        #    level ``has_extglob`` is the right predicate because a nested
        #    group cannot exist without a containing top-level Extglob element,
        #    and the probe sequence adds only a Star.
        #
        # CONSEQUENCE, stated where the claim is made: the "no-match
        # substitution scan is linear" guarantee is SCOPED to extglob-free
        # patterns. Extglob-bearing patterns keep the per-position forward DP
        # and their own achieved bound.
        startable = m._starts(Sequence(root.elements + (Star(),)), len(text))

        def span_at(pos: int) -> Optional[int]:
            if pos not in startable:
                return None
            ends = match(root, 0, pos)
            return (max(ends) - pos) if ends else None

        span_at.matcher = m                                 # type: ignore[attr-defined]
        return span_at

    def matching_spans(self, text: str,
                       profile: MatchProfile = STRING) -> Iterator[Tuple[int, int]]:
        """Left-to-right leftmost-longest non-overlapping match spans
        ``(start, end)`` over *text*. Zero-width matches advance by one.

        PRODUCTION-DEAD since slot 3.1 but a PERMANENT test-pinned relation
        oracle (the ``extglob_to_regex`` permanent-oracle precedent): it is
        the only direct pin of the left-to-right walk algebra that
        ``spanner``/``span_at`` compose into (``test_pattern_relations.py``).
        The ``${v//}`` consumer no longer walks it — substitution implements
        bash's measured ``pat_subst`` loop over ``spanner`` with the
        pre-test and position gate at the consumer seam
        (``parameter_expansion.py``, slot 3.1). Census at that slot: zero
        production callers; do not re-route consumers through it without
        re-measuring the consumer layer."""
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
