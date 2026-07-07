"""Unit tests for the computed special-parameter registry (appraisal H1).

Two layers:

- the typed ``SpecialParameterState`` state machine (is_computed / has_lifecycle
  / assign / deactivate / attribute overlay / monotonic SECONDS / clone); and
- the end-to-end shell behaviour these produce, verified against bash 5.2:
  readonly PERSISTS and is enforced (a later assignment is fatal, like bash),
  ``export`` materialises a snapshot into the environment, ``unset`` deactivates
  EVERY dynamic special (not just SECONDS/RANDOM), and ``declare -p NAME`` lists
  a computed special.

Behavioural values here were pinned by differential probes against
/opt/homebrew/bin/bash 5.2.26; the parallel bash comparison lives in the
``corestate3_special_*`` golden cases.
"""

import subprocess
import sys

import pytest

from psh.core.special_registry import (
    SPECIAL_REGISTRY,
    AssignPolicy,
    SpecialContext,
    SpecialParameterState,
)
from psh.core.variables import VarAttributes


def run_psh(cmd, env=None):
    return subprocess.run([sys.executable, '-m', 'psh', '--norc', '-c', cmd],
                          capture_output=True, text=True, env=env)


# --------------------------------------------------------------------------- #
# Typed state machine
# --------------------------------------------------------------------------- #

class TestSpecialParameterStateClassification:
    def test_registry_covers_the_dynamic_and_shell_view_specials(self):
        assert {n for n, s in SPECIAL_REGISTRY.items() if s.lifecycle} == {
            'SECONDS', 'RANDOM', 'BASHPID', 'SRANDOM',
            'EPOCHSECONDS', 'EPOCHREALTIME', 'LINENO',
        }
        assert {n for n, s in SPECIAL_REGISTRY.items() if not s.lifecycle} == {
            'PIPESTATUS', 'BASH_COMMAND', 'FUNCNAME',
        }

    def test_is_computed_and_has_lifecycle(self):
        st = SpecialParameterState()
        assert st.is_computed('RANDOM') and st.has_lifecycle('RANDOM')
        # Shell-view special: computed on read but NO lifecycle interception.
        assert st.is_computed('FUNCNAME') and not st.has_lifecycle('FUNCNAME')
        # Not a special at all.
        assert not st.is_computed('PATH') and not st.has_lifecycle('PATH')

    def test_deactivate_stops_computing_and_drops_state(self):
        st = SpecialParameterState()
        st.assign('SECONDS', '500')
        assert st.seconds_base == 500
        st.deactivate('SECONDS')
        assert not st.is_computed('SECONDS')
        assert not st.has_lifecycle('SECONDS')
        assert st.seconds_base is None

    def test_seed_vs_ignore_assign_policy(self):
        assert SPECIAL_REGISTRY['SECONDS'].assign is AssignPolicy.SEED
        assert SPECIAL_REGISTRY['RANDOM'].assign is AssignPolicy.SEED
        assert SPECIAL_REGISTRY['BASHPID'].assign is AssignPolicy.IGNORE
        assert SPECIAL_REGISTRY['SRANDOM'].assign is AssignPolicy.IGNORE
        st = SpecialParameterState()
        st.assign('BASHPID', '7')  # IGNORE: no recorded state
        assert st.seconds_base is None and st.random_seed is None

    def test_read_side_effects_flag(self):
        st = SpecialParameterState()
        assert st.read_has_side_effects('RANDOM')
        assert st.read_has_side_effects('SRANDOM')
        assert not st.read_has_side_effects('SECONDS')
        assert not st.read_has_side_effects('LINENO')


