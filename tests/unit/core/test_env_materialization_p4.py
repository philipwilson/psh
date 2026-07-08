"""Env materialization: explicit opaque base + command-env overlay (Phase 4).

Core-state appraisal H3: the execution environment is MATERIALIZED from
opaque-inherited-base + exported-variables + command-local-overlay, and every
env write goes through the one interface (``_materialize_env_name``) rather than
direct pokes. These pin:

* the opaque base is an explicit typed store holding exactly the invalid-name
  inherited entries;
* the command-env overlay wins over an exported variable's value and tears down
  cleanly (needed so ``RANDOM=5 cmd`` passes the literal, not a re-derived
  value); and
* the OLDPWD-readonly stale-env leak fixed by routing ``cd`` through the one
  interface.
"""

import os
import subprocess
import sys

from psh.core.state import ShellState


def _clean_env():
    env = dict(os.environ)
    for k in ("DISPLAY", "XAUTHORITY"):
        env.pop(k, None)
    return env


def _fresh_state(monkeypatch, extra_env=None):
    # Construct a ShellState with a controlled os.environ so the opaque base is
    # deterministic. Invalid names (bad-name) must NOT become shell variables.
    for k in list(extra_env or {}):
        monkeypatch.setenv(k, extra_env[k])
    return ShellState()


class TestOpaqueBase:
    def test_invalid_name_entry_is_opaque_not_a_variable(self, monkeypatch):
        st = _fresh_state(monkeypatch, {"bad-name": "x", "GOODNAME": "y"})
        # opaque base holds the invalid name, not the valid one.
        assert st._env_base.get("bad-name") == "x"
        assert "GOODNAME" not in st._env_base
        # the invalid name is in the live env but is NOT a shell variable.
        assert st.env.get("bad-name") == "x"
        assert st.scope_manager.get_variable_object("bad-name") is None
        # the valid name IS an exported shell variable.
        assert st.get_variable("GOODNAME") == "y"

    def test_opaque_entry_survives_a_variable_change(self, monkeypatch):
        st = _fresh_state(monkeypatch, {"bad-name": "keep"})
        # Changing an unrelated variable re-fires the observer; the opaque
        # entry must remain (the observer never touches names it doesn't own).
        st.set_variable("SOMEVAR", "1")
        st.export_variable("SOMEVAR", "1")
        assert st.env.get("bad-name") == "keep"


class TestCommandEnvOverlay:
    def test_overlay_wins_over_exported_variable_then_restores(self, monkeypatch):
        st = _fresh_state(monkeypatch)
        st.export_variable("E", "orig")
        assert st.env["E"] == "orig"
        # Overlay wins while active.
        st.apply_command_env({"E": "temp"})
        assert st.env["E"] == "temp"
        # ...and even a re-fire of the observer keeps the overlay value.
        st._sync_exported_variable("E")
        assert st.env["E"] == "temp"
        # Teardown re-derives from the (still exported) variable.
        st.restore_command_env(["E"])
        assert st.env["E"] == "orig"

    def test_overlay_for_unset_name_is_dropped_on_restore(self, monkeypatch):
        st = _fresh_state(monkeypatch)
        assert "TMPONLY" not in st.env
        st.apply_command_env({"TMPONLY": "v"})
        assert st.env["TMPONLY"] == "v"
        st.restore_command_env(["TMPONLY"])
        # No backing variable and not opaque -> absent again.
        assert "TMPONLY" not in st.env

    def test_materialize_precedence_overlay_over_base(self, monkeypatch):
        # An overlay literal wins over an opaque base entry of the same name
        # (materialization order: overlay > exported var > opaque base).
        st = _fresh_state(monkeypatch, {"weird.name": "base"})
        assert st.env["weird.name"] == "base"
        st.apply_command_env({"weird.name": "over"})
        assert st.env["weird.name"] == "over"
        st.restore_command_env(["weird.name"])
        # Falls back to the opaque base, not absent.
        assert st.env["weird.name"] == "base"


class TestPrefixLiteralPass:
    """The overlay is what makes a computed special / array pass its LITERAL to
    a child, verified end-to-end against the live shell."""

    def _run(self, script):
        return subprocess.run(
            [sys.executable, "-m", "psh", "--norc", "-c", script],
            capture_output=True, text=True, cwd="/",
        )

    def test_random_prefix_passes_literal(self):
        r = self._run('RANDOM=5 env | grep "^RANDOM="')
        assert r.stdout == "RANDOM=5\n"

    def test_array_scalar_append_prefix_passes_element0(self):
        r = self._run('a=(x y); a+=z env | grep "^a="')
        assert r.stdout == "a=xz\n"


class TestCdReadonlyOldpwdNoLeak:
    """cd routes PWD/OLDPWD through export_variable's observer only; a readonly
    OLDPWD that rejects the update must NOT leak the new value into a child's
    environment (the removed raw env poke did leak it).

    The child is a DIRECT external ``printenv`` — NOT ``$(printenv ...)``
    command substitution, whose fork re-materializes the environment and would
    mask the leak (that inert form was the verifier bounce). Leading ``cd /``
    normalizes OLDPWD to ``/`` so the assertion is cwd-independent; the pre-fix
    raw poke printed ``/tmp`` here (verified red-on-base)."""

    def test_readonly_oldpwd_keeps_old_value_in_child_env(self):
        script = ('cd /; cd /tmp; export OLDPWD; readonly OLDPWD; '
                  'cd / 2>/dev/null; printenv OLDPWD')
        env = _clean_env()
        r = subprocess.run(
            [sys.executable, "-m", "psh", "--norc", "-c", script],
            capture_output=True, text=True, cwd="/", env=env,
        )
        # OLDPWD stays `/` (set by `cd /tmp`, frozen by readonly); the blocked
        # `cd /` must not leak its attempted `/tmp` into the child's env.
        assert r.stdout == "/\n", r.stdout
