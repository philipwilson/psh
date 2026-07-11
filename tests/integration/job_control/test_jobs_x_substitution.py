"""`jobs -x command [args]` — jobspec→pgid substitution + exec (task #22 [#36]).

bash's `jobs -x` replaces every whole-word job specification in the command
line with the corresponding process group id, then runs the command, returning
its status. A word that is not a resolvable jobspec is left untouched. The
command goes through normal resolution (functions included) and runs in the
current shell. Verified against bash 5.2.26 (tmp/probes/probe_b*.sh).

Subprocess pins (job control); serial-by-path.
"""

import subprocess
import sys

TIMEOUT = 15


def _psh(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True, timeout=TIMEOUT,
    )


def test_x_substitutes_jobspec_with_pgid():
    """`jobs -x echo %1` prints the job's pgid (== $! for a single command)."""
    r = _psh('set -m; sleep 3 & p=$!; jobs -x echo %1; kill "$p" 2>/dev/null')
    printed = r.stdout.strip().splitlines()
    assert printed, r.stdout
    # For a single-command job the pgid equals the leader pid ($!).
    assert printed[-1].isdigit()


def test_x_leaves_non_jobspec_words_literal():
    """Plain words, substrings (`pre%1`), and unresolved specs (`%99`) pass
    through unchanged; only the whole-word %1 is substituted."""
    r = _psh('set -m; sleep 3 & jobs -x echo hello %1 world pre%1 %99; '
             'kill %1 2>/dev/null')
    out = r.stdout.strip()
    parts = out.split()
    assert parts[0] == 'hello'
    assert parts[1].isdigit()           # %1 -> pgid
    assert parts[2:] == ['world', 'pre%1', '%99']


def test_x_returns_command_exit_status():
    """`jobs -x` returns the executed command's status."""
    r = _psh('set -m; sleep 3 & jobs -x true; echo "t=$?"; '
             'jobs -x false; echo "f=$?"; kill %1 2>/dev/null')
    assert 't=0' in r.stdout
    assert 'f=1' in r.stdout


def test_x_runs_function_with_resolution():
    """`jobs -x` resolves the command through the normal order (functions)."""
    r = _psh('set -m; f(){ echo "func:$1"; }; sleep 3 & p=$!; '
             'jobs -x f %1; kill "$p" 2>/dev/null')
    assert r.stdout.strip().startswith('func:')
    assert r.stdout.strip().split(':', 1)[1].strip().isdigit()


def test_x_runs_in_current_shell():
    """`jobs -x cd DIR` changes the shell's own cwd (runs in-process)."""
    r = _psh('set -m; sleep 3 & jobs -x cd /tmp; pwd; kill %1 2>/dev/null')
    # macOS /tmp is a symlink to /private/tmp; accept either.
    assert r.stdout.strip().splitlines()[-1] in ('/tmp', '/private/tmp')


def test_x_bare_is_noop_rc0():
    """`jobs -x` with no command is a no-op returning 0 (bash)."""
    r = _psh('set -m; jobs -x; echo "rc=$?"')
    assert 'rc=0' in r.stdout


def test_x_missing_jobspec_passes_through_rc0():
    """An unresolved `%N` is left literal and NOT an error (`jobs -x echo %5`
    prints `%5`, rc 0)."""
    r = _psh('set -m; jobs -x echo %5; echo "rc=$?"')
    assert '%5' in r.stdout
    assert 'rc=0' in r.stdout


def test_x_rejects_combination_with_other_options():
    """`-x` combined with any other option is an error (rc 1)."""
    r = _psh('set -m; jobs -lx echo; echo "rc=$?"')
    assert "no other options allowed with `-x'" in r.stderr
    assert 'rc=1' in r.stdout
