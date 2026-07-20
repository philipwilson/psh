"""Variable-truth vs child-env-projection reads (campaign R2 / CV2).

Three consumer sites read PATH/CDPATH and must consult the VARIABLE (tri-state),
not the child-env projection ``shell.env`` — otherwise a declared-unset
``local PATH``/``local CDPATH`` RESURRECTS an outer exported value that bash
treats as shadowed-unset (the #20 H13 class):

- CD's CDPATH search (`builtins/navigation.py`)
- external command PATH search (`executor/command_resolver.py` +
  `executor/strategies.py`, whose bare-name miss is now definitive)
- the 127-message discriminator empty-vs-nonempty PATH (`executor/strategies.py`)

Each command is run in BOTH shells against a SHARED temp tree (so absolute
paths in the output are identical), and compared with the shell-name
diagnostic prefix stripped (``bash: line 1: `` / ``psh: line 1: ``). Every
declared-unset-shadow row was DIVERGENT before v0.750.0 (psh resurrected the
export); the non-shadow rows matched at base and are kept-green parity.
Probed against bash 5.2 (tmp/boundary-ledgers/CV-probes/cv2_matrix.sh).
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest
from shell_oracle import resolve_bash

PSH_ROOT = Path(__file__).resolve().parents[3]

# Strip the argv0/location prefix (`psh: line 1: ` / `bash: line 1: ` /
# bash's `environment: line 1: `) so only the message BODY is compared.
_PREFIX_RE = re.compile(r'^[^:\n]*: (line \d+: )?', re.MULTILINE)


def _strip_prefix(text: str) -> str:
    return _PREFIX_RE.sub('', text)


def _run(shell_argv, cmd, cwd):
    # These rows merge the diagnostic into stdout with 2>&1, so strip the
    # argv0/location prefix on BOTH streams. The regex needs a ``: `` (colon
    # space), so ordinary output lines (AT:target, RAN:hi, rc=127) are untouched.
    r = subprocess.run(shell_argv + ['-c', cmd], capture_output=True,
                       text=True, cwd=cwd, timeout=20)
    return (_strip_prefix(r.stdout), _strip_prefix(r.stderr), r.returncode)


def _psh(cmd, cwd):
    return _run([sys.executable, '-m', 'psh'], cmd, cwd)


def _bash(cmd, cwd):
    return _run([resolve_bash().path], cmd, cwd)


def _assert_same(cmd, cwd):
    p = _psh(cmd, cwd)
    b = _bash(cmd, cwd)
    assert p == b, f"psh {p!r} != bash {b!r}\ncmd: {cmd}"


@pytest.fixture
def cvtree(tmp_path):
    """A CDPATH target dir, a real external command on a bin dir, and a cwd."""
    (tmp_path / "cdroot" / "target").mkdir(parents=True)
    binp = tmp_path / "bin"
    binp.mkdir()
    cmd = binp / "cvcmd"
    cmd.write_text("#!/bin/sh\necho RAN:$1\n")
    cmd.chmod(0o755)
    (binp / "cvsrc").write_text("echo SOURCED\n")  # a sourced script on PATH
    (tmp_path / "cwd").mkdir()
    return tmp_path


@pytest.fixture
def twotier(tmp_path):
    """PATH dirs for bash's two-tier search: a sole non-exec candidate, and a
    non-exec-early + exec-late pair (same command name)."""
    (tmp_path / "only").mkdir()
    (tmp_path / "only" / "cvsole").write_text("#!/bin/sh\necho RAN-ONLY\n")
    (tmp_path / "only" / "cvsole").chmod(0o644)          # exists, NOT executable
    (tmp_path / "early").mkdir()
    (tmp_path / "early" / "cvx").write_text("#!/bin/sh\necho RAN-EARLY\n")
    (tmp_path / "early" / "cvx").chmod(0o644)            # non-exec, earlier
    (tmp_path / "late").mkdir()
    (tmp_path / "late" / "cvx").write_text("#!/bin/sh\necho RAN-LATE\n")
    (tmp_path / "late" / "cvx").chmod(0o755)             # exec, later
    return tmp_path


class TestTwoTierPathSearch:
    """CV2 B2/B3: bash's PATH execution search is TWO-TIER — an X_OK match wins,
    a sole non-executable candidate is the LAST RESORT (execve -> EACCES ->
    rc 126), and a non-executable earlier on PATH never shadows an executable
    later. The unified CV2 fix regressed these (X_OK miss treated as definitive
    -> 127; exec's F_OK walk stopped at the first existing file). RED at the fix
    tip. Rows compare the behavioral fact (rc / which ran) with stderr
    suppressed — the "Permission denied" WORDING (bash abs-path vs psh bare name)
    is a separate carried divergence (register #24)."""

    def test_b2_sole_nonexec_plain(self, twotier):
        # bash: rc 126 (Permission denied), NOT 127 (command not found).
        _assert_same(f'PATH={twotier}/only; cvsole 2>/dev/null; echo rc=$?',
                     twotier)

    def test_b2_sole_nonexec_pipeline(self, twotier):
        _assert_same(
            f'PATH={twotier}/only; cvsole 2>/dev/null | cat; echo rc=$?',
            twotier)

    def test_b2_sole_nonexec_command_builtin(self, twotier):
        _assert_same(
            f'PATH={twotier}/only; command cvsole 2>/dev/null; echo rc=$?',
            twotier)

    def test_b2_sole_nonexec_set_plus_h(self, twotier):
        _assert_same(
            f'PATH={twotier}/only; set +h; cvsole 2>/dev/null; echo rc=$?',
            twotier)

    def test_b2_sole_nonexec_tempenv_prefix(self, twotier):
        _assert_same(
            f'PATH={twotier}/only cvsole 2>/dev/null; echo rc=$?', twotier)

    def test_b3_nonexec_early_exec_late_plain(self, twotier):
        # bash runs the executable LATER one, not the non-exec earlier.
        _assert_same(f'PATH={twotier}/early:{twotier}/late; cvx 2>/dev/null',
                     twotier)

    def test_b3_nonexec_early_exec_late_exec(self, twotier):
        _assert_same(
            f'PATH={twotier}/early:{twotier}/late; exec cvx 2>/dev/null; echo NR',
            twotier)

    def test_d1b_sole_exec_still_runs(self, twotier):
        # Kept-green: a sole EXECUTABLE candidate runs (exec replaces process).
        _assert_same(f'PATH={twotier}/late; exec cvx 2>/dev/null; echo NR',
                     twotier)


class TestCdpathVariableTruth:
    """CDPATH is read from the variable, never resurrected from the export."""

    def test_declared_unset_local_shadow_nocd(self, cvtree):
        # export CDPATH + `local CDPATH` (declared-unset) -> bash NOCD (target
        # not found); psh used to resurrect the export and cd. RED ON BASE.
        cmd = (f'export CDPATH={cvtree}/cdroot; cd {cvtree}/cwd; '
               'f(){ local CDPATH; cd target 2>&1 && echo AT:${PWD##*/}; '
               'echo rc=$?; }; f')
        _assert_same(cmd, cvtree)

    def test_export_no_shadow_cds(self, cvtree):
        cmd = (f'export CDPATH={cvtree}/cdroot; cd {cvtree}/cwd; '
               'cd target 2>&1 && echo AT:${PWD##*/}; echo rc=$?')
        _assert_same(cmd, cvtree)

    def test_local_with_value_cds(self, cvtree):
        cmd = (f'export CDPATH={cvtree}/nope; '
               f'f(){{ local CDPATH={cvtree}/cdroot; cd {cvtree}/cwd; '
               'cd target 2>&1 && echo AT:${PWD##*/}; echo rc=$?; }; f')
        _assert_same(cmd, cvtree)

    def test_global_unexported_shadow_nocd(self, cvtree):
        cmd = (f'CDPATH={cvtree}/cdroot; cd {cvtree}/cwd; '
               'f(){ local CDPATH; cd target 2>&1 && echo AT:${PWD##*/}; '
               'echo rc=$?; }; f')
        _assert_same(cmd, cvtree)


class TestPathSearchVariableTruth:
    """External command search uses the variable PATH; a bare-name miss under a
    declared-unset local is definitive (not re-searched via the child env)."""

    def test_declared_unset_local_shadow_not_found(self, cvtree):
        # export PATH + `local PATH` -> bash: command not found (127). RED ON BASE.
        cmd = (f'export PATH={cvtree}/bin; '
               'f(){ local PATH; cvcmd hi 2>&1; echo rc=$?; }; f')
        _assert_same(cmd, cvtree)

    def test_export_no_shadow_runs(self, cvtree):
        cmd = f'export PATH={cvtree}/bin; cvcmd hi 2>&1; echo rc=$?'
        _assert_same(cmd, cvtree)

    def test_local_with_value_runs(self, cvtree):
        cmd = (f'export PATH=/nope; f(){{ local PATH={cvtree}/bin; '
               'cvcmd hi 2>&1; echo rc=$?; }; f')
        _assert_same(cmd, cvtree)

    def test_local_unset_then_assign_runs(self, cvtree):
        cmd = (f'export PATH=/nope; f(){{ local PATH; PATH={cvtree}/bin; '
               'cvcmd hi 2>&1; echo rc=$?; }; f')
        _assert_same(cmd, cvtree)

    def test_global_unexported_shadow_not_found(self, cvtree):
        cmd = (f'PATH={cvtree}/bin; '
               'f(){ local PATH; cvcmd hi 2>&1; echo rc=$?; }; f')
        _assert_same(cmd, cvtree)


class TestNotFoundMessageVariableTruth:
    """The 127-message discriminator (empty vs non-empty PATH) reads the
    variable, so a `local PATH` shadow yields the empty-PATH wording."""

    def test_local_unset_path_is_empty_path_message(self, cvtree):
        # bash: 'nosuchcmd: No such file or directory' (empty PATH), not
        # 'command not found'. RED ON BASE (psh saw the resurrected PATH).
        cmd = (f'export PATH={cvtree}/bin; '
               'f(){ local PATH; nosuchcmd 2>&1; echo rc=$?; }; f')
        _assert_same(cmd, cvtree)

    def test_normal_path_is_command_not_found_message(self, cvtree):
        cmd = (f'export PATH={cvtree}/bin; '
               'f(){ nosuchcmd 2>&1; echo rc=$?; }; f')
        _assert_same(cmd, cvtree)

    def test_explicit_empty_path_is_no_such_file(self, cvtree):
        _assert_same('PATH= nosuchcmd 2>&1; echo rc=$?', cvtree)


# --- CV2 scope extension (integrator ruling): the SAME class in the three
# builtin PATH searches — hash / exec / source — converged, not carried.


class TestHashPathVariableTruth:
    """`hash NAME` searches the variable PATH (builtins/hash_builtin.py)."""

    def test_declared_unset_local_shadow_not_found(self, cvtree):
        # RED ON BASE: psh hashed via the resurrected PATH (rc 0); bash rc 1.
        cmd = (f'export PATH={cvtree}/bin; '
               'f(){ local PATH; hash cvcmd 2>&1; echo rc=$?; }; f')
        _assert_same(cmd, cvtree)

    def test_exported_global_no_shadow_hashes(self, cvtree):
        cmd = (f'export PATH={cvtree}/bin; hash cvcmd 2>&1; echo rc=$?; hash')
        _assert_same(cmd, cvtree)

    def test_global_unexported_shadow_not_found(self, cvtree):
        cmd = (f'PATH={cvtree}/bin; '
               'f(){ local PATH; hash cvcmd 2>&1; echo rc=$?; }; f')
        _assert_same(cmd, cvtree)


class TestExecPathVariableTruth:
    """`exec NAME` locates the program on the variable PATH (builtins/core.py).

    exec replaces the process on success, so the rows compare stdout + status
    with stderr suppressed (the exec diagnostic wording is compared elsewhere)."""

    def test_declared_unset_local_shadow_not_found(self, cvtree):
        # RED ON BASE: psh exec'd cvcmd via the resurrected PATH; bash 127.
        cmd = (f'export PATH={cvtree}/bin; '
               'f(){ local PATH; exec cvcmd 2>/dev/null; }; f; echo rc=$?')
        _assert_same(cmd, cvtree)

    def test_exported_global_no_shadow_execs(self, cvtree):
        cmd = f'export PATH={cvtree}/bin; exec cvcmd 2>/dev/null; echo AFTER'
        _assert_same(cmd, cvtree)

    def test_global_unexported_shadow_not_found(self, cvtree):
        cmd = (f'PATH={cvtree}/bin; '
               'f(){ local PATH; exec cvcmd 2>/dev/null; }; f; echo rc=$?')
        _assert_same(cmd, cvtree)


class TestSourcePathVariableTruth:
    """`source NAME` searches the variable PATH (builtins/source_command.py).

    source's not-found diagnostic carries a ``source:`` name that bash omits (a
    pre-existing message difference), so the rows compare the behavioral fact —
    did the file run — with stderr suppressed."""

    def test_declared_unset_local_shadow_not_found(self, cvtree):
        # RED ON BASE: psh sourced cvsrc via the resurrected PATH (SOURCED, rc0).
        cmd = (f'export PATH={cvtree}/bin; '
               'f(){ local PATH; source cvsrc 2>/dev/null; echo rc=$?; }; f')
        _assert_same(cmd, cvtree)

    def test_exported_global_no_shadow_sources(self, cvtree):
        cmd = (f'export PATH={cvtree}/bin; source cvsrc 2>/dev/null; echo rc=$?')
        _assert_same(cmd, cvtree)

    def test_global_unexported_shadow_not_found(self, cvtree):
        cmd = (f'PATH={cvtree}/bin; '
               'f(){ local PATH; source cvsrc 2>/dev/null; echo rc=$?; }; f')
        _assert_same(cmd, cvtree)
