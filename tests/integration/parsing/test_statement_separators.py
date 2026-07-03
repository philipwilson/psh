"""Statement-boundary validation and and-or-level backgrounding (RD parser).

Reappraisal #15 findings A1 + A3. Before the fix, psh re-entered
parse_statement without requiring a separator, so `echo (ls)` EXECUTED
echo and then ls (bash: rc=2 syntax error), and subshell/brace groups
consumed a trailing '&' themselves, so `(a) && (b) &` ran the first
group in the FOREGROUND (bash backgrounds the whole and-or list).

Every case here was verified against bash 5.2 (see
tmp/r15_a_truth_table.py history). Run in subprocesses because syntax
errors must abort the whole -c input, like bash.
"""

import subprocess
import sys
import time


def run_psh(script):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                          capture_output=True, text=True, timeout=15)


class TestMissingSeparatorRejected:
    """A statement not ended at a separator/terminator is a syntax error (A1)."""

    REJECTED = [
        'echo (ls)',
        'echo foo(bar)',
        'x=1 (echo sub)',
        'if true; then echo hi (uname); fi',
        '{ echo hi (uname); }',
        'fi(uname)',
        '(echo a)(echo b)',
        '(echo a) foo',
        '{ echo a; } { echo b; }',
        '((1+1)) echo x',
        '[[ -n x ]] echo y',
        'case x in a) (echo s)(echo t);; esac',
        'while true; do echo hi (uname); done',
        'f() { echo hi (uname); }',
        'echo hi (uname) | cat',
    ]

    def test_rejected_with_syntax_error(self):
        for script in self.REJECTED:
            r = run_psh(script)
            assert r.returncode == 2, f'{script!r}: rc={r.returncode}'
            assert r.stdout == '', f'{script!r}: executed, stdout={r.stdout!r}'
            # 'fi(uname)' is rejected by command-start validation ("Expected
            # command"); the rest by the boundary guard ("syntax error").
            assert r.stderr, f'{script!r}: no error reported'

    def test_eval_returns_2(self):
        """eval of an unseparated statement fails with 2 (bash) — nothing runs."""
        r = run_psh('eval "echo (ls)"; echo rc=$?')
        assert r.returncode == 0
        assert r.stdout == 'rc=2\n'
        assert 'syntax error' in r.stderr.lower()

    def test_command_substitution_rejected(self):
        """`x=$(echo (uname))` must not execute uname.

        psh parses substitution text at expansion time in the child, so the
        rejection is rc=2 there (bash validates at parse time of the outer
        command and exits 127 — documented divergence; the misexecution is
        what matters).
        """
        r = run_psh('x=$(echo (uname)); echo "x=[$x]"')
        assert 'syntax error' in r.stderr.lower()
        assert 'Darwin' not in r.stdout and 'Linux' not in r.stdout


class TestAmpersandJunkRejected:
    """'&' is a separator: another operator right after it is a syntax error."""

    REJECTED = [
        '(echo a) & | cat',
        '(echo a) & && echo b',
        '{ echo a; } & | cat',
        'echo a & | cat',
        'echo a & && echo b',
        'echo a & ; echo b',
        'echo a &; echo b',
        '(echo a) &; echo b',
    ]

    def test_rejected_with_syntax_error(self):
        for script in self.REJECTED:
            r = run_psh(script)
            assert r.returncode == 2, f'{script!r}: rc={r.returncode}'
            assert r.stdout == '', f'{script!r}: executed, stdout={r.stdout!r}'

    def test_ampersand_case_terminator_allowed(self):
        """`& ;;` inside a case item stays legal (bash)."""
        r = run_psh('case x in x) echo a & ;; esac; wait')
        assert r.returncode == 0
        assert r.stdout == 'a\n'