class TestSpecialParameterStateAttributes:
    def test_default_attributes(self):
        st = SpecialParameterState()
        assert st.attributes_for('RANDOM') & VarAttributes.INTEGER
        assert st.attributes_for('BASHPID') & VarAttributes.INTEGER
        # EPOCH* / LINENO are plain (bash: declare -- ...).
        assert not (st.attributes_for('EPOCHSECONDS') & VarAttributes.INTEGER)
        assert not (st.attributes_for('LINENO') & VarAttributes.INTEGER)

    def test_overlay_add_and_remove(self):
        st = SpecialParameterState()
        st.add_attributes('RANDOM', VarAttributes.READONLY | VarAttributes.EXPORT)
        attrs = st.attributes_for('RANDOM')
        assert attrs & VarAttributes.READONLY and attrs & VarAttributes.EXPORT
        # INTEGER default survives alongside the overlay.
        assert attrs & VarAttributes.INTEGER
        st.remove_attributes('RANDOM', VarAttributes.EXPORT)
        assert not (st.attributes_for('RANDOM') & VarAttributes.EXPORT)
        assert st.attributes_for('RANDOM') & VarAttributes.READONLY

    def test_deactivate_clears_overlay(self):
        st = SpecialParameterState()
        st.add_attributes('RANDOM', VarAttributes.READONLY)
        assert st.attributes_for('RANDOM') & VarAttributes.READONLY
        st.deactivate('RANDOM')
        assert not st.has_lifecycle('RANDOM')
        # Overlay cleared — no stale readonly lingers on the deactivated name.
        assert not (st.attributes_for('RANDOM') & VarAttributes.READONLY)


class TestSecondsMonotonic:
    def test_seconds_uses_monotonic_not_wall_clock(self, monkeypatch):
        """SECONDS elapsed must ride the MONOTONIC clock: a wall-clock step
        (time.time jumping) must not move SECONDS."""
        import psh.core.special_registry as reg
        fake_mono = {'t': 1000.0}
        monkeypatch.setattr(reg.time, 'monotonic', lambda: fake_mono['t'])
        # A wall-clock leap must be irrelevant to SECONDS.
        monkeypatch.setattr(reg.time, 'time', lambda: 9_999_999_999.0)

        st = SpecialParameterState()  # shell_start_time = 1000.0 (monotonic)
        ctx = SpecialContext(st, None)
        assert reg._compute_seconds(ctx) == '0'
        fake_mono['t'] = 1042.7  # 42.7 monotonic seconds later
        assert reg._compute_seconds(ctx) == '42'

    def test_seconds_assignment_baseline_on_monotonic(self, monkeypatch):
        import psh.core.special_registry as reg
        fake_mono = {'t': 500.0}
        monkeypatch.setattr(reg.time, 'monotonic', lambda: fake_mono['t'])
        st = SpecialParameterState()
        st.assign('SECONDS', '100')
        ctx = SpecialContext(st, None)
        assert reg._compute_seconds(ctx) == '100'
        fake_mono['t'] = 507.0  # +7s
        assert reg._compute_seconds(ctx) == '107'


class TestCloneIndependence:
    def test_clone_inherits_baseline_and_deactivation_but_not_random_seed(self):
        st = SpecialParameterState()
        st.assign('SECONDS', '500')
        st.assign('RANDOM', '42')
        st.deactivate('EPOCHSECONDS')
        st.add_attributes('LINENO', VarAttributes.READONLY)

        child = st.clone()
        assert child.seconds_base == 500          # SECONDS baseline inherited
        assert child.random_seed is None          # RANDOM reseeded (not copied)
        assert not child.is_computed('EPOCHSECONDS')  # deactivation inherited
        assert child.attributes_for('LINENO') & VarAttributes.READONLY

    def test_clone_is_graph_independent(self):
        st = SpecialParameterState()
        st.add_attributes('RANDOM', VarAttributes.READONLY)
        st.deactivate('LINENO')
        child = st.clone()
        # Mutating the child must not reach back into the parent.
        child.add_attributes('SECONDS', VarAttributes.EXPORT)
        child.deactivate('BASHPID')
        assert not (st.attributes_for('SECONDS') & VarAttributes.EXPORT)
        assert st.is_computed('BASHPID')
        # ...and vice versa.
        st.deactivate('SRANDOM')
        assert child.is_computed('SRANDOM')


# --------------------------------------------------------------------------- #
# End-to-end shell behaviour (pinned to bash 5.2)
# --------------------------------------------------------------------------- #

