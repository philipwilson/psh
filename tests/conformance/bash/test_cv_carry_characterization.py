"""Both-sides characterization pins for closing-verification carry register
(dev-cv, v0.750.0). These are DOCUMENTED DIVERGENCES — psh's behavior is pinned
alongside bash's so a future accidental change to EITHER is caught. They are
carried (carry register #18-24 in docs/reviews/boundary_campaign_close_2026-07),
not fixed, per the closing-verification dispositions.
"""
import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

BASH = resolve_bash().path
PSH = [sys.executable, "-m", "psh"]


def _run(argv, cmd, cwd=None):
    return subprocess.run(argv + ["-c", cmd], capture_output=True, text=True,
                          timeout=20, cwd=cwd)


class TestPosixSpecialBuiltinRedirectFatality:
    """Carry #18 (R3): in POSIX mode a redirection error on a POSIX SPECIAL
    builtin is FATAL in bash (the shell exits, the rest of the line never runs);
    psh reports the error and CONTINUES. Both shells agree in default (non-posix)
    mode (continue). Divergence probed vs bash 5.2."""

    _CMD = "{mode}: > /no/such/dir/f 2>/dev/null; echo AFTER=$?"

    def test_posix_mode_bash_exits_psh_continues(self):
        cmd = "set -o posix; : > /no/such/dir/f 2>/dev/null; echo AFTER=$?"
        bash = _run([BASH], cmd)
        psh = _run(PSH, cmd)
        # bash: the special-builtin redirect error aborts — AFTER never prints.
        assert "AFTER=" not in bash.stdout, bash.stdout
        assert bash.returncode != 0
        # psh: continues past the error (documented divergence).
        assert psh.stdout.strip() == "AFTER=1", psh.stdout

    def test_default_mode_both_continue(self):
        cmd = ": > /no/such/dir/f 2>/dev/null; echo AFTER=$?"
        bash = _run([BASH], cmd)
        psh = _run(PSH, cmd)
        assert bash.stdout.strip() == "AFTER=1"
        assert psh.stdout.strip() == "AFTER=1"


class TestAnsiCHighEscapeByteModel:
    """Carry #19: an ANSI-C `$'\\xNN'` escape with NN >= 0x80 — bash emits the
    RAW byte 0xNN; psh emits the UTF-8 ENCODING of codepoint U+00NN. Probed vs
    bash 5.2 (a documented pre-existing byte-model divergence)."""

    def test_xff_bash_raw_byte_psh_utf8(self):
        cmd = r"printf '%s' $'\xff'"
        bash = subprocess.run([BASH, "-c", cmd], capture_output=True, timeout=20)
        psh = subprocess.run(PSH + ["-c", cmd], capture_output=True, timeout=20)
        assert bash.stdout == b"\xff", bash.stdout            # raw byte
        assert psh.stdout == b"\xc3\xbf", psh.stdout          # UTF-8 of U+00FF

    def test_x80_boundary(self):
        cmd = r"printf '%s' $'\x80'"
        bash = subprocess.run([BASH, "-c", cmd], capture_output=True, timeout=20)
        psh = subprocess.run(PSH + ["-c", cmd], capture_output=True, timeout=20)
        assert bash.stdout == b"\x80"
        assert psh.stdout == b"\xc2\x80"                      # UTF-8 of U+0080


@pytest.fixture
def nonexec_on_path(tmp_path):
    """A sole non-executable (644) regular file on a bin dir."""
    binp = tmp_path / "bin"
    binp.mkdir()
    f = binp / "cvsole"
    f.write_text("#!/bin/sh\necho X\n")
    f.chmod(0o644)
    return tmp_path


