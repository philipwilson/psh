#!/usr/bin/env python3
"""Idempotence-checked application of ALL slot 3.1 Phase C source edits on
top of tip 7bec085c (the three files a replay revert can touch). Run from
the worktree root. Each replacement asserts uniqueness; a second run fails
its asserts loudly (already applied) rather than corrupting anything."""
import sys

PE = 'psh/expansion/pattern_engine.py'
PX = 'psh/expansion/parameter_expansion.py'
BT = 'tests/unit/expansion/test_pattern_bash_composition_differential.py'


def sub(path, old, new, tag):
    src = open(path).read()
    assert src.count(old) == 1, f"{tag}: target not unique/found in {path}"
    open(path, 'w').write(src.replace(old, new))
    print(f"applied {tag}")


# ---------- pattern_engine.py ----------
sub(PE, '''            # Star: the bash star case.
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
        return n == se''', '''            # Star: the bash star case. The outer loop below is the glibc
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
        return ((1 if m == se else 0), m, j)''', "PE star-jump + _segment")

sub(PE, '''3. EXCEPT for bash-composition patterns (slot 3.1): where an extglob group
   sits directly after a wildcard run, bash 5.2's measured semantics are
   SLICE-END-RELATIVE (the star case's strict continuation bounds, its
   ``?(``/``*(`` try-then-skip branches, and the unenclosed-negation
   end-of-string rule — ``lib/glob/sm_loop.c``), so "matches ``text[i:k]``"
   is a per-``(i, k)`` boolean that no single forward pass can produce.
   :func:`_seq_bash_quirk` routes exactly those patterns to
   :class:`_BashMatcher` (a memoized port of the measured model — 64,575
   corpus cells against live bash, 0 mismatches; the lock is
   ``test_pattern_bash_composition_differential.py``), and the relations
   evaluate them as per-slice booleans. Every other pattern keeps the fast
   paths above unchanged. Flagged-pattern recursion is bounded by PATTERN
   structure (star-runs + group dispatches + nesting), never subject length.''',
    '''3. EXCEPT for bash-composition patterns (slot 3.1): where an extglob group
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
   never subject length.''', "PE docstring point 3")

sub(PE, '''# is a per-(i,k) boolean and cannot ride the forward reachability DP. This
# matcher is a faithful port of the MEASURED model (65,625 corpus cells vs
# live bash 5.2.26, 0 mismatches — slot 3.1 ledger A4; enforced by
# test_pattern_bash_composition_differential.py). Non-quirk patterns never
# reach it. The rules, in bash sm_loop.c terms:''',
    '''# is a per-(i,k) boolean and cannot ride the forward reachability DP. This
# matcher is a faithful port of the MEASURED model; exactness is SCOPED to
# the slot's measured corpora (437,811 cells vs live bash 5.2.26 across
# corpus1/2/3 incl. a disjoint-alphabet mirror, 0 mismatches — ledger A4 +
# C-2; permanently enforced by the grammar-v2 battery in
# test_pattern_bash_composition_differential.py). Non-quirk patterns never
# reach it. The rules, in bash sm_loop.c terms:''', "PE block comment")

sub(PE, '''#     '!' = per-split complement AND continuation.
#
# Recursion here is bounded by the PATTERN structure (one frame per group
# dispatch / star-run in a sequence, plus alt nesting) — never by subject
# length or star count; the per-(sequence, element, si, se) memo keeps the
# evaluation polynomial (guarded by count_states via `states`).''',
    '''#     '!' = per-split complement AND continuation;
#   * the glibc star-JUMP (round 1): the general scan's inner walk
#     (_segment, = GMATCH-with-&end) STOPS at the next wildcard star and
#     COMMITS that position — a simple-element segment between stars is
#     placed at its LEFTMOST match and earlier stars never retry; groups
#     are jump-opaque (EXTMATCH passes NULL ends). Invisible to plain
#     patterns; decisive for the entry position the rules above see.
#
# Recursion here is bounded by the PATTERN structure (one frame per group
# dispatch, plus alt nesting; star-run scanning and jump commits are
# iterative) — never by subject length or star count; the per-(sequence,
# element, si, se) memo keeps the evaluation polynomial (guarded by
# count_states via `states`).''', "PE rules/recursion comment")

