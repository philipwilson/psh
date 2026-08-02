#!/usr/bin/env python3
"""A4 — DESIGN PROTOTYPES, measured (no production file is touched).

Two load-bearing claims, each prototyped against the REAL compiled AST and
checked for exact agreement with the shipped relation before any timing is
believed.

P1  all-start backward DP  -> `matching_starts` becomes ONE pass (linear in
    subject for a fixed plain-glob AST) instead of one forward DP per start.

P2  memoized `ok` DP for the `*`/`+` closure inside _BashMatcher -> the
    per-entry-position O(n^2) closure rebuild becomes ONE O(n^2) table per
    (group, gi, se), collapsing the cubic to quadratic.

Run: cd <wt>/tmp/slot32 && PSH_ROOT=<wt> PYTHONPATH=<wt> python3 proto_design.py
"""
import itertools
import os
import sys
import time

PSH_ROOT = os.environ.get('PSH_ROOT', '/Users/pwilson/src/psh-r3-2')
import psh  # noqa: E402
import psh.expansion.pattern_engine as pe  # noqa: E402
from psh.expansion.extglob import _bracket_match, _eq  # noqa: E402

if not os.path.realpath(pe.__file__).startswith(os.path.realpath(PSH_ROOT) + os.sep):
    sys.exit("DISCRIMINATOR FAIL")
print(f"# discriminator OK: {psh.__file__}  version={psh.version.__version__}")

Literal, AnyChar, Star, Bracket, Extglob = (
    pe.Literal, pe.AnyChar, pe.Star, pe.Bracket, pe.Extglob)


# =========================================================================
# P1 — all-start backward DP  (non-quirk patterns)
# =========================================================================

def matching_starts_proto(root, s, end=None, fp=False, ic=False):
    """{ i : root matches s[i:end] } in ONE backward pass.

    S_j = { p : elements[j:] matches s[p:end] }, computed right-to-left as a
    bytearray over [0, end]. Plain-glob elements are O(end) each; only an
    Extglob element falls back to the forward per-position element_ends.
    """
    if end is None:
        end = len(s)
    m = pe._Matcher(s, fp, ic)
    elements = root.elements
    cur = bytearray(end + 1)
    cur[end] = 1                                   # S_ne = {end}
    for j in range(len(elements) - 1, -1, -1):
        node = elements[j]
        t = type(node)
        nxt = bytearray(end + 1)
        if t is Literal:
            ch = node.char
            for p in range(end):
                if cur[p + 1] and _eq(s[p], ch, ic):
                    nxt[p] = 1
        elif t is AnyChar:
            for p in range(end):
                if cur[p + 1] and (not fp or s[p] != '/'):
                    nxt[p] = 1
        elif t is Bracket:
            content = node.content
            for p in range(end):
                if (cur[p + 1] and (not fp or s[p] != '/')
                        and _bracket_match(content, s[p], ic)):
                    nxt[p] = 1
        elif t is Star:
            if not fp:
                # p reaches any q >= p, so S_j = [0, max(S_{j+1})]
                hi = -1
                for q in range(end, -1, -1):
                    if cur[q]:
                        hi = q
                        break
                if hi >= 0:
                    for p in range(hi + 1):
                        nxt[p] = 1
            else:
                ns = m._next_slash()
                for p in range(end + 1):
                    lim = min(ns[p], end)
                    for q in range(p, lim + 1):
                        if cur[q]:
                            nxt[p] = 1
                            break
        else:  # Extglob — per-position element_ends (unchanged cost)
            for p in range(end + 1):
                for q in m._element_ends(node, p):
                    if q <= end and cur[q]:
                        nxt[p] = 1
                        break
        cur = nxt
    return frozenset(i for i in range(end + 1) if cur[i])


# =========================================================================
# P2 — memoized closure-`ok` DP inside the bash-composition matcher
# =========================================================================

