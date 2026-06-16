"""History expansion: quoting/scanner behavior (reappraisal #13 R15.B).

psh skipped history expansion inside double quotes and mis-handled a
backslash-escaped `!`. bash expands `!` inside `"..."` (only single quotes and
a preceding backslash suppress it). Verified against bash's `history -p`
(expand-and-print) used as a live oracle — psh's `expand_history()` is compared
to it directly (history expansion is interactive-only; there's no `-c` vehicle).
"""

import subprocess

import pytest

from psh.shell import Shell

SEED = 'echo prev cmd'


def _bash_history_p(seed, ref):
    """bash's history expansion of `ref` with `seed` as the previous command."""
    out = subprocess.run(
        ['bash', '-c', "set -H; history -s \"$1\"; history -p \"$2\"",
         '_', seed, ref],
        capture_output=True, text=True)
    return out.stdout.rstrip('\n')


def _psh_expand(seed, ref):
    sh = Shell(norc=True)
    sh.state.options['histexpand'] = True
    sh.state.history.append(seed)
    return sh.history_expander.expand_history(ref, print_expansion=False)


@pytest.mark.parametrize('ref', [
    'echo !!',                # plain event
    'echo "see !!"',          # double quotes DO expand
    'echo "x !! y"',
    'echo "it\'s !!"',        # ' inside "..." is literal, !! still expands
    "echo '!!'",              # single quotes suppress
    'echo \\!!',              # backslash suppresses, kept
    'echo \\!foo',
    'echo "a\\!b"',           # backslash inside "..." suppresses
    'a!=b',                   # != is not a history ref
    'echo "${x} !!"',         # ${...} untouched, !! expands
])
def test_scanner_matches_bash(ref):
    assert _psh_expand(SEED, ref) == _bash_history_p(SEED, ref)
