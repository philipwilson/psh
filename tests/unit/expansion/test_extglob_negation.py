"""Embedded extglob negation `!(...)` matches per-span, not per-character.

Python's ``re`` cannot express embedded negation ``a!(P)b`` (it would need a
variable-width lookbehind), so the old inline per-character lookahead
over-rejected any span that merely CONTAINED a character starting an
alternative: ``[[ xfoox == x!(o)x ]]`` was false, ``${s/x!(o)y/_}`` didn't
replace, ``echo x!(o)x`` dropped real files. The fix routes every negation
pattern through a backtracking matcher (``extglob._extglob_consume``) shared by
``case``, ``[[ == ]]``, the removal/substitution operators, and pathname
globbing (appraisal 2026-06-21, finding H5).

Every expectation here was probe-verified against bash 5.2 with
``shopt -s extglob``.
"""

import pytest

from psh.expansion.extglob import (
    extglob_fullmatch,
    extglob_match_at,
    match_extglob,
)

# (pattern, string, expected) — full-match, bash-pinned.
FULLMATCH_CASES = [
    # The headline bug: span contains the alternative but differs as a whole.
    ('x!(o)x', 'xfoox', True),
    ('x!(o)x', 'xox', False),
    ('x!(o)x', 'xx', True),
    ('x!(o)x', 'xoox', True),
    ('a!(b)c', 'abbc', True),
    ('a!(b)c', 'abc', False),
    ('a!(b)c', 'ac', True),
    ('!(b)c', 'abc', True),
    ('!(b)c', 'bc', False),
    ('!(b)c', 'bbc', True),
    ('file_!(bad).txt', 'file_xbadx.txt', True),
    ('file_!(bad).txt', 'file_bad.txt', False),
    # Standalone negation still correct.
    ('!(foo)', 'foo', False),
    ('!(foo)', 'foobar', True),
    ('!(foo)', '', True),
    ('!(*.o)', 'a.o', False),
    ('!(*.o)', 'a.c', True),
    ('!(b*)', 'bar', False),
    ('!(b*)', 'cat', True),
    # Alternation and nesting.
    ('x!(a|b)y', 'xcy', True),
    ('x!(a|b)y', 'xay', False),
    ('x!(a|b)y', 'xaby', True),
    ('a@(b|!(c))d', 'abd', True),
    ('a@(b|!(c))d', 'axd', True),
    ('a@(b|!(c))d', 'acd', False),
    # Negation next to globs / other extglob ops.
    ('*!(o)*', 'ooo', True),
    ('!(a)!(b)', 'ab', True),
    ('!([0-9])', 'a', True),
    ('!([0-9])', '5', False),
]


@pytest.mark.parametrize('pattern,string,expected',
                         [pytest.param(*c, id=f'{c[0]}~{c[1] or "empty"}={c[2]}')
                          for c in FULLMATCH_CASES])
def test_extglob_fullmatch(pattern, string, expected):
    assert extglob_fullmatch(pattern, string) is expected
    # match_extglob routes negation through the same matcher.
    assert match_extglob(pattern, string) is expected


def test_match_at_leftmost_longest():
    # x!(o)y at pos 0 of "xfooy" consumes the whole 5-char span.
    assert extglob_match_at('x!(o)y', 'xfooy', 0) == 5
    # No match at a position.
    assert extglob_match_at('x!(o)y', 'abc', 0) is None


class TestNegationInConstructs:
    """End-to-end through case / [[ ]] / operators (extglob enabled)."""

    def _run(self, captured_shell, body):
        captured_shell.run_command('shopt -s extglob')
        captured_shell.clear_output()
        captured_shell.run_command(body)
        return captured_shell.get_stdout()

    def test_double_bracket_embedded(self, captured_shell):
        assert self._run(captured_shell,
                         '[[ xfoox == x!(o)x ]] && echo y || echo n') == 'y\n'

    def test_double_bracket_embedded_reject(self, captured_shell):
        assert self._run(captured_shell,
                         '[[ xox == x!(o)x ]] && echo y || echo n') == 'n\n'

    def test_case_embedded(self, captured_shell):
        assert self._run(captured_shell,
                         'case xfoox in x!(o)x) echo m;; *) echo no;; esac') == 'm\n'

    def test_patsub_embedded(self, captured_shell):
        assert self._run(captured_shell, 's=xfooy; echo "${s/x!(o)y/_}"') == '_\n'

    def test_patsub_all_empty_capable(self, captured_shell):
        assert self._run(captured_shell, 's=a1b2c; echo "${s//!([0-9])/_}"') == '_\n'

    def test_prefix_removal_embedded(self, captured_shell):
        assert self._run(captured_shell, 'v=xfooxER; echo "${v#x!(o)x}"') == 'ER\n'

    def test_longest_prefix_removal(self, captured_shell):
        assert self._run(captured_shell, 'v=aXbXc; echo "${v##*!(b)}"') == '\n'
