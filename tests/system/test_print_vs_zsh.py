"""Compatibility tests comparing psh ``print`` against real zsh.

The conformance framework only compares against bash, which has no ``print``
builtin, so these subprocess tests are the guard for the "zsh-compatible"
claim. They are skipped automatically when zsh is not installed.
"""

import shutil
import subprocess
import sys

import pytest

ZSH = shutil.which("zsh")

pytestmark = pytest.mark.skipif(ZSH is None, reason="zsh not installed")


def _psh(cmd):
    return subprocess.run(
        [sys.executable, "-m", "psh", "-c", cmd],
        capture_output=True, text=True,
    )


def _zsh(cmd):
    return subprocess.run([ZSH, "-c", cmd], capture_output=True, text=True)


# Commands whose stdout should be identical between psh and zsh.
IDENTICAL_CASES = [
    "print hello world",
    "print",
    r"print 'a\tb'",
    r"print 'a\nb'",
    r"print -r 'a\tb'",
    "print -n hello",
    "print -l a b c",
    "print -nl a b c",
    "print -N a b",
    r"print -rn 'a\tb'",
    r"print 'foo\cbar'",
    r"print -R 'a\tb'",
    r"print -R -e 'a\tb'",
    "print -R -l x",
    "print -- -n hello",
    "print -",
    r"print -f '%s=%d\n' a 1 b 2",
    r"print -f'%s\n' hi",
    "print -m 'f*' foo far bar",
    "print -m '?' a bb c",
    "print -o c b a",
    "print -O a b c",
    "print -i -o B a C",
    "print -o b A c",
]


@pytest.mark.parametrize("cmd", IDENTICAL_CASES)
def test_matches_zsh_stdout(cmd):
    p = _psh(cmd)
    z = _zsh(cmd)
    assert p.stdout == z.stdout, (
        f"cmd={cmd!r}\npsh={p.stdout!r}\nzsh={z.stdout!r}"
    )
