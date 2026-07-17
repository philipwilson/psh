"""Temporary-environment visibility ledger (full ``temporary_env``, CLOSED
2026-07-09).

A ``VAR=x cmd`` prefix over a builtin/external now keeps ``VAR`` in a SEPARATE
temporary environment (ScopeManager.command_temp_env) that NAME LOOKUP consults
but whole-table ENUMERATIONS (``set`` / ``export -p`` / ``declare -p`` with no
name) skip — matching bash. It used to bind ``VAR`` as an exported shell
variable for the command's duration (PSH's Phase-4 model), which LEAKED into
those enumerations.

This battery pins both halves against live bash:

* the name-lookup behaviors (``$VAR``, ``declare -p VAR`` as ``declare -x``,
  ``${VAR@a}``==x, external env, function binding, teardown) — behavior-
  preservation locks across the swap to the temporary-environment model; and
* the THREE enumeration-visibility behaviors that were divergences before the
  swap and now EQUAL bash (``set`` / ``export -p`` hide the prefix var; an
  override shows the original exported value).

Derived from the 16-case visibility probe run 2026-07-08 (worktree-psh vs bash).
"""

import os
import subprocess
import sys

import pytest
from shell_oracle import try_resolve_bash

_ORACLE = try_resolve_bash()
pytestmark = pytest.mark.skipif(
    _ORACLE is None, reason="needs a live bash to compare against")


def _clean_env():
    env = dict(os.environ)
    for k in ("DISPLAY", "XAUTHORITY"):
        env.pop(k, None)
    return env


def _run(argv, cmd):
    return subprocess.run(argv + [cmd], capture_output=True, text=True,
                          env=_clean_env(), cwd="/")


def _bash(cmd):
    return _run([_ORACLE.path, "--noprofile", "--norc", "-c"], cmd)


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


# The three enumeration-visibility divergences, NOW CLOSED (full temporary_env,
# 2026-07-09): a ``VAR=x cmd`` prefix over a builtin/external is a SEPARATE
# temporary environment (ScopeManager.command_temp_env) that name lookup
# consults but whole-table enumerations skip — so ``set`` / ``export -p`` /
# ``declare -p`` (no name) no longer list it, and an override shows the ORIGINAL
# exported value. psh now EQUALS bash on all three.
class TestEnumerationSkipsTemporaryEnv:
    def test_prefix_var_hidden_from_export_p(self):
        cmd = 'FOO=bar export -p 2>&1 | grep "^declare -x FOO=" || echo NONE'
        assert _psh(cmd).stdout == _bash(cmd).stdout             # both: NONE
        assert _psh(cmd).stdout == "NONE\n"

    def test_prefix_var_hidden_from_set(self):
        cmd = 'FOO=bar set 2>&1 | grep "^FOO=" || echo NONE'
        assert _psh(cmd).stdout == _bash(cmd).stdout             # both: NONE
        assert _psh(cmd).stdout == "NONE\n"

    def test_override_shows_original_in_export_p(self):
        cmd = 'export E=orig; E=temp export -p 2>&1 | grep "^declare -x E="'
        assert _psh(cmd).stdout == _bash(cmd).stdout             # both: orig
        assert _psh(cmd).stdout == 'declare -x E="orig"\n'


# The persistence row (`V=hi export V`): an attribute-setting builtin
# (export/readonly/declare -x) named on a temporary-environment binding PROMOTES
# it to a real exported/readonly shell variable that PERSISTS past the command,
# carrying the temp value (which wins over any real same-name variable). Was a
# no-op in psh (the attribute applied only to the scope stack, missing the temp
# binding); now equals bash.
class TestAttributeBuiltinPromotesTemporaryEnv:
    def test_export_valueless_promotes(self):
        cmd = 'V=hi export V; declare -p V 2>&1'
        assert _psh(cmd).stdout == _bash(cmd).stdout
        assert _psh(cmd).stdout == 'declare -x V="hi"\n'

    def test_readonly_valueless_promotes_with_export(self):
        cmd = 'V=hi readonly V; declare -p V 2>&1'
        assert _psh(cmd).stdout == _bash(cmd).stdout
        assert _psh(cmd).stdout == 'declare -rx V="hi"\n'

    def test_export_promotes_temp_value_over_existing_real(self):
        cmd = 'export E=orig; E=temp export E; declare -p E 2>&1'
        assert _psh(cmd).stdout == _bash(cmd).stdout
        assert _psh(cmd).stdout == 'declare -x E="temp"\n'

    def test_export_in_function_promotes_to_global(self):
        cmd = 'f(){ V=hi export V; }; f; echo "[${V-GONE}]"'
        assert _psh(cmd).stdout == _bash(cmd).stdout
        assert _psh(cmd).stdout == "[hi]\n"


# Accepted DELIBERATE DIVERGENCE (documented in docs/user_guide/
# 17_differences_from_bash.md): a prefix over ``eval``/``source``/``.`` whose body
# then runs a WHOLE-TABLE ENUMERATOR. bash makes the outer prefix visible to that
# nested enumeration; psh consistently HIDES it (the temporary environment is
# never a shell variable, so it never enters an enumeration, even one run by
# eval). This is a NEW single-prefix divergence — base MATCHED bash here, so psh
# is the one that changed — accepted because psh's consistent hiding is cleaner,
# the corner is vanishingly rare, and the common direct-command/function cases
# are a strict improvement. Pinned so the divergence stays intentional (a
# regression back to bash's leak, or to some third behavior, is caught here).
class TestNestedEvalEnumerationDivergesFromBash:
    def test_eval_export_p_hides_prefix_var_unlike_bash(self):
        cmd = 'FOO=bar eval \'export -p\' 2>&1 | grep "^declare -x FOO=" || echo NONE'
        assert _psh(cmd).stdout == "NONE\n"                    # psh: consistently hides
        assert 'declare -x FOO="bar"' in _bash(cmd).stdout     # bash: leaks into eval's enumeration
        assert _psh(cmd).stdout != _bash(cmd).stdout           # the documented difference
