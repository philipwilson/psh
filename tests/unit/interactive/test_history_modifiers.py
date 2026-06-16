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


@pytest.mark.parametrize('seed,ref', [
    # Pathname modifiers operate on the whole selected text.
    ('echo /a/b/c.txt foo', '!!:h'),
    ('echo /a/b/c.txt foo', '!!:t'),
    ('echo /a/b/c.txt foo', '!!:r'),
    ('echo /a/b/c.txt foo', '!!:e'),
    ('echo /a/b/c.txt foo', '!!:t:r'),     # chaining
    ('echo plainword', '!!:h'),            # no slash -> unchanged
    ('echo plainword', '!!:r'),            # no dot -> unchanged
    ('echo .bashrc', '!!:r'),              # leading-dot suffix removed
    ('echo a.b.c', '!!:r'),
    ('echo a.b.c', '!!:e'),
    # Substitution.
    ('echo foo boo', '!!:s/o/0/'),         # first match
    ('echo foo boo', '!!:gs/o/0/'),        # global
    ('echo foo boo', '!!:s|o|0|'),         # alternate delimiter
    ('echo foo boo', '!!:s/foo/X/'),
    ('echo foo boo', '!!:1:s/o/0/'),       # word designator + modifier
    ('echo foo boo', '!!:s/o/0/:gs/0/Z/'), # chained substitutions
    # Quick substitution (^old^new).
    ('echo foo boo', '^o^0'),
    ('echo foo boo', '^o^0^'),
    ('echo foo boo', '^foo^bar'),
])
def test_modifiers_match_bash(seed, ref):
    assert _psh_expand(seed, ref) == _bash_history_p(seed, ref)


def test_print_modifier_prints_and_suppresses_execution(capsys):
    # :p prints the expansion and returns '' so nothing executes (bash).
    sh = Shell(norc=True)
    sh.state.options['histexpand'] = True
    sh.state.history.append('echo hello')
    result = sh.history_expander.expand_history('!!:p', print_expansion=False)
    assert result == ''                       # nothing to execute
    assert capsys.readouterr().out == 'echo hello\n'  # printed


def test_repeat_substitution_modifier():
    # :& repeats the last :s; verified against bash within one expansion.
    seed = 'echo foo boo'
    ref = '!!:s/o/0/ then !!:&'
    # (two history refs on one line: first does the sub, second repeats it)
    assert _psh_expand(seed, ref) == _bash_history_p(seed, ref)


def test_bad_modifier_is_error():
    sh = Shell(norc=True)
    sh.state.options['histexpand'] = True
    sh.state.history.append('echo hi')
    # An unknown modifier letter is a bad word specifier (returns None).
    assert sh.history_expander.expand_history('!!:Z', report_errors=False) is None
