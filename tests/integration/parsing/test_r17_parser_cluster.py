"""Reappraisal #17 Tier-2 RD-parser cluster (bare `}`, time/! prefixes,
function-name validation, unified error rendering).

Every expectation here was pinned against bash 5.2 first (probe battery in
tmp/probes-r17t2-parser/); exit codes and run/not-run behavior must match.
Timing VALUES are nondeterministic, so `time` cases assert stdout and exit
codes only.
"""

import subprocess
import sys

import pytest


def _psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, timeout=15)


class TestBareRBraceAtCommandPosition:
    """MED-1: a bare `}` can never START a command (bash: rc 2, syntax
    error, NOTHING runs — psh used to run everything around it)."""

    @pytest.mark.parametrize("cmd", [
        'echo A; }; echo B',
        '}; echo B',
        '} echo x',
        '}',
        'echo hi; } 2>/dev/null; echo done',
        'true && }',
        'echo a | }',
        'if true; then }; fi',
        'case x in x) } ;; esac',
        '! }',
        'time }',
    ])
    def test_rejected_and_nothing_runs(self, cmd):
        r = _psh(cmd)
        assert r.returncode == 2, (cmd, r.stdout, r.stderr)
        assert r.stdout == '', (cmd, r.stdout)
        assert "syntax error near unexpected token '}'" in r.stderr

    def test_multiline_earlier_lines_run_then_abort(self):
        # bash runs line 1, errors on line 2, never reaches line 3.
        r = _psh('echo A\n}\necho B')
        assert r.returncode == 2
        assert r.stdout == 'A\n'
        assert 'echo B' not in r.stdout

    @pytest.mark.parametrize("cmd, out", [
        ('echo }', '}\n'),
        ('echo a } b', 'a } b\n'),
        ('case x in x) echo } ;; esac', '}\n'),
        ('{ echo hi; }', 'hi\n'),
        ('{ echo hi; } 2>/dev/null', 'hi\n'),
        ('f() { echo x; }; f', 'x\n'),
    ])
    def test_argument_and_brace_group_positions_keep_working(self, cmd, out):
        r = _psh(cmd)
        assert r.returncode == 0, (cmd, r.stderr)
        assert r.stdout == out


class TestTimeBangPrefixOrdering:
    """LOW-1: bash's pipeline_command grammar is recursive — `time` and `!`
    prefixes repeat and interleave."""

    @pytest.mark.parametrize("cmd, rc, out", [
        ('! time true', 1, ''),
        ('! time false', 0, ''),
        ('! time -p true', 1, ''),
        ('time time true', 0, ''),
        ('time time false; echo rc=$?', 0, 'rc=1\n'),
        ('! ! time true', 0, ''),
        ('time ! time true', 1, ''),
        ('! time ! true', 0, ''),
        ('! time ! false', 1, ''),
        ('time -p ! false', 0, ''),
        ('! time echo hi | cat', 1, 'hi\n'),
        # v0.602 negation-toggle semantics interact per-`!`:
        ('! time false; echo rc=$?', 0, 'rc=0\n'),
    ])
    def test_interleaved_prefixes(self, cmd, rc, out):
        r = _psh(cmd)
        assert r.returncode == rc, (cmd, r.stdout, r.stderr)
        assert r.stdout == out

    def test_time_mid_pipeline_is_external_command(self):
        # bash: `time` is a reserved word only at pipeline start; after a
        # `|` it is the EXTERNAL time command (BSD/GNU output format).
        import shutil
        if not shutil.which('time'):
            pytest.skip('no external time binary on this host')
        r = _psh('echo a | time cat')
        assert r.returncode == 0, r.stderr
        assert r.stdout == 'a\n'
        # keyword-time format is "\nreal\t..."; external is not
        assert '\nreal\t' not in r.stderr

    @pytest.mark.parametrize("cmd, rc, out", [
        ('!', 1, ''),
        ('! !', 0, ''),
        ('! ; echo after', 0, 'after\n'),
        ('time !; echo rc=$?', 0, 'rc=1\n'),
        ('! time; echo rc=$?', 0, 'rc=1\n'),
        ('{ ! ; }; echo rc=$?', 0, 'rc=1\n'),
        ('while ! ; do break; done', 0, ''),
        ('for i in 1; do !\ndone; echo rc=$?', 0, 'rc=1\n'),
    ])
    def test_prefix_before_list_terminator_is_empty_pipeline(self, cmd, rc, out):
        # bash grammar: `BANG list_terminator` / `timespec list_terminator`
        # — an empty pipeline (status 0), negated by `!` (status 1).
        r = _psh(cmd)
        assert r.returncode == rc, (cmd, r.stdout, r.stderr)
        assert r.stdout == out

    @pytest.mark.parametrize("cmd", [
        'time && echo x',
        'time || echo x',
        'time | cat',
        'time & wait',
        '{ time }',
        '( time )',
        '( ! )',
        '! && echo x',
        '! & wait',
        'case x in x) time ;; esac',
    ])
    def test_prefix_before_non_terminator_is_syntax_error(self, cmd):
        # bash REJECTS a bare prefix before anything that is not `;`,
        # newline, or EOF (rc 2, nothing runs).
        r = _psh(cmd)
        assert r.returncode == 2, (cmd, r.stdout, r.stderr)
        assert r.stdout == ''


