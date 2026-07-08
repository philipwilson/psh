"""Temporary-environment visibility ledger (opening artifact for the full
``temporary_env`` follow-up).

A ``VAR=x cmd`` prefix over a builtin/external binds ``VAR`` as an exported
shell variable for the command's duration (PSH's Phase-4 model). bash instead
keeps it in a SEPARATE temporary environment that NAME LOOKUP consults but the
whole-table ENUMERATIONS (``set`` / ``export -p``) skip.

This battery pins both halves against live bash:

* the name-lookup behaviors PSH already matches (``$VAR``, ``declare -p VAR`` as
  ``declare -x``, ``${VAR@a}``==x, external env, function binding, teardown) —
  these are behavior-preservation locks for the mutate/rollback -> overlay
  materialization swap; and
* the THREE enumeration-visibility divergences PSH currently has, asserted as
  the CURRENT psh behavior with a note that closing them (full temporary_env in
  the variable-lookup path) is the tracked follow-up. When that lands, the three
  ``divergence`` assertions flip to equal bash.

Derived from the 16-case visibility probe run 2026-07-08 (worktree-psh vs bash).
"""

import os
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="needs a live bash to compare against")


def _clean_env():
    env = dict(os.environ)
    for k in ("DISPLAY", "XAUTHORITY"):
        env.pop(k, None)
    return env


def _run(argv, cmd):
    return subprocess.run(argv + [cmd], capture_output=True, text=True,
                          env=_clean_env(), cwd="/")


def _bash(cmd):
    return _run(["bash", "--noprofile", "--norc", "-c"], cmd)


def _psh(cmd):
    return _run([sys.executable, "-m", "psh", "--norc", "-c"], cmd)


# (label, command) — the name-lookup behaviors PSH matches bash on.
_MATCHING = [
    ("declare_p_specific", 'FOO=bar declare -p FOO 2>&1'),
    ("attribute_op_a", 'FOO=bar eval "echo attrs=${FOO@a}"'),
    ("command_env_builtin", 'FOO=bar command env 2>&1 | grep "^FOO=" || echo NONE'),
    ("printenv_external", 'FOO=bar printenv FOO 2>&1 || echo NONE'),
    ("func_export_p", 'f(){ export -p | grep FOO || echo NONE; }; FOO=bar f'),
    ("func_declare_p", 'f(){ declare -p FOO 2>&1; }; FOO=bar f'),
    ("func_attrs", 'f(){ echo "attrs=${FOO@a}"; }; FOO=bar f'),
    ("after_declare_p_gone", 'FOO=bar true; declare -p FOO >/dev/null 2>&1 && echo SET || echo GONE'),
    ("after_printenv_gone", 'FOO=bar true; printenv FOO >/dev/null 2>&1 && echo SET || echo GONE'),
    ("override_export_restored_after", 'export E=orig; E=temp true; printenv E'),
    ("override_export_visible_during", 'export E=orig; E=temp printenv E'),
]


@pytest.mark.parametrize("label,cmd", _MATCHING, ids=[c[0] for c in _MATCHING])
def test_name_lookup_behavior_matches_bash(label, cmd):
    b, p = _bash(cmd), _psh(cmd)
    assert (p.returncode, p.stdout) == (b.returncode, b.stdout), (
        f"{label}: psh {p.returncode} {p.stdout!r} != bash {b.returncode} {b.stdout!r}")


# The three enumeration-visibility divergences: bash's temporary_env is skipped
# by whole-table enumerations; PSH's exported binding is not. Asserted as the
# CURRENT psh behavior — the tracked full-temporary_env follow-up flips these to
# equal bash. If a future change makes psh match bash here, update this test.
class TestKnownEnumerationDivergences:
    def test_prefix_var_appears_in_export_p_unlike_bash(self):
        cmd = 'FOO=bar export -p 2>&1 | grep "^declare -x FOO=" || echo NONE'
        assert _bash(cmd).stdout == "NONE\n"                      # bash: hidden
        assert _psh(cmd).stdout == 'declare -x FOO="bar"\n'       # psh: shown

    def test_prefix_var_appears_in_set_unlike_bash(self):
        cmd = 'FOO=bar set 2>&1 | grep "^FOO=" || echo NONE'
        assert _bash(cmd).stdout == "NONE\n"                      # bash: hidden
        assert _psh(cmd).stdout == "FOO=bar\n"                    # psh: shown

    def test_override_shows_temp_in_export_p_unlike_bash(self):
        cmd = 'export E=orig; E=temp export -p 2>&1 | grep "^declare -x E="'
        assert _bash(cmd).stdout == 'declare -x E="orig"\n'       # bash: original
        assert _psh(cmd).stdout == 'declare -x E="temp"\n'        # psh: overridden
