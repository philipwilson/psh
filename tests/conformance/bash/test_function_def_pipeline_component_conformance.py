"""Function-definition-as-PipelineComponent conformance (#20 H9, campaign S5).

Bash's grammar treats a function definition as a ``command``, so it can be a
pipeline member, negation/``time`` target, and-or-list element, or background
job. Whether the definition LEAKS into the parent shell follows the ordinary
fork rule: a single-member pipeline (``! f`` / ``time f`` / ``x && f`` /
``f > out``) runs in the current shell and the def LEAKS; a multi-member pipeline
or background forks a child whose function-table write dies with it (NO leak).

psh historically PARSE-ERRORED on every one of these forms (FunctionDef was a
Statement, not a Command, and both parsers special-cased defs above the pipeline
machinery). S5 makes FunctionDef a PipelineComponent; execution is unchanged, so
these now match bash exactly. This module pins the whole family — leak, exit
status, and stdout — against live bash, across -c / file / stdin input modes.

Full probe transcripts (all 16 rows x 5 modes, incl. eval/source): base RED and
fixed GREEN in tmp/boundary-ledgers/S5-probes/h9_{base,fixed}_<sha>.txt.
"""
import os
import subprocess
import sys
import tempfile

import pytest
from shell_oracle import resolve_bash

BASH = resolve_bash().path

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
_ENV = dict(os.environ, PYTHONPATH=_ROOT)

# Appended to each fragment: capture the construct's own rc, then whether `f`
# leaked into the parent shell. Bash and psh must agree on all three signals.
_MARKER = ('\n__RC__=$?; echo "__RC__=$__RC__"; '
           'type f >/dev/null 2>&1 && echo __LEAK__ || echo __NOLEAK__')

# (id, fragment). Every row's fragment (attempts to) define `f`.
_CASES = [
    # --- rows that were PARSE ERRORS in psh before S5 (the H9 fix) ---
    ("pipe_first",   "f() { echo hi; } | cat"),
    ("pipe_last",    "cat </dev/null | f() { echo hi; }"),
    ("pipe_middle",  "echo x | f() { cat; } | cat"),
    ("background",   "f() { echo hi; } &\nwait"),
    ("bang_nopipe",  "! f() { :; }"),
    ("bang_pipe",    "! f() { :; } | cat"),
    ("time_def",     "time f() { :; } 2>/dev/null"),
    ("and_list",     "true && f() { :; }"),
    ("or_list",      "false || f() { :; }"),
    ("two_defs_pipe", "f() { echo a; } | g() { echo b; }"),
    # --- rows that already matched bash at base (parity, must stay matched) ---
    ("standalone",   "f() { echo hi; }"),
    ("brace_pipe",   "{ f() { echo hi; }; } | cat"),
    ("subshell_pipe", "( f() { echo hi; } ) | cat"),
    ("redir_out",    "f() { :; } > out_h9.txt"),
    ("semicolon_list", "f() { :; }; true"),
    ("def_then_use", "f() { echo hi; }\nf | cat"),
]

_MODES = ["-c", "file", "stdin"]


def _run(argv0_is_bash, script, mode, cwd):
    argv = [BASH] if argv0_is_bash else [sys.executable, "-m", "psh"]
    env = None if argv0_is_bash else _ENV
    if mode == "-c":
        return subprocess.run(argv + ["-c", script], capture_output=True,
                              text=True, timeout=30, cwd=cwd, env=env,
                              stdin=subprocess.DEVNULL)
    if mode == "stdin":
        return subprocess.run(argv, input=script + "\n", capture_output=True,
                              text=True, timeout=30, cwd=cwd, env=env)
    # file
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, dir=cwd) as f:
        f.write(script + "\n")
        path = f.name
    try:
        return subprocess.run(argv + [path], capture_output=True, text=True,
                              timeout=30, cwd=cwd, env=env,
                              stdin=subprocess.DEVNULL)
    finally:
        os.unlink(path)


def _signals(out):
    """(leak, rc, body) triple extracted from a run's stdout."""
    leak = "LEAK" if "__LEAK__" in out else ("NOLEAK" if "__NOLEAK__" in out else "?")
    rc = next((ln.split("=", 1)[1] for ln in out.splitlines()
               if ln.startswith("__RC__=")), "?")
    body = [ln for ln in out.splitlines()
            if not ln.startswith("__RC__=") and ln not in ("__LEAK__", "__NOLEAK__")]
    return leak, rc, "\n".join(body)


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("case_id,fragment", _CASES, ids=[c[0] for c in _CASES])
def test_function_def_pipeline_component_matches_bash(case_id, fragment, mode):
    """psh matches bash on leak, exit status, and stdout for the whole family."""
    script = fragment + _MARKER
    with tempfile.TemporaryDirectory() as bd, tempfile.TemporaryDirectory() as pd:
        b = _run(True, script, mode, bd)
        p = _run(False, script, mode, pd)
    b_leak, b_rc, b_body = _signals(b.stdout)
    p_leak, p_rc, p_body = _signals(p.stdout)
    assert (p_leak, p_rc, p_body) == (b_leak, b_rc, b_body), (
        f"[{case_id}/{mode}] psh {(p_leak, p_rc, p_body)} != "
        f"bash {(b_leak, b_rc, b_body)}\npsh.stderr={p.stderr!r}"
    )


# --- Explicit discriminator pins (the diagnostic core of H9) ----------------

def _c(shell_is_bash, cmd, cwd):
    argv = [BASH] if shell_is_bash else [sys.executable, "-m", "psh"]
    env = None if shell_is_bash else _ENV
    return subprocess.run(argv + ["-c", cmd], capture_output=True, text=True,
                          timeout=30, cwd=cwd, env=env, stdin=subprocess.DEVNULL)


def test_single_member_pipeline_def_leaks_like_bash(tmp_path):
    """`! f() { :; }` — a single-command pipeline runs in the current shell, so
    the def LEAKS and `!` negates its success (rc 1). The discriminator vs the
    piped form."""
    cmd = "! f() { :; }; type f >/dev/null 2>&1 && echo LEAK || echo NOLEAK; echo rc=$?"
    b = _c(True, cmd, str(tmp_path))
    p = _c(False, cmd, str(tmp_path))
    assert "LEAK" in b.stdout and b.stdout == p.stdout


def test_multi_member_pipeline_def_does_not_leak_like_bash(tmp_path):
    """`f() { :; } | cat` — a real pipeline forks each member, so the def does
    NOT leak."""
    cmd = "f() { :; } | cat; type f >/dev/null 2>&1 && echo LEAK || echo NOLEAK"
    b = _c(True, cmd, str(tmp_path))
    p = _c(False, cmd, str(tmp_path))
    assert "NOLEAK" in b.stdout and b.stdout == p.stdout


def test_background_def_does_not_leak_like_bash(tmp_path):
    """`f() { :; } &` forks a background child; the def does NOT leak, rc 0."""
    cmd = "f() { :; } & wait; type f >/dev/null 2>&1 && echo LEAK || echo NOLEAK"
    b = _c(True, cmd, str(tmp_path))
    p = _c(False, cmd, str(tmp_path))
    assert "NOLEAK" in b.stdout and b.stdout == p.stdout
