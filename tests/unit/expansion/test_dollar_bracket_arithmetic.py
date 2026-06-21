"""The deprecated `$[expr]` arithmetic form (appraisal Tier 3, M3).

``$[expr]`` is bash's deprecated spelling of ``$((expr))``. psh passed it
through verbatim (``echo $[1+2]`` printed ``$[1+2]``) because the lexer's
expansion dispatch and the literal recognizer's ``can_start_expansion`` did not
recognise ``$[``. The lexer now rewrites ``$[expr]`` (with balanced ``[]`` and
nested ``$[...]``) to the canonical ``$((expr))`` token.

Every expectation was probe-verified against bash 5.2.
"""

import pytest


def run(captured_shell, cmd):
    captured_shell.clear_output()
    captured_shell.run_command(cmd)
    return captured_shell.get_stdout()


CASES = [
    ('echo $[1+2]', '3\n'),
    ('x=5; echo $[x+1]', '6\n'),
    ('echo "$[1+1]"', '2\n'),
    ('echo "result=$[10/2]"', 'result=5\n'),
    ('y=$[3*4]; echo $y', '12\n'),
    ('arr=(5 6); echo $[arr[0]+1]', '6\n'),       # balanced [] subscript
    ('echo $[2*$[3]]', '6\n'),                     # nested $[...]
    ('echo $[1+$[2*$[3+1]]]', '9\n'),             # deep nest
    ('echo $[2#101]', '5\n'),                      # base, like $(( ))
]


@pytest.mark.parametrize('cmd,expected',
                         [pytest.param(c, e, id=c) for c, e in CASES])
def test_dollar_bracket_arithmetic(captured_shell, cmd, expected):
    assert run(captured_shell, cmd) == expected


def test_does_not_disturb_normal_subscript(captured_shell):
    # ${arr[1]} and a[b] literal are unaffected.
    assert run(captured_shell, 'arr=(1 2 3); echo ${arr[1]}') == '2\n'
    assert run(captured_shell, 'echo a[b]') == 'a[b]\n'
