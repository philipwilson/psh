"""Unit coverage for the R3 typed command-resolution triad (#20 H10).

Pins the invariants of the three campaign contract types and the one
mode-aware ``resolve_command`` chokepoint in
``psh/executor/command_resolution.py``:

- ``NormalizedCommandName`` — post-quote-removal spelling + bypass provenance.
- ``CommandEnvOverlay`` — immutable effective-environment view; PATH projection.
- ``ResolvedCommand`` — the single dispatch answer, mode-aware.

plus the empty/unset-PATH command-not-found MESSAGE alignment (a subprocess
row against live bash, prefix-normalized).
"""

import dataclasses
import re
import subprocess
import sys

import pytest

from psh.executor.command_assignments import CommandAssignments
from psh.executor.command_resolution import (
    EMPTY_OVERLAY,
    CommandEnvOverlay,
    DispatchKind,
    NormalizedCommandName,
    ResolvedCommand,
    normalize_command_word,
    resolve_command,
)
from psh.executor.strategies import (
    BuiltinExecutionStrategy,
    ExternalExecutionStrategy,
    FunctionExecutionStrategy,
    SpecialBuiltinExecutionStrategy,
)

BASH = "/opt/homebrew/bin/bash"


def _strategies():
    """The executor's default-mode strategy order (see CommandExecutor)."""
    return (
        FunctionExecutionStrategy(),
        SpecialBuiltinExecutionStrategy(),
        BuiltinExecutionStrategy(),
        ExternalExecutionStrategy(),
    )


def _resolve(shell, name, *, backslash=False):
    normalized = normalize_command_word(name, backslash_bypass=backslash)
    return resolve_command(shell, _strategies(), normalized,
                           EMPTY_OVERLAY, None)


class TestNormalizedCommandName:
    def test_plain_name(self):
        n = normalize_command_word('echo')
        assert n == NormalizedCommandName('echo', False, False)
        assert not n.backslash_bypass and not n.has_slash

    def test_backslash_provenance_recorded(self):
        n = normalize_command_word('export', backslash_bypass=True)
        assert n.backslash_bypass is True
        assert n.text == 'export'

    def test_slash_detected(self):
        assert normalize_command_word('/bin/echo').has_slash is True
        assert normalize_command_word('a/b').has_slash is True
        assert normalize_command_word('ab').has_slash is False

    def test_frozen(self):
        n = normalize_command_word('echo')
        with pytest.raises(dataclasses.FrozenInstanceError):
            n.text = 'other'  # type: ignore[misc]


class TestCommandEnvOverlay:
    def test_empty_overlay_defaults(self):
        assert EMPTY_OVERLAY.assignment_names == ()
        assert EMPTY_OVERLAY.has_path_override is False

    def test_build_records_names_in_order(self, captured_shell):
        ca = CommandAssignments(captured_shell)
        raw = [('A', '1', None), ('B', '$A', None)]
        overlay = ca.build_overlay(raw)
        assert overlay.assignment_names == ('A', 'B')
        assert overlay.has_path_override is False

    def test_build_detects_path_override(self, captured_shell):
        ca = CommandAssignments(captured_shell)
        overlay = ca.build_overlay([('PATH', '/only', None)])
        assert overlay.has_path_override is True

    def test_effective_path_reads_live_env(self, captured_shell):
        captured_shell.state.env['PATH'] = '/tmp/xyz-r3'
        assert CommandEnvOverlay().effective_path(captured_shell) == '/tmp/xyz-r3'

    def test_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            CommandEnvOverlay().has_path_override = True  # type: ignore[misc]