class BashMatcherProto(pe._BashMatcher):
    """_BashMatcher with the `*`/`+` closure replaced by a memoized ok-table.

    ok(p) == "the rest of the sequence matches starting somewhere reachable
    from p by zero-or-more NONEMPTY alternative spans" — exactly the original
    `any(rest_ok(pos) for pos in _closure(alts, {p}, se))`, unrolled as a
    backward DP and memoized per (group node, gi, se) so O(n) entry positions
    share ONE O(n^2) table instead of rebuilding it each time.
    """

    def __init__(self, s, fp, ic):
        super().__init__(s, fp, ic)
        self._okmemo = {}

    def _ok_table(self, node, seq, gi, se):
        key = (id(node), gi, se)
        tbl = self._okmemo.get(key)
        if tbl is None:
            alts = node.alts
            tbl = bytearray(se + 2)
            for p in range(se, -1, -1):
                r = self.match(seq, gi + 1, p, se)
                if not r:
                    for q in range(p + 1, se + 1):
                        if tbl[q] and self._alt_span(alts, p, q):
                            r = True
                            break
                tbl[p] = 1 if r else 0
            self._okmemo[key] = tbl
        return tbl

    def _extmatch(self, node, seq, gi, si, se):
        op = node.op
        if op == '*':
            return bool(self._ok_table(node, seq, gi, se)[si])
        if op == '+':
            tbl = self._ok_table(node, seq, gi, se)
            alts = node.alts
            for split in range(si, se + 1):
                if tbl[split] and self._alt_span(alts, si, split):
                    return True
            return False
        return super()._extmatch(node, seq, gi, si, se)


def full_match_proto(root, s, fp=False, ic=False):
    return BashMatcherProto(s, fp, ic).match(root, 0, 0, len(s))


def matching_ends_proto(root, s, start=0, fp=False, ic=False):
    bm = BashMatcherProto(s, fp, ic)
    return frozenset(k for k in range(start, len(s) + 1)
                     if bm.match(root, 0, start, k))


def matching_starts_quirk_proto(root, s, end=None, fp=False, ic=False):
    if end is None:
        end = len(s)
    bm = BashMatcherProto(s, fp, ic)
    return frozenset(i for i in range(end + 1) if bm.match(root, 0, i, end))


# =========================================================================
# AGREEMENT (correctness gate — timing is meaningless without this)
# =========================================================================

PATTERNS = [
    # plain globs (P1 territory)
    '*b', 'a*b', '*a*b', '*', '?b', 'a?c', '[ab]*', '*[!a]', 'a*b*c',
    '*a*a*a*b', 'ab', '', '*?', '?*',
    # extglob, non-quirk
    '+(a)', '@(a|b)', '!(a)', '*(ab)', '@(a|)', '+([ab])', '!(a|b)c',
    # quirk (star before group) — P2 territory
    '**(a)b', '*!(a)', '*?(a|b)', '*@(a|*)', '*+(a)', '*@(a|b)c',
    '*!(a)b', '**(a|b)c', '?*+(a)', '*?(a)!(b)', '*+(a|aa)b', '**(a)',
    '*!(ab)c', 'a*+(b)c', '*@(a)*(b)',
]
SUBJECTS = ['', 'a', 'b', 'ab', 'ba', 'aab', 'aba', 'aaa', 'abc', 'aabb',
            'abab', 'xa', 'ax', 'aaab', 'abba', 'c', 'ac', 'bc', 'aabbcc']

print("\n" + "=" * 76)
print("AGREEMENT — prototypes vs the SHIPPED relations (exact, all cells)")
print("=" * 76)
cells = 0
bad = []
for pat in PATTERNS:
    root = pe.compile_pattern(pat)
    cp = pe.CompiledPattern(root)
    quirk = pe._seq_bash_quirk(root)
    for s in SUBJECTS:
        cells += 1
        # P1 applies to NON-quirk patterns only
        if not quirk:
            want = cp.matching_starts(s, len(s), pe.STRING)
            got = matching_starts_proto(root, s)
            if want != got:
                bad.append(('P1 matching_starts', pat, s, want, got))
        else:
            want = cp.full_match(s, pe.STRING)
            got = full_match_proto(root, s)
            if want != got:
                bad.append(('P2 full_match', pat, s, want, got))
            want = cp.matching_ends(s, 0, pe.STRING)
            got = matching_ends_proto(root, s)
            if want != got:
                bad.append(('P2 matching_ends', pat, s, want, got))
            want = cp.matching_starts(s, len(s), pe.STRING)
            got = matching_starts_quirk_proto(root, s)
            if want != got:
                bad.append(('P2 matching_starts', pat, s, want, got))

