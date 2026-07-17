"""The `time` reserved word (reappraisal #14 Tier 2).

`time [-p] PIPELINE` times the whole pipeline and reports real/user/sys to
stderr; psh previously had no `time` keyword, so `time cmd` ran the external
`/usr/bin/time`. Timing VALUES are non-deterministic, so these assert the
output SHAPE (bash's default and `-p` formats), that the command still runs,
and that `time` parses as a pipeline prefix before compound commands (the
M1 leftover: `time while`, `time [[ ]]`). Verified against bash 5.2.
"""

import re
import subprocess
import sys

from shell_oracle import resolve_bash

BASH = resolve_bash().path


def _psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


def _bash(cmd):
    return subprocess.run([BASH, '-c', cmd], capture_output=True, text=True)


# bash default TIMEFORMAT: blank line, then real/user/sys as <m>m<s.SSS>s.
_DEFAULT_RE = re.compile(
    r'\nreal\t\d+m\d+\.\d{3}s\nuser\t\d+m\d+\.\d{3}s\nsys\t\d+m\d+\.\d{3}s\n\Z')
# `-p` POSIX format: real/user/sys as seconds with 2 decimals, space-separated.
_POSIX_RE = re.compile(
    r'\Areal \d+\.\d{2}\nuser \d+\.\d{2}\nsys \d+\.\d{2}\n\Z')


def test_runs_command_and_reports_default_format():
    r = _psh('time echo hi')
    assert r.stdout == 'hi\n'
    assert _DEFAULT_RE.search(r.stderr), repr(r.stderr)
    assert r.returncode == 0


def test_posix_format():
    r = _psh('time -p echo hi')
    assert r.stdout == 'hi\n'
    assert _POSIX_RE.match(r.stderr), repr(r.stderr)


def test_times_whole_pipeline():
    r = _psh('time echo hi | cat')
    assert r.stdout == 'hi\n'
    assert _DEFAULT_RE.search(r.stderr)


def test_reports_pipeline_exit_status():
    # The timed pipeline's status is the shell's $? (last stage).
    r = _psh('time false; echo "rc=$?"')
    assert 'rc=1' in r.stdout


def test_time_before_while_loop():
    # M1 leftover: `time while ...` must parse (time keeps command position).
    r = _psh('time while false; do :; done; echo done')
    assert 'done' in r.stdout
    assert _DEFAULT_RE.search(r.stderr)


def test_time_before_double_bracket():
    r = _psh('time [[ -z x ]]; echo "rc=$?"')
    assert 'rc=1' in r.stdout


# A program that is EXACTLY one timed compound must keep the timing report:
# `_bare_top_level_compound` used to unwrap the lone Pipeline (guarding
# `negated` but not its `timed` sibling), silently dropping the report. A
# trailing statement masked the bug (test_time_before_while_loop), so these
# have nothing after the compound. Verified against bash 5.2.
def test_time_lone_if():
    r = _psh('time if true; then echo hi; fi')
    assert r.stdout == 'hi\n'
    assert _DEFAULT_RE.search(r.stderr), repr(r.stderr)
    assert r.returncode == 0


def test_time_lone_for():
    r = _psh('time for i in 1 2; do :; done')
    assert r.stdout == ''
    assert _DEFAULT_RE.search(r.stderr), repr(r.stderr)


def test_time_lone_while():
    r = _psh('time while false; do :; done')
    assert r.stdout == ''
    assert _DEFAULT_RE.search(r.stderr), repr(r.stderr)


def test_time_before_brace_group():
    r = _psh('time { echo a; echo b; }')
    assert r.stdout == 'a\nb\n'


def test_time_alone_times_empty():
    r = _psh('time')
    assert r.stdout == ''
    assert _DEFAULT_RE.search(r.stderr)
    assert r.returncode == 0


def test_negated_timed_pipeline():
    r = _psh('time ! false; echo "rc=$?"')
    assert 'rc=0' in r.stdout


# Regressions: `time` is only a keyword at command position (matches bash).
def test_time_as_argument_is_literal():
    r = _psh('echo time')
    assert r.stdout == 'time\n'


def test_time_as_variable():
    r = _psh('time=5; echo "$time"')
    assert r.stdout == '5\n'


def test_time_as_loop_variable():
    r = _psh('for time in a b; do echo "$time"; done')
    assert r.stdout == 'a\nb\n'


def test_type_reports_keyword():
    r = _psh('type time')
    assert 'keyword' in r.stdout