class TestResolveCommandModeAware:
    def test_external_catch_all_never_none(self, captured_shell):
        r = _resolve(captured_shell, 'definitely-not-a-command-xyz')
        assert r is not None
        assert r.dispatch_kind is DispatchKind.EXTERNAL
        assert r.assignments_persist is False
        assert r.uses_temp_env_scope is False
        assert r.is_exec_special is False

    def test_regular_builtin(self, captured_shell):
        r = _resolve(captured_shell, 'true')
        assert r.dispatch_kind is DispatchKind.BUILTIN
        assert r.is_posix_special is False

    def test_special_builtin_default_mode_no_persist(self, captured_shell):
        r = _resolve(captured_shell, ':')
        assert r.dispatch_kind is DispatchKind.SPECIAL_BUILTIN
        assert r.is_posix_special is True
        assert r.assignments_persist is False  # not posix

    def test_special_builtin_posix_persists(self, captured_shell):
        captured_shell.state.options['posix'] = True
        try:
            r = _resolve(captured_shell, ':')
            assert r.dispatch_kind is DispatchKind.SPECIAL_BUILTIN
            assert r.assignments_persist is True
        finally:
            captured_shell.state.options['posix'] = False

    def test_function_default_mode_wins_over_special(self, captured_shell):
        captured_shell.run_command('eval(){ :; }')
        r = _resolve(captured_shell, 'eval')
        assert r.dispatch_kind is DispatchKind.FUNCTION
        assert r.uses_temp_env_scope is True
        assert r.assignments_persist is False
        assert r.is_exec_special is False

    def test_h10_posix_special_shadows_function(self, captured_shell):
        # The H10 core: in POSIX mode the special builtin wins over a
        # same-named function, so resolution is SPECIAL (persist), not FUNCTION.
        captured_shell.run_command('eval(){ :; }')
        captured_shell.state.options['posix'] = True
        try:
            r = _resolve(captured_shell, 'eval')
            assert r.dispatch_kind is DispatchKind.SPECIAL_BUILTIN
            assert r.uses_temp_env_scope is False
            assert r.assignments_persist is True
        finally:
            captured_shell.state.options['posix'] = False

    def test_exec_special_default_mode(self, captured_shell):
        r = _resolve(captured_shell, 'exec')
        assert r.is_exec_special is True

    def test_exec_shadowed_by_function_default_mode(self, captured_shell):
        captured_shell.run_command('exec(){ echo fn; }')
        r = _resolve(captured_shell, 'exec')
        assert r.dispatch_kind is DispatchKind.FUNCTION
        assert r.is_exec_special is False

    def test_exec_special_wins_posix_over_function(self, captured_shell):
        captured_shell.run_command('exec(){ echo fn; }')
        captured_shell.state.options['posix'] = True
        try:
            r = _resolve(captured_shell, 'exec')
            assert r.dispatch_kind is DispatchKind.SPECIAL_BUILTIN
            assert r.is_exec_special is True
        finally:
            captured_shell.state.options['posix'] = False

    def test_resolved_command_frozen(self, captured_shell):
        r = _resolve(captured_shell, 'true')
        assert isinstance(r, ResolvedCommand)
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.assignments_persist = True  # type: ignore[misc]


def _norm_prefix(text: str) -> str:
    out = []
    for line in text.splitlines():
        line = line.replace(BASH, 'SH')
        line = re.sub(r'^(SH|psh): line \d+: ', 'SH: line N: ', line)
        out.append(line)
    return "\n".join(out)


@pytest.mark.skipif(not __import__('os').path.exists(BASH),
                    reason="PATH bash 5.2 not present")
class TestEmptyPathNotFoundMessage:
    """bash reports a bare-name miss under an EMPTY or UNSET PATH as
    'No such file or directory' (rc 127), not 'command not found'; a
    non-empty PATH miss stays 'command not found'. Prefix-normalized so only
    the message BODY + rc are compared (the psh:/argv0 prefix differs)."""

    def _both(self, script):
        p = subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                           capture_output=True, text=True)
        b = subprocess.run([BASH, '--norc', '--noprofile', '-c', script],
                           capture_output=True, text=True)
        return p, b

    def test_empty_path_says_no_such_file(self):
        p, b = self._both('PATH= zzznope 2>&1; echo rc=$?')
        assert 'No such file or directory' in p.stdout
        assert _norm_prefix(p.stdout) == _norm_prefix(b.stdout)

    def test_unset_path_says_no_such_file(self):
        p, b = self._both('unset PATH; zzznope 2>&1; echo rc=$?')
        assert 'No such file or directory' in p.stdout
        assert _norm_prefix(p.stdout) == _norm_prefix(b.stdout)

    def test_nonempty_path_miss_still_command_not_found(self):
        p, b = self._both('PATH=/nope-xyz zzznope 2>&1; echo rc=$?')
        assert 'command not found' in p.stdout
        assert _norm_prefix(p.stdout) == _norm_prefix(b.stdout)

    def test_colon_path_is_nonempty_command_not_found(self):
        # PATH=: is a non-empty search (cwd only) that MISSES -> not found.
        p, b = self._both('PATH=: zzznope 2>&1; echo rc=$?')
        assert 'command not found' in p.stdout
        assert _norm_prefix(p.stdout) == _norm_prefix(b.stdout)
