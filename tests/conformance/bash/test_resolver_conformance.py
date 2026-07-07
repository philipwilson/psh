"""Conformance tests for shared command resolution (CommandResolver campaign).

These pin the cross-consumer resolution contract that `command`, `type`,
`hash`, and the executor must agree on (bash 5.2, probed 2026-07-07). The
campaign's premise (builtins appraisal finding 5) is that resolution was
independently reimplemented, so a fact seeded through one surface
(`hash -p`) was invisible to another (`command -v`), and the executor's
PATH walk (which honours an empty PATH component as the cwd) disagreed
with `type`/`command`'s (which skipped it).

Two groups:

- ``TestResolverLocks`` — resolution facts that ALREADY match bash. They
  are the regression guard for routing the four surfaces through one
  resolver: the refactor must not change any of them.
- ``TestResolverDrift`` — the probe-verified DEFECTS. xfail(strict) until
  the resolver lands, then the marker is removed in the fixing commit.

Error-message PREFIXES differ (``psh:`` vs ``bash: line N:``), so any case
that provokes a diagnostic redirects stderr and compares ``$?``.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest

# A cwd executable, created inside the (per-shell) temp cwd so both shells
# see their own copy. Used for the empty-PATH-component cases.
MK = "printf '#!/bin/sh\\necho CWDPROG\\n' > prog; chmod +x prog; "


class TestResolverLocks(ConformanceTest):
    """Resolution facts that already match bash — regression guard."""

    # --- type: the primary introspection surface ---
    def test_type_builtin(self):
        self.assert_identical_behavior('type echo')

    def test_type_keyword(self):
        self.assert_identical_behavior('type if')

    def test_type_function(self):
        # Body rendering (`f () {` vs `f() {`) is a separate pre-existing
        # cosmetic divergence; lock the -t word, which is the resolution fact.
        self.assert_identical_behavior('f() { :; }; type -t f')

    def test_type_external(self):
        self.assert_identical_behavior('type sh')

    def test_type_not_found(self):
        self.assert_identical_behavior('type zzznope 2>/dev/null; echo rc=$?')

    def test_type_t_builtin(self):
        self.assert_identical_behavior('type -t echo')

    def test_type_t_keyword(self):
        self.assert_identical_behavior('type -t while')

    def test_type_t_external(self):
        self.assert_identical_behavior('type -t sh')

    def test_type_t_not_found(self):
        self.assert_identical_behavior('type -t zzznope; echo rc=$?')

    def test_type_a_builtin_plus_file(self):
        # `echo` is a builtin AND on PATH: -a lists the builtin then the file.
        self.assert_identical_behavior('type -a echo')

    def test_type_p_file(self):
        self.assert_identical_behavior('type -p sh')

    def test_type_p_builtin_is_empty(self):
        # -p prints nothing when type -t would not say "file".
        self.assert_identical_behavior('type -p echo; echo rc=$?')

    def test_type_P_forces_disk(self):
        self.assert_identical_behavior('type -P echo')

    def test_type_hashed_render(self):
        # A hashed command renders "is hashed (PATH)" through bare `type`.
        self.assert_identical_behavior('sh -c : ; hash -p /bin/sh sh; type sh')

    # --- command -v / -V ---
    def test_command_v_builtin(self):
        self.assert_identical_behavior('command -v echo')

    def test_command_v_keyword(self):
        self.assert_identical_behavior('command -v if')

    def test_command_v_function(self):
        self.assert_identical_behavior('f() { :; }; command -v f')

    def test_command_v_external(self):
        self.assert_identical_behavior('command -v sh')

    def test_command_v_not_found(self):
        self.assert_identical_behavior('command -v zzznope; echo rc=$?')

    def test_command_V_builtin(self):
        self.assert_identical_behavior('command -V echo')

    def test_command_bypasses_function(self):
        self.assert_identical_behavior(
            'echo() { printf FUNC; }; command echo hi')

    # --- executor / hash population parity ---
    def test_external_hashes_on_run(self):
        self.assert_identical_behavior('sh -c : ; hash')

    def test_type_a_ignores_hash(self):
        # -a re-walks PATH and does not report the hash entry.
        self.assert_identical_behavior('hash -p /bin/sh sh; type -a sh')


class TestResolverDrift(ConformanceTest):
    """Probe-verified drift the shared resolver fixes. xfail until it lands."""

    # DEFECT 1: command -p keeps builtin selection; -p only changes the
    # PATH used for the EXTERNAL search.
    @pytest.mark.xfail(strict=True, reason="resolver: command -p bypasses builtins")
    def test_command_p_runs_cd_builtin(self):
        self.assert_identical_behavior('command -p cd / && pwd')

    @pytest.mark.xfail(strict=True, reason="resolver: command -p bypasses builtins")
    def test_command_p_runs_export_builtin(self):
        self.assert_identical_behavior('command -p export FOO=1; echo ${FOO-unset}')

    @pytest.mark.xfail(strict=True, reason="resolver: command -p mutates child PATH")
    def test_command_p_child_keeps_original_path(self):
        # -p uses the default path only for the search; the child inherits the
        # shell's real PATH (psh's old env-mutation approach corrupted it).
        self.assert_identical_behavior("command -p sh -c 'echo \"$PATH\"'")

    # DEFECT 2: hash -p seeds a fact all surfaces must see.
    @pytest.mark.xfail(strict=True, reason="resolver: command -v misses hash entries")
    def test_hash_p_visible_to_command_v(self):
        self.assert_identical_behavior(
            'hash -p /tmp/custom-path customcmd; command -v customcmd; echo rc=$?')

    @pytest.mark.xfail(strict=True, reason="resolver: command -V misses hash entries")
    def test_hash_p_visible_to_command_V(self):
        self.assert_identical_behavior(
            'hash -p /tmp/custom-path customcmd; command -V customcmd')

    @pytest.mark.xfail(strict=True, reason="resolver: type -P ignores hash entries")
    def test_hash_p_visible_to_type_P(self):
        self.assert_identical_behavior(
            'hash -p /tmp/custom-path customcmd; type -P customcmd')

    # DEFECT 3: an empty PATH component denotes the cwd.
    @pytest.mark.xfail(strict=True, reason="resolver: empty PATH component skipped")
    def test_empty_path_component_type_P(self):
        self.assert_identical_behavior(MK + 'PATH=:/usr/bin type -P prog')

    @pytest.mark.xfail(strict=True, reason="resolver: empty PATH component skipped")
    def test_empty_path_component_command_v(self):
        self.assert_identical_behavior(MK + 'PATH=:/usr/bin command -v prog')

    @pytest.mark.xfail(strict=True, reason="resolver: empty PATH component skipped")
    def test_empty_path_component_type_bare(self):
        self.assert_identical_behavior(MK + 'PATH=:/usr/bin type prog')

    @pytest.mark.xfail(strict=True, reason="resolver: empty PATH component skipped")
    def test_trailing_empty_path_component(self):
        self.assert_identical_behavior(MK + 'PATH=/usr/bin: type -P prog')

    # Bonus drift exposed by the map: bash reports a slash-containing name
    # AS GIVEN; _find_in_path abspath'd it (only relative names discriminate).
    @pytest.mark.xfail(strict=True, reason="resolver: slash name abspath'd, not kept as given")
    def test_relative_slash_name_kept_as_given(self):
        self.assert_identical_behavior(MK + 'type -P ./prog')

    # DEFECT 4 (D3): env override must re-search PATH, not reuse the shell hash.
    @pytest.mark.xfail(strict=True, reason="resolver: env reuses the shell command hash (D3)")
    def test_env_override_re_searches_path(self):
        self.assert_identical_behavior(
            'ls / >/dev/null; env PATH=/nonexistent ls / >/dev/null 2>&1; echo rc=$?')