# pathname profile pass for P1 (fp=True) on slash-bearing subjects
SLASH_SUBJ = ['a/b', '/ab', 'ab/', 'a/b/c', '//', 'a//b']
for pat in ['*b', 'a*b', '*', '*/b', 'a*', '?/b', '*a*']:
    root = pe.compile_pattern(pat)
    cp = pe.CompiledPattern(root)
    if pe._seq_bash_quirk(root):
        continue
    for s in SLASH_SUBJ:
        cells += 1
        want = cp.matching_starts(s, len(s), pe.PATHNAME)
        got = matching_starts_proto(root, s, fp=True)
        if want != got:
            bad.append(('P1 matching_starts fp', pat, s, want, got))

print(f"  cells checked: {cells}")
print(f"  disagreements: {len(bad)}")
for row in bad[:12]:
    print(f"    {row}")
if bad:
    print("\n  PROTOTYPE DISAGREES — timing below is NOT evidence.")

# =========================================================================
# COMPLEXITY (only meaningful if agreement is exact)
# =========================================================================

def growth(label, fn, sizes, mk=lambda n: 'a' * n):
    print(f"\n## {label}")
    print(f"{'N':>7} {'seconds':>11} {'ratio':>8}")
    prev = None
    for n in sizes:
        subj = mk(n)
        t0 = time.perf_counter()
        fn(subj)
        dt = time.perf_counter() - t0
        r = (dt / prev) if prev else float('nan')
        print(f"{n:>7} {dt:>11.4f} {r:>8.2f}")
        prev = dt
        if dt > 20:
            print("        (stopped)")
            break


print("\n" + "=" * 76)
print("P1 COMPLEXITY — matching_starts '*b'  (base = x4/doubling quadratic)")
print("=" * 76)
r_star_b = pe.compile_pattern('*b')
cp_star_b = pe.CompiledPattern(r_star_b)
growth("SHIPPED  matching_starts('*b')",
       lambda s: cp_star_b.matching_starts(s, len(s), pe.STRING),
       (500, 1000, 2000, 4000))
growth("PROTO P1 matching_starts('*b')",
       lambda s: matching_starts_proto(r_star_b, s),
       (500, 1000, 2000, 4000, 8000, 16000))

print("\n" + "=" * 76)
print("P2 COMPLEXITY — full_match '**(a)b'  (base = x8/doubling CUBIC)")
print("=" * 76)
r_cubic = pe.compile_pattern('**(a)b')
cp_cubic = pe.CompiledPattern(r_cubic)
growth("SHIPPED  full_match('**(a)b')",
       lambda s: cp_cubic.full_match(s, pe.STRING), (50, 100, 200, 400))
growth("PROTO P2 full_match('**(a)b')",
       lambda s: full_match_proto(r_cubic, s), (50, 100, 200, 400, 800, 1600))

print("\n" + "=" * 76)
print("P2 COMPLEXITY — matching_starts '*+(a)'  (base = x8/doubling CUBIC)")
print("=" * 76)
r_sp = pe.compile_pattern('*+(a)')
cp_sp = pe.CompiledPattern(r_sp)
growth("SHIPPED  matching_starts('*+(a)')",
       lambda s: cp_sp.matching_starts(s, len(s), pe.STRING), (100, 200, 400))
growth("PROTO P2 matching_starts('*+(a)')",
       lambda s: matching_starts_quirk_proto(r_sp, s), (100, 200, 400, 800))

print("\n" + "=" * 76)
print("STATES side-effect check — does the ok-table inflate the memo?")
print("=" * 76)
print(f"{'N':>6} {'shipped':>10} {'proto':>10} {'bound (n+2)^2':>15} {'proto<=bound':>13}")
for n in (16, 64, 128, 256):
    subj = 'a' * n
    sm = pe._BashMatcher(subj, False, False)
    sm.match(r_cubic, 0, 0, n)
    pm = BashMatcherProto(subj, False, False)
    pm.match(r_cubic, 0, 0, n)
    b = (n + 2) ** 2
    print(f"{n:>6} {sm.states:>10} {pm.states:>10} {b:>15} "
          f"{str(pm.states <= b):>13}")
