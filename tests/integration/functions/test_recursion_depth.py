"""Function recursion depth — the implicit FUNCNEST (reappraisal #17 Tier 2).

psh's recursive executor burns ~18 Python frames per shell function call, so
CPython's default recursion limit of 1000 capped shell recursion at ~50 calls
(bash handles 5000+), and the failure surfaced wherever the deepest Python
frame happened to be — e.g. as a misleading "arithmetic error: expression too
deeply nested" from the ``$(($1-1))`` decrement, or (under strict-errors, the
suite default) as a raw Python traceback.

Fixed three ways (v0.607):
- ``psh.shell`` raises the interpreter recursion limit at startup
  (``RECURSION_LIMIT`` = 40,000 → ~2,200 shell-call depth);
- ``FunctionOperationExecutor.execute_function_call`` converts a runaway
  ``RecursionError`` at the function-call boundary into bash's FUNCNEST
  diagnostic ("NAME: maximum function nesting level exceeded") and aborts the
  current top-level command via TopLevelAbort — same semantics as an explicit
  ``FUNCNEST=N`` (verified against bash 5.2), the shell survives;
- ``RecursionError`` joined the expected-error taxonomy so the function-less
  paths report cleanly even under strict-errors.

All tests run psh in a subprocess: recursion tests must not burn the test
runner's own stack, and the suite's PSH_STRICT_ERRORS=1 environment is
inherited, so every case here also proves the no-traceback guarantee under
strict mode.
"""

import os
import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

BASH = resolve_bash().path


def _psh_c(cmd, strict=None):
    env = dict(os.environ)
    if strict is True:
        env['PSH_STRICT_ERRORS'] = '1'
    elif strict is False:
        env.pop('PSH_STRICT_ERRORS', None)
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, env=env, timeout=120)


RECURSE_N = 'f(){ [ $1 -le 0 ] && return 0; f $(($1-1)); }; f %d; echo rc=$?'


@pytest.mark.parametrize('depth', [100, 1000])
def test_deep_recursion_succeeds(depth):
    """Recursion to bash-realistic depths returns 0 (was: died at ~50)."""
    r = _psh_c(RECURSE_N % depth)
    assert r.stdout == 'rc=0\n'
    assert r.stderr == ''
    assert r.returncode == 0


def test_deep_recursion_matches_bash():
    cmd = RECURSE_N % 500
    psh = _psh_c(cmd)
    bash = subprocess.run([BASH, '-c', cmd], capture_output=True, text=True,
                          timeout=120)
    assert psh.stdout == bash.stdout == 'rc=0\n'
    assert psh.returncode == bash.returncode == 0


def test_infinite_recursion_clean_funcnest_diagnostic():
    """g(){ g; }; g → FUNCNEST-style message, rc 1, rest of list aborted.

    (bash itself segfaults here without FUNCNEST; with FUNCNEST=N it prints
    "g: maximum function nesting level exceeded (N)" and aborts the current
    command — psh's implicit ceiling mirrors that behavior.)
    """
    r = _psh_c('g(){ g; }; g; echo after=$?')
    assert 'g: maximum function nesting level exceeded' in r.stderr
    assert 'Traceback' not in r.stderr
    assert 'after' not in r.stdout  # whole -c list aborts, like FUNCNEST
    assert r.returncode == 1


@pytest.mark.parametrize('strict', [True, False])
def test_infinite_recursion_no_traceback_both_modes(strict):
    """RecursionError is an expected shell error: no traceback even strict."""
    r = _psh_c('g(){ g; }; g', strict=strict)
    assert 'Traceback' not in r.stderr
    assert 'maximum function nesting level exceeded' in r.stderr
    assert r.returncode == 1


def test_not_mislabeled_as_arithmetic_error():
    """The old failure surfaced at the deepest frame — often arithmetic —
    as "expression too deeply nested". It must name function nesting now."""
    r = _psh_c('f(){ f $(($1-1)); }; f 100000')
    assert 'expression too deeply nested' not in r.stderr
    assert 'f: maximum function nesting level exceeded' in r.stderr


def test_script_resumes_at_next_line():
    """Like FUNCNEST: abort the current top-level command, resume next line."""
    r = _psh_c('g(){ g; }\ng\necho survived=$?')
    assert r.stdout == 'survived=1\n'
    assert r.returncode == 0
    assert 'maximum function nesting level exceeded' in r.stderr


def test_mutual_recursion_clean():
    r = _psh_c('a(){ b; }; b(){ a; }; a')
    assert 'maximum function nesting level exceeded' in r.stderr
    assert 'Traceback' not in r.stderr
    assert r.returncode == 1


def test_mutual_recursion_within_ceiling_succeeds():
    r = _psh_c('a(){ [ $1 -le 0 ] && return 0; b $(($1-1)); }; '
               'b(){ a $1; }; a 400; echo rc=$?')
    assert r.stdout == 'rc=0\n'
    assert r.returncode == 0


def test_recursion_through_eval_clean():
    """eval frames must not swallow the RecursionError on its way to the
    function-call boundary (execute_builtin_guarded re-raises it)."""
    r = _psh_c('f(){ eval f; }; f')
    assert 'f: maximum function nesting level exceeded' in r.stderr
    assert 'Traceback' not in r.stderr
    assert r.returncode == 1


def test_recursion_in_command_substitution_child():
    """Runaway recursion inside $(...) fails the CHILD cleanly; the parent
    continues (bash's child segfaults → status 139; psh's reports → 1)."""
    r = _psh_c('f(){ f; }; x=$(f); echo after=$? x=[$x]')
    assert r.stdout == 'after=1 x=[]\n'
    assert 'maximum function nesting level exceeded' in r.stderr
    assert 'Traceback' not in r.stderr
    assert r.returncode == 0


def test_recursion_in_pipeline_member():
    """A pipeline member's runaway recursion must not hang or traceback."""
    r = _psh_c('g(){ g; }; g | cat; echo after=$?')
    assert r.stdout == 'after=0\n'  # last member (cat) exits 0, like bash
    assert 'Traceback' not in r.stderr


def test_infinite_source_recursion_is_a_resource_limit(tmp_path):
    """A function-less runaway (infinite `source`) reports a resource-limit
    diagnostic at the top level, NOT the internal-defect "unexpected error:"
    prefix (scripting appraisal 2026-07-07 finding #4).

    bash SEGFAULTS on this (rc 139); psh degrades to rc 1 with a clean message.
    """
    selfrec = tmp_path / "selfrec.sh"
    selfrec.write_text(f"source {selfrec}\n")
    r = _psh_c(f"source {selfrec}")
    assert r.returncode == 1
    assert 'maximum recursion depth exceeded' in r.stderr
    assert 'unexpected error' not in r.stderr
    assert 'Traceback' not in r.stderr
