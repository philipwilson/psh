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

import os
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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "harness"))
from shell_oracle import try_resolve_bash  # noqa: E402

_ORACLE = try_resolve_bash()
BASH = _ORACLE.path if _ORACLE else None


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

    def test_slots_no_dict(self):
        # slots-non-frozen (allocate-fresh-never-mutate hot-path precedent):
        # no __dict__, and a stray attribute is rejected by the slots layout.
        n = normalize_command_word('echo')
        assert not hasattr(n, '__dict__')
        with pytest.raises(AttributeError):
            n.stray = 1  # type: ignore[attr-defined]


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

    def test_no_prefix_returns_shared_empty_overlay(self, captured_shell):
        # The hot-path singleton: no per-command allocation without a prefix.
        ca = CommandAssignments(captured_shell)
        assert ca.build_overlay([]) is EMPTY_OVERLAY

    def test_posix_override_name_level(self, captured_shell):
        # bash sv_strict_posix: ANY POSIXLY_CORRECT assignment counts — the
        # value (even empty) is irrelevant, so detection is name-level.
        ca = CommandAssignments(captured_shell)
        assert ca.build_overlay(
            [('POSIXLY_CORRECT', '1', None)]).has_posix_override is True
        assert ca.build_overlay(
            [('POSIXLY_CORRECT', '', None)]).has_posix_override is True
        assert ca.build_overlay(
            [('OTHER', '1', None)]).has_posix_override is False

    def test_posix_override_through_nameref(self, captured_shell):
        # bash flips posix for `declare -n r=POSIXLY_CORRECT; r=1 cmd`.
        captured_shell.run_command('declare -n r3ref=POSIXLY_CORRECT')
        ca = CommandAssignments(captured_shell)
        assert ca.build_overlay(
            [('r3ref', '1', None)]).has_posix_override is True

    def test_posix_override_blocked_by_readonly(self, captured_shell):
        # A readonly POSIXLY_CORRECT blocks the flip (the assignment will
        # fail; bash never turns posix on — probe E1/E1b).
        captured_shell.run_command('readonly POSIXLY_CORRECT')
        ca = CommandAssignments(captured_shell)
        assert ca.build_overlay(
            [('POSIXLY_CORRECT', '1', None)]).has_posix_override is False

    def test_slots_no_dict(self):
        ov = CommandEnvOverlay()
        assert not hasattr(ov, '__dict__')
        with pytest.raises(AttributeError):
            ov.stray = 1  # type: ignore[attr-defined]


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

    def test_overlay_posix_override_resolves_posix(self, captured_shell):
        # A POSIXLY_CORRECT prefix resolves the command IN POSIX MODE even
        # though the live option is still off (resolution precedes install).
        captured_shell.run_command('eval(){ :; }')
        assert captured_shell.state.options.get('posix') is False
        normalized = normalize_command_word('eval')
        overlay = CommandEnvOverlay(
            assignment_names=('POSIXLY_CORRECT',), has_posix_override=True)
        r = resolve_command(captured_shell, _strategies(), normalized,
                            overlay, None)
        assert r.dispatch_kind is DispatchKind.SPECIAL_BUILTIN
        assert r.assignments_persist is True
        assert r.uses_temp_env_scope is False

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

    def test_resolved_command_slots(self, captured_shell):
        r = _resolve(captured_shell, 'true')
        assert isinstance(r, ResolvedCommand)
        assert not hasattr(r, '__dict__')
        with pytest.raises(AttributeError):
            r.stray = 1  # type: ignore[attr-defined]


def _norm_prefix(text: str) -> str:
    out = []
    for line in text.splitlines():
        line = line.replace(BASH, 'SH')
        line = re.sub(r'^(SH|psh): line \d+: ', 'SH: line N: ', line)
        out.append(line)
    return "\n".join(out)


@pytest.mark.skipif(BASH is None, reason="bash oracle not available")
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


@pytest.mark.skipif(BASH is None, reason="bash oracle not available")
class TestPosixlyPrefixInputModes:
    """The POSIXLY_CORRECT-prefix persistence face across INPUT MODES
    (the mode-blind-pin lesson): -c, stdin, and script file."""

    SCRIPT = 'unset X; X=kept POSIXLY_CORRECT=1 :; echo "${X-unset}"'

    def _psh(self, argv, stdin=None):
        return subprocess.run([sys.executable, '-m', 'psh', *argv],
                              input=stdin, capture_output=True, text=True)

    def _bash(self, argv, stdin=None):
        return subprocess.run([BASH, '--norc', '--noprofile', *argv],
                              input=stdin, capture_output=True, text=True)

    def test_dash_c(self):
        p, b = self._psh(['-c', self.SCRIPT]), self._bash(['-c', self.SCRIPT])
        assert p.stdout == b.stdout == 'kept\n'
        assert p.returncode == b.returncode

    def test_stdin(self):
        p = self._psh([], stdin=self.SCRIPT + '\n')
        b = self._bash([], stdin=self.SCRIPT + '\n')
        assert p.stdout == b.stdout == 'kept\n'
        assert p.returncode == b.returncode

    def test_script_file(self, tmp_path):
        f = tmp_path / 'posixly_prefix.sh'
        f.write_text(self.SCRIPT + '\n')
        p, b = self._psh([str(f)]), self._bash([str(f)])
        assert p.stdout == b.stdout == 'kept\n'
        assert p.returncode == b.returncode
