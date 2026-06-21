"""Composite / $-containing heredoc delimiters (appraisal Tier 3, M1).

A heredoc delimiter that spans several tokens — ``<<E$X``, ``<<E"O"F``,
``<<$VAR`` — was truncated to its leading token, so the body never terminated
(or the trailing parts were parsed as command arguments). bash takes the whole
delimiter word LITERALLY (no expansion), terminating at the first unquoted
whitespace/metacharacter. The lexer (body terminator), the parser (token
consumption + quote flag) and the line-gathering detector now all recover the
same full delimiter.

Heredocs need real fds, so these run psh in a subprocess and compare to bash.
"""

import subprocess
import sys


def run(script):
    return subprocess.run([sys.executable, '-m', 'psh'], input=script,
                          capture_output=True, text=True)


def run_bash(script):
    return subprocess.run(['bash'], input=script, capture_output=True, text=True)


CASES = [
    # ($-delimiter is LITERAL; body still expands because the delimiter is unquoted)
    ('X=zzz\ncat <<E$X\nv=$X\nE$X\n', 'v=zzz\n'),
    ('cat <<E$X\nbody line\nE$X\n', 'body line\n'),
    ('cat <<$VAR\nhi\n$VAR\n', 'hi\n'),
    # composite quoted delimiter -> body NOT expanded
    ('cat <<E"O"F\nv=$HOME\nEOF\n', 'v=$HOME\n'),
    # regressions: ordinary delimiters and trailing operators
    ('cat <<EOF\nplain\nEOF\n', 'plain\n'),
    ('cat <<EOF; echo done\nhi\nEOF\n', 'hi\ndone\n'),
    ('cat <<-EOF\n\tindent\nEOF\n', 'indent\n'),
]


import pytest


@pytest.mark.parametrize('script,expected',
                         [pytest.param(s, e, id=repr(s)) for s, e in CASES])
def test_composite_delimiter_body(script, expected):
    r = run(script)
    assert r.stdout == expected


@pytest.mark.parametrize('script', [s for s, _ in CASES])
def test_matches_bash(script):
    assert run(script).stdout == run_bash(script).stdout
