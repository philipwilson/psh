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

from shell_oracle import is_comparable, run_bash, run_psh

TIMEOUT = 15


def _bash_c(s):
    r = run_bash(['-c', s], timeout=TIMEOUT)
    assert is_comparable(r), r
    return r.stdout


def _psh_c(s):
    r = run_psh(['-c', s], timeout=TIMEOUT)
    assert is_comparable(r), r
    return r.stdout


def _script(runner, s, tmp_path):
    f = tmp_path / "job.sh"
    f.write_text(s + "\n")
    r = runner([str(f)], timeout=TIMEOUT)
    assert is_comparable(r), r
    return r.stdout


def _bash_script(s, tmp_path):
    return _script(run_bash, s, tmp_path)


def _psh_script(s, tmp_path):
    return _script(run_psh, s, tmp_path)


def _bash_stdin(s):
    r = run_bash([], stdin_data=s + "\n", stdin_mode='pipe', timeout=TIMEOUT)
    assert is_comparable(r), r
    return r.stdout


def _psh_stdin(s):
    r = run_psh([], stdin_data=s + "\n", stdin_mode='pipe', timeout=TIMEOUT)
    assert is_comparable(r), r
    return r.stdout


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
    # Report the whole listing when the line is missing. This row failed once
    # on the Linux nightly (run 30143337081) with a bare StopIteration, which
    # said nothing about what psh had actually printed; it did not recur at
    # base (run 30154694015) and psh matches bash locally, so the cause is
    # still open and the next occurrence needs to arrive carrying its evidence.
    matches = [ln for ln in out.splitlines() if 'false' in ln and 'Exit' in ln]
    assert matches, f"no completed-job line for `false` in listing: {out!r}"
    line = matches[0]
    assert line == line.rstrip(), repr(line)
    assert line.endswith('false'), repr(line)
