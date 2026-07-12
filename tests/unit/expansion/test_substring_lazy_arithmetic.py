"""Substring offset/length arithmetic is evaluated LAZILY (bash).

T8 bounce fix (blocker 1). bash short-circuits ``${param:offset:length}``
BEFORE evaluating the offset/length arithmetic when the subject expands to
ZERO elements: unset scalar, out-of-range positional, absent array element,
unset/empty array, unset assoc key. An unevaluable operand (``x='$y'``,
``x='bogus['``) then yields empty, rc 0 — never an arithmetic error.

The arithmetic IS evaluated whenever the subject has at least one element:
a set scalar (even set-but-EMPTY ``v=``), ``$@``/``$*`` always (their slice
element list includes $0, so it is never empty — bash errors even with zero
positional parameters), a scalar with an ``[@]`` subscript, and any
non-empty array. With T8's expand=False (stored values never re-$-expanded),
an evaluated ``$``-bearing operand is an error like bash.

The corrected item-5 rule: bash errors on a $-bearing stored value WHEN THE
ARITHMETIC IS ACTUALLY EVALUATED — the unset-substring short-circuit never
evaluates it. Every expectation probe-verified against bash 5.2
(tmp/r19-ledgers/T8-probes/bounce_substring_lazy.sh + bounce_edges).
"""

import subprocess
import sys

import pytest


def _psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, timeout=30)


class TestSubstringLazyOnUnsetSubject:
    """RED ON PRE-BOUNCE TIP (8671e01c): psh errored rc 1 on these."""

    @pytest.mark.parametrize("cmd", [
        "y=5; x='$y'; unset v; echo [${v:x:1}]",     # THE regression case
        "x='bogus['; unset v; echo [${v:x:1}]",      # garbage offset
        "x='1//'; unset v; echo [${v:x:1}]",         # unevaluable offset
        "y=5; x='$y'; unset v; echo [${v:x}]",       # offset-only form
        "y=5; x='$y'; unset v; echo [${v:0:x}]",     # bad LENGTH
        "y=5; x='$y'; set --; echo [${1:x:1}]",      # out-of-range positional
        "y=5; x='$y'; unset a; echo [${a[0]:x:1}]",  # element of unset array
        "y=5; x='$y'; a=(p); echo [${a[5]:x:1}]",    # absent element, SET array
        "y=5; x='$y'; declare -A h; echo [${h[k]:x:1}]",       # empty assoc key
        "y=5; x='$y'; declare -A h=([k]=v); echo [${h[q]:x:1}]",  # absent key
        'y=5; x=\'$y\'; a=(); echo "[${a[@]:x:1}]"',    # empty array, fields path
        'y=5; x=\'$y\'; a=(); echo [${a[@]:x:1}]',      # empty array, string path
        'y=5; x=\'$y\'; unset a; echo "[${a[@]:x:1}]"',  # unset array, fields path
        'y=5; x=\'$y\'; unset v; echo "[${v[@]:x:1}]"',  # unset scalar with [@]
        "y=5; x='$y'; a=(); echo [${a[*]:x:1}]",     # empty array, [*] form
        'y=5; x=\'$y\'; declare -A H=(); echo "[${H[@]:x:1}]"',  # empty assoc
    ])
    def test_unset_subject_short_circuits(self, cmd):
        r = _psh(cmd)
        assert r.returncode == 0, r
        assert r.stdout == "[]\n", r
        assert r.stderr == "", r


class TestSubstringEagerOnSetSubject:
    """A subject with >= 1 element evaluates the arithmetic — and errors."""

    @pytest.mark.parametrize("cmd", [
        "y=5; x='$y'; v=abc; echo [${v:x:1}]",       # set scalar
        "y=5; x='$y'; v=; echo [${v:x:1}]",          # set-but-EMPTY scalar
        "y=5; x='$y'; v=abc; echo [${v:0:x}]",       # bad length, set scalar
        "y=5; x='$y'; set --; echo [${@:x}]",        # $@: always ($0 counts)
        "y=5; x='$y'; set -- p; echo [${@:x:1}]",
        "y=5; x='$y'; set --; echo [${*:x:1}]",      # $*: always
        "y=5; x='$y'; a=(p q); echo [${a[@]:x:1}]",  # non-empty array
        "y=5; x='$y'; a=(p q); echo [${a[*]:x:1}]",
        'y=5; x=\'$y\'; a=(p q); echo "[${a[@]:x:1}]"',   # fields path
        'y=5; x=\'$y\'; v=abc; echo "[${v[@]:x:1}]"',     # scalar with [@]
        'y=5; x=\'$y\'; v=; echo "[${v[@]:x:1}]"',        # empty scalar with [@]
        'y=5; x=\'$y\'; declare -A H=([k]=v); echo "[${H[@]:x:1}]"',
    ])
    def test_set_subject_evaluates_and_errors(self, cmd):
        r = _psh(cmd)
        assert r.returncode == 1, r
        assert r.stdout == "", r
        assert r.stderr != "", r

    def test_good_offsets_still_work(self):
        # Controls: ordinary slicing unaffected.
        for cmd, expected in [
            ('a=(1 2 3 4); echo [${a[@]:1:2}]', '[2 3]\n'),
            ('set -- a b c; echo [${@:2}]', '[b c]\n'),
            ('v=hello; echo [${v:1:3}]', '[ell]\n'),
            ('unset v; echo [${v:5:2}]', '[]\n'),
            ('v=; echo [${v:0:1}]', '[]\n'),
        ]:
            r = _psh(cmd)
            assert r.returncode == 0, (cmd, r)
            assert r.stdout == expected, (cmd, r)

    def test_nounset_wins_over_laziness(self):
        # set -u: the unbound error fires before the substring operator.
        r = _psh("set -u; y=5; x='$y'; unset v; echo [${v:x:1}]")
        assert r.returncode == 127
        assert "unbound variable" in r.stderr