class TestReadonlyEnforced:
    @pytest.mark.parametrize('name', ['RANDOM', 'SECONDS', 'BASHPID',
                                      'EPOCHSECONDS', 'LINENO'])
    def test_readonly_special_blocks_assignment(self, name):
        # bash: readonly special + later assignment is a fatal error in a
        # non-interactive shell — the shell exits and the trailing echo never
        # runs. (Before the registry, RANDOM/SECONDS/BASHPID silently accepted
        # the assignment.)
        r = run_psh(f'readonly {name}; {name}=999; echo AFTER')
        assert 'AFTER' not in r.stdout
        assert r.returncode == 1
        assert 'readonly variable' in r.stderr

    def test_readonly_special_still_reads(self):
        r = run_psh('readonly RANDOM; r=$RANDOM; '
                    '[ "$r" -ge 0 ] && [ "$r" -le 32767 ] && echo inrange')
        assert r.stdout == 'inrange\n'

    def test_readonly_special_cannot_be_unset(self):
        # bash: unset of a readonly variable is a NON-fatal builtin error —
        # it reports "cannot unset: readonly variable" but the shell continues.
        r = run_psh('readonly RANDOM; unset RANDOM; echo AFTER')
        assert r.stdout == 'AFTER\n'
        assert r.returncode == 0
        assert 'readonly' in r.stderr


class TestExportMaterialization:
    @pytest.mark.parametrize('name', ['RANDOM', 'SECONDS', 'EPOCHSECONDS',
                                      'EPOCHREALTIME'])
    def test_export_makes_env_value_visible_to_child(self, name):
        # bash: `export RANDOM` snapshots the current value into the
        # environment; a child process sees it.
        r = run_psh(f'export {name}; printenv {name} >/dev/null; echo "rc=$?"')
        assert r.stdout == 'rc=0\n'

    def test_export_with_value_seeds_and_materializes(self):
        # export SECONDS=100 seeds the baseline AND snapshots 100 into env.
        r = run_psh('export SECONDS=100; '
                    'v=$(printenv SECONDS); [ "$v" = 100 ] && echo ok')
        assert r.stdout == 'ok\n'

    def test_export_n_removes_env_entry(self):
        r = run_psh('export RANDOM; export -n RANDOM; '
                    'printenv RANDOM >/dev/null; echo "rc=$?"')
        assert r.stdout == 'rc=1\n'


class TestUnsetDeactivation:
    @pytest.mark.parametrize('name', ['EPOCHSECONDS', 'EPOCHREALTIME', 'LINENO',
                                      'RANDOM', 'SECONDS', 'BASHPID'])
    def test_unset_then_assign_stores_literal(self, name):
        # bash: after `unset EPOCHSECONDS`, the name is an ordinary variable —
        # a later assignment stores the literal string (no longer computed).
        r = run_psh(f'unset {name}; {name}=hello; echo "[${name}]"')
        assert r.stdout == '[hello]\n'


class TestDeclarePListsComputedSpecial:
    def test_declare_p_random_shows_integer_attribute(self):
        r = run_psh("declare -p RANDOM | sed 's/=.*//'")
        assert r.stdout == 'declare -i RANDOM\n'

    def test_declare_p_epochseconds_is_plain(self):
        r = run_psh("declare -p EPOCHSECONDS | sed 's/=.*//'")
        assert r.stdout == 'declare -- EPOCHSECONDS\n'

    def test_declare_p_readonly_export_random(self):
        r = run_psh("readonly RANDOM; export RANDOM; declare -p RANDOM | sed 's/=.*//'")
        assert r.stdout == 'declare -irx RANDOM\n'


class TestShellViewSpecialsUnchanged:
    """The shell-view specials (no lifecycle) keep their ordinary-path
    behaviour — regression pins for the split."""

    def test_pipestatus_readonly_still_enforced(self):
        r = run_psh('readonly PIPESTATUS; PIPESTATUS=x; echo AFTER')
        assert 'AFTER' not in r.stdout
        assert r.returncode == 1

    def test_funcname_empty_outside_function(self):
        r = run_psh('echo "[${FUNCNAME[@]}]"')
        assert r.stdout == '[]\n'

    def test_funcname_stack_in_nested_functions(self):
        r = run_psh('f() { g; }; g() { echo "${FUNCNAME[0]} ${FUNCNAME[1]}"; }; f')
        assert r.stdout == 'g f\n'
