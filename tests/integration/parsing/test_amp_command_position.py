"""Reserved words / `[[` / `!` keep command position after `&` (A2).

Reappraisal #15 finding A2. Before the fix, STATEMENT_SEPARATORS omitted
AMPERSAND, so `true & if true; then echo B; fi` was rc=2 and
`true & [[ -n x ]]` ran a command named `[[` (command not found).
`|&` had the same defect (PIPE was a separator, PIPE_AND was not).

Every case here was verified against bash 5.2
(tmp/r15_a2_truth_table.sh). Run in subprocesses because syntax errors
must abort the whole -c input, like bash.
"""

import subprocess
import sys


def run_psh(script):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                          capture_output=True, text=True, timeout=15)


class TestCompoundAfterAmpersand:
    """A compound command directly after `&` parses and runs (bash)."""

    ACCEPTED = [
        ('true & if true; then echo B; fi; wait', 'B\n'),
        ('true & while true; do echo W; break; done; wait', 'W\n'),
        ('true & until false; do echo U; break; done; wait', 'U\n'),
        ('true & case x in x) echo C;; esac; wait', 'C\n'),
        ('true & for i in 1; do echo F$i; done; wait', 'F1\n'),
        ('true & [[ -n x ]] && echo X; wait', 'X\n'),
        ('true & ! false && echo NOT; wait', 'NOT\n'),
        ('true & (( 1 )) && echo AR; wait', 'AR\n'),
        # no space between '&' and the keyword
        ('true &if true; then echo NS; fi; wait', 'NS\n'),
        # nested contexts exercise the same lexer
        ('f() { true & if true; then echo FN; fi; wait; }; f', 'FN\n'),
        ('eval "true & if true; then echo EV; fi"; wait', 'EV\n'),
        ('echo $(true & if true; then echo CS; fi; wait)', 'CS\n'),
        # |& is a separator exactly like | (bash accepts a compound next)
        ('true |& if true; then echo PA; fi', 'PA\n'),
    ]

    def test_accepted(self):
        for script, expected in self.ACCEPTED:
            r = run_psh(script)
            assert r.returncode == 0, f'{script!r}: rc={r.returncode} err={r.stderr!r}'
            assert r.stdout == expected, f'{script!r}: stdout={r.stdout!r}'
            assert r.stderr == '', f'{script!r}: stderr={r.stderr!r}'


class TestAmpersandBeforeClosingKeyword:
    """`&` may be the last thing before a closing keyword (bash)."""

    ACCEPTED = [
        ('{ echo a & }; wait', 'a\n'),
        ('if true; then echo hi & fi; wait', 'hi\n'),
        ('while false; do echo hi & done; echo ok', 'ok\n'),
        ('case x in x) echo m & esac; wait', 'm\n'),
    ]

    def test_accepted(self):
        for script, expected in self.ACCEPTED:
            r = run_psh(script)
            assert r.returncode == 0, f'{script!r}: rc={r.returncode} err={r.stderr!r}'
            assert r.stdout == expected, f'{script!r}: stdout={r.stdout!r}'


class TestPlainBackgroundingUnchanged:
    """The everyday `&` uses keep working (regression set)."""

    ACCEPTED = [
        ('echo a & wait', 'a\n'),
        ('true & echo fg; wait', 'fg\n'),
        ('sleep 0.1 & wait $!; echo rc=$?', 'rc=0\n'),
        ('true & true & wait; echo done', 'done\n'),
        ('echo hi |& cat', 'hi\n'),
        ('echo "a & b"', 'a & b\n'),
        ('echo $((3&2))', '2\n'),
        ('[[ "a&b" == "a&b" ]] && echo AMPTEST', 'AMPTEST\n'),
        # a keyword VALUE after '&' that is an argument stays a word
        ('true & echo if; wait', 'if\n'),
    ]

    def test_accepted(self):
        for script, expected in self.ACCEPTED:
            r = run_psh(script)
            assert r.returncode == 0, f'{script!r}: rc={r.returncode} err={r.stderr!r}'
            assert r.stdout == expected, f'{script!r}: stdout={r.stdout!r}'
