"""`jobs` completed-job listing across the read-path modes (task #22 [#36]).

bash's `jobs` lists a COMPLETED background job on stdout exactly once — but the
behavior is READ-PATH dependent, which an all-`-c` pin suite missed (the
verifier bounce). Verified vs bash 5.2 with stdout/stderr separated across all
four read paths:

    -c          : completed job NOT listed (reaped eagerly; announced on stderr
                  under monitor — the deferred -c+monitor boundary notice)
    script-file : completed job LISTED once (`[1]+ Exit 1 false` / `Done`)
    stdin       : LISTED once
    interactive : NOT listed (the prompt notice reaps it first; psh's REPL does
                  the same — covered by the PTY tier)

These pins compare psh's stdout to LIVE bash in each mode (the oracle), so they
pin the exact mode-dependent text, including that an argument-less builtin lists
as `false` with no trailing space. Subprocess + timeout; serial-by-path.
"""

import subprocess
import sys

from shell_oracle import resolve_bash

BASH = resolve_bash().path

TIMEOUT = 15


def _bash_c(s):
    return subprocess.run([BASH, '-c', s], capture_output=True, text=True,
                          timeout=TIMEOUT).stdout


def _psh_c(s):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', s],
                          capture_output=True, text=True, timeout=TIMEOUT).stdout


def _script(exe, s, tmp_path):
    f = tmp_path / "job.sh"
    f.write_text(s + "\n")
    return subprocess.run(exe + [str(f)], capture_output=True, text=True,
                          timeout=TIMEOUT).stdout


def _bash_script(s, tmp_path):
    return _script([BASH], s, tmp_path)


def _psh_script(s, tmp_path):
    return _script([sys.executable, '-m', 'psh'], s, tmp_path)


def _bash_stdin(s):
    return subprocess.run([BASH], input=s + "\n", capture_output=True,
                          text=True, timeout=TIMEOUT).stdout


def _psh_stdin(s):
    return subprocess.run([sys.executable, '-m', 'psh'], input=s + "\n",
                          capture_output=True, text=True, timeout=TIMEOUT).stdout


# A finished BUILTIN (false/true) and a finished EXTERNAL, framed by markers.
FALSE = 'false & sleep 0.3; echo A:; jobs; echo B:'
TRUE = 'true & sleep 0.3; echo A:; jobs; echo B:'
EXTERNAL = 'sleep 0.1 & sleep 0.3; echo A:; jobs; echo B:'  # external, completes
JOBS_N = ('sleep 5 & sleep 0.2 & echo A:; jobs -n; sleep 0.4; '
          'echo B:; jobs -n; echo C:; kill %1 2>/dev/null')


# ---- script-file mode: completed job LISTED once, exact bash parity ----------

def test_completed_builtin_listed_once_script(tmp_path):
    assert _psh_script(FALSE, tmp_path) == _bash_script(FALSE, tmp_path)


def test_completed_builtin_done_label_script(tmp_path):
    # exit 0 -> `Done`, exit 1 -> `Exit 1`; and no trailing space after `false`.
    out = _psh_script(TRUE, tmp_path)
    assert out == _bash_script(TRUE, tmp_path)
    assert 'Done' in out


def test_completed_external_listed_once_script(tmp_path):
    assert _psh_script(EXTERNAL, tmp_path) == _bash_script(EXTERNAL, tmp_path)


def test_jobs_n_completion_listed_once_script(tmp_path):
    assert _psh_script(JOBS_N, tmp_path) == _bash_script(JOBS_N, tmp_path)


# ---- stdin mode: same (LISTED once) ------------------------------------------

def test_completed_builtin_listed_once_stdin():
    assert _psh_stdin(FALSE) == _bash_stdin(FALSE)


def test_completed_external_listed_once_stdin():
    assert _psh_stdin(EXTERNAL) == _bash_stdin(EXTERNAL)


# ---- -c mode: completed job SUPPRESSED (stdout empty), exact bash parity ------

def test_completed_builtin_suppressed_c_mode():
    out = _psh_c(FALSE)
    assert out == _bash_c(FALSE)
    assert 'Exit' not in out and 'Done' not in out


def test_completed_external_suppressed_c_mode():
    assert _psh_c(EXTERNAL) == _bash_c(EXTERNAL)


# ---- trailing-space regression: argument-less builtin bg job -----------------

def test_argument_less_builtin_has_no_trailing_space_script(tmp_path):
    """`false &` lists as `...false`, never `...false ` (bg builtin command
    string was joined with a trailing space when arg-less)."""
    out = _psh_script(FALSE, tmp_path)
    line = next(ln for ln in out.splitlines() if 'false' in ln and 'Exit' in ln)
    assert line == line.rstrip(), repr(line)
    assert line.endswith('false'), repr(line)