class TestTwoTierIntrospectionResidual:
    """Carry #24 (R3/CV2 N4): bash's `type`/`command -v`/`type -P` REPORT a
    non-executable file found on PATH (rc 0, two-tier existence), while psh's
    introspection uses the X_OK search and says "not found" (rc 1). Pre-existing
    (base AND branch); converging it would need a two-tier flag threaded through
    the resolver's candidate model WITHOUT loosening the X_OK-only exec/hash
    search — deferred. `type -a` (X_OK only) already MATCHES bash. Probed vs
    bash 5.2."""

    def test_type_reports_nonexec_in_bash(self, nonexec_on_path):
        cmd = f'PATH={nonexec_on_path}/bin; type cvsole >/dev/null 2>&1; echo $?'
        assert _run([BASH], cmd).stdout.strip() == "0"       # bash: reports it
        assert _run(PSH, cmd).stdout.strip() == "1"          # psh: not found

    def test_command_v_reports_nonexec_in_bash(self, nonexec_on_path):
        cmd = (f'PATH={nonexec_on_path}/bin; '
               'command -v cvsole >/dev/null 2>&1; echo $?')
        assert _run([BASH], cmd).stdout.strip() == "0"
        assert _run(PSH, cmd).stdout.strip() == "1"

    def test_type_a_matches_bash_not_found(self, nonexec_on_path):
        # type -a is X_OK-only in BOTH shells (kept-green control).
        cmd = f'PATH={nonexec_on_path}/bin; type -a cvsole >/dev/null 2>&1; echo $?'
        assert _run([BASH], cmd).stdout.strip() == "1"
        assert _run(PSH, cmd).stdout.strip() == "1"


class TestPermissionDeniedWording:
    """Carry #24 (CV2 B2 wording): the two-tier last-resort candidate reports
    rc 126 in BOTH shells, but bash names the ABSOLUTE PATH while psh names the
    BARE command word — a pre-existing message-wording difference (the exec/
    external diagnostics name the raw word, not the resolved path). rc + the
    behavioral fact (not run) are pinned by the two-tier conformance rows; only
    the wording differs. Probed vs bash 5.2."""

    def test_permission_denied_rc126_both_word_differs(self, nonexec_on_path):
        cmd = f'PATH={nonexec_on_path}/bin; cvsole; echo rc=$?'
        b = _run([BASH], cmd)
        p = _run(PSH, cmd)
        assert "rc=126" in b.stdout and "rc=126" in p.stdout      # SAME rc
        assert "Permission denied" in b.stderr and "Permission denied" in p.stderr
        # bash names the resolved absolute path; psh names the bare word.
        assert "/bin/cvsole: Permission denied" in b.stderr
        assert "cvsole: Permission denied" in p.stderr
        assert f"{nonexec_on_path}/bin/cvsole" not in p.stderr    # psh: bare word


class TestStickyNonExecHash:
    """Carry #27 (CV2 R3): bash IMPLICITLY HASHES the non-executable last-resort
    (126) candidate at exec time — `hash` lists it afterward, and it can beat a
    later executable within the (unchanged) PATH — whereas psh does NOT insert a
    126 candidate into the command hash. A DIRECTORY lose-on is hashed by neither
    (control). Implementing implicit insertion would risk the resolve-once/hash
    machinery at campaign close (integrator ruling: CARRY). This corrects
    commit ab2fecba's design note "bash hashes only executables" — bash also
    hashes the non-exec lose-on. Probed vs bash 5.2."""

    @pytest.fixture
    def hashtree(self, tmp_path):
        b = tmp_path / "bin"
        b.mkdir()
        (b / "cvh").write_text("#!/bin/sh\n")
        (b / "cvh").chmod(0o644)                     # sole NON-EXECUTABLE
        (tmp_path / "dbin").mkdir()
        (tmp_path / "dbin" / "cvd").mkdir()          # sole DIRECTORY candidate
        return tmp_path

    def test_bash_hashes_nonexec_lose_on_psh_does_not(self, hashtree):
        # After a 126 non-exec run, bash's hash lists cvh; psh's is empty.
        cmd = f'PATH={hashtree}/bin; cvh 2>/dev/null; hash 2>&1'
        assert "cvh" in _run([BASH], cmd).stdout             # bash hashed it
        psh_out = _run(PSH, cmd).stdout
        assert "cvh" not in psh_out                          # psh did NOT
        assert "empty" in psh_out.lower()

    def test_directory_lose_on_hashed_by_neither(self, hashtree):
        # Control: a directory candidate (127) is hashed by NEITHER shell.
        cmd = f'PATH={hashtree}/dbin; cvd 2>/dev/null; hash 2>&1'
        assert "cvd" not in _run([BASH], cmd).stdout
        assert "cvd" not in _run(PSH, cmd).stdout