class TestConsecutiveSemicolonRejected:
    """A `;` with no command in front of it is a syntax error (reappraisal #16).

    `;` terminates a command; only blank lines may follow before the next
    command. psh used to skip separators greedily, so `echo a; ; echo b` ran
    BOTH commands. Now the extra `;` is left for parse_statement to reject, in
    every command-list context (top level, loop/if/case bodies, conditions).
    bash 5.2 rejects each of these with rc=2.
    """

    # Single-line -c input is parsed fully before executing, so a rejected
    # program runs nothing. (Multi-line `echo a\n; echo b` executes line 1
    # then errors on line 2 — psh matches bash there too, but it is a
    # different, incremental-execution behavior and not asserted here.)
    REJECTED = [
        'echo a; ; echo b',
        'for i in 1 2; do echo $i; ; echo y; done',
        '{ echo a; ; echo b; }',
        'if true; then echo a; ; echo b; fi',
        'if true; ; then echo a; fi',             # condition
        'case x in x) echo a; ; echo b;; esac',
        'while true; ; do :; done',
    ]

    def test_rejected(self):
        for script in self.REJECTED:
            r = run_psh(script)
            assert r.returncode == 2, f'{script!r}: rc={r.returncode}'
            assert r.stdout == '', f'{script!r}: executed, stdout={r.stdout!r}'
            assert r.stderr, f'{script!r}: no error reported'

    # Legal separator runs must keep working: a single `;`, trailing `;`,
    # `;` then newlines, and multiple blank lines.
    ACCEPTED = [
        ('echo a; echo b', 'a\nb\n'),
        ('echo a;', 'a\n'),
        ('echo a;\necho b', 'a\nb\n'),
        ('echo a\n\necho b', 'a\nb\n'),
        ('for i in 1; do echo $i; done', '1\n'),
        ('{ echo a; }', 'a\n'),
        ('if true; then echo a; echo b; fi', 'a\nb\n'),
        ('case x in x) echo a; echo b;; esac', 'a\nb\n'),
    ]

    def test_accepted(self):
        for script, expected in self.ACCEPTED:
            r = run_psh(script)
            assert r.returncode == 0, f'{script!r}: rc={r.returncode} err={r.stderr!r}'
            assert r.stdout == expected, f'{script!r}: stdout={r.stdout!r}'


class TestBackgroundScopesWholeList:
    """`(a) && (b) &` backgrounds the whole and-or list, not the last group (A3)."""

    def test_andor_list_of_groups_backgrounds_whole_list(self):
        """bash order: fg first (well before the sleep), then a, then b."""
        start = time.monotonic()
        p = subprocess.Popen(
            [sys.executable, '-m', 'psh', '-c',
             '(sleep 0.3; echo a) && (echo b) & echo fg; wait'],
            stdout=subprocess.PIPE, text=True)
        first = p.stdout.readline()
        elapsed = time.monotonic() - start
        rest = p.stdout.read()
        assert p.wait() == 0
        assert first == 'fg\n' and rest == 'a\nb\n'
        assert elapsed < 0.3, f'fg took {elapsed:.3f}s — first group ran in foreground'

    def test_single_subshell_background(self):
        r = run_psh('( sleep 0.1 ) & wait; echo done')
        assert r.returncode == 0 and r.stdout == 'done\n'

    def test_single_brace_group_background(self):
        r = run_psh('{ sleep 0.1; } & wait; echo done')
        assert r.returncode == 0 and r.stdout == 'done\n'

    def test_brace_group_redirect_then_background(self):
        r = run_psh('{ echo x; } > /dev/null & wait; echo done')
        assert r.returncode == 0 and r.stdout == 'done\n'

    def test_group_background_then_next_statement(self):
        r = run_psh('(echo a) & (echo b) & wait')
        assert r.returncode == 0
        assert sorted(r.stdout.splitlines()) == ['a', 'b']


class TestBoundariesStillAccepted:
    """Constructs that legally follow a statement keep parsing (regression set)."""

    ACCEPTED = [
        ('f() { :; }; f; echo ok', 'ok\n'),
        ('function f { :; }; f; echo ok', 'ok\n'),
        ('case x in (x) echo m;; esac', 'm\n'),
        ('echo $(echo hi)', 'hi\n'),
        ('(( 1+1 )); echo $?', '0\n'),
        ('a=(1 2); echo ${a[1]}', '2\n'),
        ('declare -a b=(3 4); echo ${b[0]}', '3\n'),
        ('if (true); then echo y; fi', 'y\n'),
        ('if (true) then echo y; fi', 'y\n'),
        ('if ((1)) then echo t; fi', 't\n'),
        ('if [[ -n x ]] then echo t; fi', 't\n'),
        ('while (false) do :; done; echo w', 'w\n'),
        ('echo "(x)"', '(x)\n'),
        ('echo \\( \\)', '( )\n'),
        ('! (false); echo $?', '0\n'),
        ('echo a & wait; echo b', 'a\nb\n'),
        ('(echo a &); wait', 'a\n'),
        # break/continue leave their (unreachable) redirect in the stream —
        # the pinned pre-existing shape; must not become a syntax error.
        ('while true; do break > /dev/null; done; echo rc=$?', 'rc=0\n'),
        ('for i in 1; do continue > /dev/null; done; echo rc=$?', 'rc=0\n'),
    ]

    def test_accepted(self):
        for script, expected in self.ACCEPTED:
            r = run_psh(script)
            assert r.returncode == 0, f'{script!r}: rc={r.returncode} err={r.stderr!r}'
            assert r.stdout == expected, f'{script!r}: stdout={r.stdout!r}'
            assert r.stderr == '', f'{script!r}: stderr={r.stderr!r}'

    def test_time_subshell(self):
        r = run_psh('time (sleep 0)')
        assert r.returncode == 0 and r.stdout == ''
        assert 'real' in r.stderr  # timing report, not an error