sub(PE, '''        """Left-to-right leftmost-longest non-overlapping match spans
        ``(start, end)`` over *text*. Zero-width matches advance by one.

        A generic relation (pinned by ``test_pattern_relations.py``); the
        ``${v//}`` consumer no longer walks it directly — substitution
        implements bash's measured ``pat_subst`` loop over ``spanner`` with
        the pre-test and position gate at the consumer seam
        (``parameter_expansion.py``, slot 3.1)."""''',
    '''        """Left-to-right leftmost-longest non-overlapping match spans
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
        re-measuring the consumer layer."""''', "PE matching_spans oracle label")

# ---------- parameter_expansion.py ----------
sub(PX, "from typing import TYPE_CHECKING, List, Optional, Tuple, Union, cast",
    "from functools import lru_cache\n"
    "from typing import TYPE_CHECKING, List, Optional, Tuple, Union, cast",
    "PX lru_cache import")

sub(PX, '''# Sentinel marking "the matched text" in a prepared replacement template
# (bash 5.2 patsub_replacement: an unquoted & in the replacement).
PATSUB_MATCH = object()''',
    '''# Sentinel marking "the matched text" in a prepared replacement template
# (bash 5.2 patsub_replacement: an unquoted & in the replacement).
PATSUB_MATCH = object()


@lru_cache(maxsize=512)
def _sub_machinery_cached(pattern: str, anchor: str, extglob: bool
                          ) -> Tuple[CompiledPattern, CompiledPattern, bool]:
    """Cached body of ``ParameterExpansionOps._sub_machinery`` (see it for
    the semantics; round-1 nit N3). Semantics-neutral: ``CompiledPattern``
    is stateless and the wrapped Sequence's lazy routing/enclosure bits are
    identical for equal ``(pattern, anchor, extglob)`` keys. The memo
    amortizes wrapper construction and its ``_seq_bash_quirk`` walk across
    repeated substitutions of one pattern; the dominant per-operation cost
    (matching) is unchanged — measured gain recorded in the slot ledger."""
    compiled = PatternCompiler.compile(pattern, extglob=extglob)
    elems = compiled.root.elements
    head = elems[0] if elems else None
    tail = elems[-1] if elems else None
    head_star = type(head) is Star
    end_eligible = head_star or (
        type(head) is Extglob and cast(Extglob, head).op == '*')
    pre: Tuple[object, ...] = ()
    post: Tuple[object, ...] = ()
    if anchor != 'beg' and not head_star:
        pre = (Star(),)
    if anchor != 'end' and not (type(tail) is Star):
        post = (Star(),)
    if pre or post:
        wrapped = CompiledPattern(Sequence(pre + elems + post))
    else:
        wrapped = compiled
    return compiled, wrapped, end_eligible''', "PX cached helper")

sub(PX, '''        compiled = self._compile(pattern)
        elems = compiled.root.elements
        head = elems[0] if elems else None
        tail = elems[-1] if elems else None
        head_star = type(head) is Star
        end_eligible = head_star or (
            type(head) is Extglob and cast(Extglob, head).op == '*')
        pre: Tuple[object, ...] = ()
        post: Tuple[object, ...] = ()
        if anchor != 'beg' and not head_star:
            pre = (Star(),)
        if anchor != 'end' and not (type(tail) is Star):
            post = (Star(),)
        if pre or post:
            wrapped = CompiledPattern(Sequence(pre + elems + post))
        else:
            wrapped = compiled
        return compiled, wrapped, end_eligible''',
    "        return _sub_machinery_cached(pattern, anchor, self._extglob)",
    "PX thin method")

print("pattern_engine + parameter_expansion restored; battery next (run "
      "restore_battery.py)")
