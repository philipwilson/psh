#!/usr/bin/env python3
"""Is "match the SUFFIX STRING" the same relation as "match s[pos:] in place"?

The substitution scan currently materialises `value[pos:]` and builds a fresh
matcher per scan position — O(n) copy x O(n) positions = the residual
quadratic on the word-spaced shape. Replacing it with offsets into the
original string and ONE shared matcher is only sound if, for every pattern,
subject and position:

    full_match(value[pos:])            ==  "matches value[pos:len] in place"

This probe MEASURES that identity rather than assuming it, across both matcher
routes (quirk / non-quirk), both profiles, and every position — including the
wrapper patterns the pre-test actually uses.
"""
import os
import sys

PSH_ROOT = os.environ.get('PSH_ROOT', '/Users/pwilson/src/psh-r3-2')
import psh  # noqa: E402
import psh.expansion.pattern_engine as pe  # noqa: E402
from psh.expansion.parameter_expansion import _sub_machinery_cached  # noqa: E402

if not os.path.realpath(pe.__file__).startswith(os.path.realpath(PSH_ROOT) + os.sep):
    sys.exit("DISCRIMINATOR FAIL")
print(f"# discriminator OK: {psh.__file__}")


def inplace_full(root, text, pos, profile):
    """'root matches text[pos:]' evaluated WITHOUT slicing the string."""
    n = len(text)
    if pe._seq_bash_quirk(root):
        return pe._BashMatcher(text, profile.for_pathname,
                               profile.ic).match(root, 0, pos, n)
    return pe._Matcher(text, profile.for_pathname,
                       profile.ic)._full(root, 0, pos)


PATTERNS = [
    '*([[:space:]])', '+([[:space:]])', '!(x)', '@(x|)', '*!(a)', '**(a)b',
    '*+(a)', 'a*b', '*b', '*', 'ab', '?(a)', '*(a|b)', '@(a|b)c', '*?(a)!(b)',
    '**([[:space:]])*', '*+([[:space:]])*', '**(a)b*', '*!(a)*', '*@(a|)*',
    '[ab]*', '*[!a]', 'a*b*c', '*a*a*b',
]
SUBJECTS = ['', ' ', 'x ', 'x x ', '  ', 'x  x', 'aab', 'abab', 'aaa',
            'x y z ', '   x', 'a', 'ab', 'ba', 'abc', 'a b', 'aa  bb ',
            'x ' * 5, ' ' * 5, 'a' * 6, 'ab' * 4]

cells = 0
bad = []
for pat in PATTERNS:
    # the raw pattern AND the wrapper the pre-test would really use
    for anchor in ('any', 'beg', 'end'):
        compiled, wrapped, _e, _f = _sub_machinery_cached(pat, anchor, True)
        for cp in (compiled, wrapped):
            for profile in (pe.STRING, pe.STRING_IC):
                for subj in SUBJECTS:
                    for pos in range(len(subj) + 1):
                        cells += 1
                        sliced = cp.full_match(subj[pos:], profile)
                        inplace = inplace_full(cp.root, subj, pos, profile)
                        if sliced != inplace:
                            bad.append((pat, anchor, subj, pos, profile.ic,
                                        sliced, inplace))

print(f"cells: {cells}")
print(f"DISAGREEMENTS: {len(bad)}")
for b in bad[:20]:
    print(f"  pat={b[0]!r} anchor={b[1]} subj={b[2]!r} pos={b[3]} ic={b[4]}: "
          f"sliced={b[5]} inplace={b[6]}")
sys.exit(1 if bad else 0)