class TestFunctionNameValidation:
    """LOW-4 (round-2 corrected): an ASSIGNMENT word followed by `()` is a
    syntax error (bash), while non-assignment words containing `=`, `+`,
    digits-first, brackets etc. are legal function names."""

    @pytest.mark.parametrize("cmd", [
        'a=b() { :; }',
        'a=b() { :; }; type a',      # phantom function must not exist
        'a+=b() { :; }',
        'a==b() { :; }',
        'a[0]=b() { :; }',
        'foo=bar() { :; }',
    ])
    def test_assignment_word_head_is_syntax_error(self, cmd):
        r = _psh(cmd)
        assert r.returncode == 2, (cmd, r.stdout, r.stderr)
        assert r.stdout == ''
        assert "syntax error near unexpected token '('" in r.stderr

    @pytest.mark.parametrize("cmd, out", [
        ('foo+bar() { echo FB; }; foo+bar', 'FB\n'),
        ('a.b+=c() { echo AIC; }; a.b+=c', 'AIC\n'),
        ('2=b() { echo TWO; }; 2=b', 'TWO\n'),
        ('2=b() { echo TWO; }; "2=b"', 'TWO\n'),
        ('[foo]() { echo BF; }; [foo]', 'BF\n'),
        ('a.b=c() { :; }; echo defined', 'defined\n'),
        ('foo.bar=() { :; }; echo defined', 'defined\n'),
        ('function foo+bar { echo FKP; }; foo+bar', 'FKP\n'),
        ('function foo+bar() { echo KFC; }; foo+bar', 'KFC\n'),
        # existing acceptances must keep working
        ('foo-bar() { echo FD; }; foo-bar', 'FD\n'),
        ('1foo() { echo D1; }; 1foo', 'D1\n'),
    ])
    def test_non_assignment_names_accepted(self, cmd, out):
        r = _psh(cmd)
        assert r.returncode == 0, (cmd, r.stderr)
        assert r.stdout == out

    def test_array_initialization_still_works(self):
        r = _psh('arr=(1 2 3); echo ${arr[1]}; declare -a d=(x y); echo ${d[0]}')
        assert r.returncode == 0, r.stderr
        assert r.stdout == '2\nx\n'


class TestUnifiedErrorRendering:
    """MED-2 (iii)/(iv): ONE canonical error format — `psh: <src>:<line>:`
    prefix + rich caret body — for both EOF-shaped and mid-input errors,
    with ABSOLUTE line numbers in both the prefix and the embedded
    (line N, column M)."""

    @pytest.mark.parametrize("cmd", ['echo a |', 'true &&', '{ echo noclose'])
    def test_eof_errors_render_rich_form(self, cmd):
        r = _psh(cmd)
        assert r.returncode == 2
        assert r.stderr.startswith('psh: -c:1: ')
        assert '^' in r.stderr          # caret line present
        assert 'TokenType.' not in r.stderr

    def test_absolute_line_in_prefix_and_message(self):
        r = _psh('echo one\necho two\necho )')
        assert r.returncode == 2
        assert r.stdout == 'one\ntwo\n'
        assert 'psh: -c:3: ' in r.stderr
        assert '(line 3, column 6)' in r.stderr

    def test_absolute_line_inside_multiline_construct(self):
        # Command starts at line 2; the error is on line 4 — bash reports
        # the ERROR's line.
        r = _psh('echo a\nif true\nthen\necho )\nfi')
        assert r.returncode == 2
        assert r.stdout == 'a\n'
        assert 'psh: -c:4: ' in r.stderr
        assert '(line 4, column 6)' in r.stderr

    def test_friendly_expected_message_end_to_end(self):
        r = _psh('if true then echo x fi')
        assert r.returncode == 2
        assert "Expected 'then', got end of input" in r.stderr
        assert "Add ';' before 'then' keyword" in r.stderr
