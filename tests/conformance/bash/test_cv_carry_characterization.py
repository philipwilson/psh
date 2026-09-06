"""Both-sides characterization pins for closing-verification carry register
(dev-cv, v0.750.0). These are DOCUMENTED DIVERGENCES — psh's behavior is pinned
alongside bash's so a future accidental change to EITHER is caught. They are
carried (carry register #18-24 in docs/reviews/boundary_campaign_close_2026-07),
not fixed, per the closing-verification dispositions.
"""
import sys

import pytest
from shell_oracle import is_comparable, resolve_bash, run_bash, run_psh

BASH = resolve_bash().path
PSH = [sys.executable, "-m", "psh"]


def _run(argv, cmd, cwd=None):
    if argv[0] == sys.executable:
        r = run_psh(["-c", cmd], cwd=cwd, timeout=20)
    else:
        r = run_bash(["-c", cmd], cwd=cwd, timeout=20)
    assert is_comparable(r), r
    return r


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
        bash = run_bash(["-c", cmd], timeout=20)
        assert is_comparable(bash), bash
        psh = run_psh(["-c", cmd], timeout=20)
        assert is_comparable(psh), psh
        assert bash.stdout.encode("utf-8", "surrogateescape") == b"\xff", bash.stdout
        assert psh.stdout.encode("utf-8", "surrogateescape") == b"\xc3\xbf", psh.stdout

    def test_x80_boundary(self):
        cmd = r"printf '%s' $'\x80'"
        bash = run_bash(["-c", cmd], timeout=20)
        assert is_comparable(bash), bash
        psh = run_psh(["-c", cmd], timeout=20)
        assert is_comparable(psh), psh
        assert bash.stdout.encode("utf-8", "surrogateescape") == b"\x80"
        assert psh.stdout.encode("utf-8", "surrogateescape") == b"\xc2\x80"


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


class TestDoubleBracketArithProvenance:
    """Carry #31 (CV1 H2, integrator-ruled): a `[[` UNQUOTED numeric operand
    carries PER-CHARACTER quote provenance into the arithmetic in bash — a `\\"`
    inside an associative subscript is a protected `"` that the key keeps
    (`[[ h[\\"q\\"] -eq 7 ]]` keys `"q"`), while psh's `[[` path quote-removes the
    operand string before arith, keying `q`. `let` (and psh) key `q` in BOTH, so
    `[[` is NOT let-like for provenance (the R1 model was too coarse for the
    UNQUOTED spelling). Base-identical (pre-existing, NOT a regression); a correct
    fix would thread W1-style protection runs through the entire string-based
    arithmetic input contract (tokenizer/parser/evaluator/subscript keying, ~10
    caller families) — disproportionate at campaign close. Deliberate, pinned.
    bash 5.2-verified. Quoted spellings, real-dquote, and `[[ -v` all MATCH.

    COMPOSED CONSEQUENCE (ruled WITHIN #31, round-4): because CV1 fixed the
    `(( ))` WRITE-side provenance while `[[` READ-side is carried, a quote-bearing
    key WRITTEN via `(( h[$k]=v ))` (keys `"q"`, bash-correct) and READ via
    `[[ h[$k] -eq v ]]` (keys `q`) now key INCONSISTENTLY within psh — the read
    misses (rc 1) where bash matches (rc 0). Base was wrong-but-CONSISTENT (the
    write ALSO keyed `q` pre-CV1, so read/write agreed and accidentally printed
    bash's match=yes). This is the transitional inconsistency inherent to a
    PARTIAL fix; the full fix is the same registered contract reshape."""

    def test_unquoted_escaped_dquote_subscript_keys_quoted(self):
        # h[q]=7: bash keys "q" (unset) -> false (rc 1); psh keys q -> 7 (rc 0).
        cmd = r'declare -A h; h[q]=7; [[ h[\"q\"] -eq 7 ]]; echo $?'
        assert _run([BASH], cmd).stdout.strip() == "1"
        assert _run(PSH, cmd).stdout.strip() == "0"

    def test_unquoted_escaped_dquote_hits_quoted_key(self):
        # The quoted key "q" is set with single quotes; the [[ operand keys it in
        # bash (true, rc 0) but psh keys q (unset, rc 1).
        cmd = r"""declare -A h; h['"q"']=7; [[ h[\"q\"] -eq 7 ]]; echo $?"""
        assert _run([BASH], cmd).stdout.strip() == "0"
        assert _run(PSH, cmd).stdout.strip() == "1"

    def test_let_keys_q_in_both_control(self):
        # let is let-like in BOTH (keys q) — proves [[ diverges specifically.
        # UNQUOTED: the shell processes \" -> " before let, then arith removes it.
        cmd = r'declare -A h; h[q]=7; let r=h[\"q\"]; echo $r'
        assert _run([BASH], cmd).stdout.strip() == "7"
        assert _run(PSH, cmd).stdout.strip() == "7"

    def test_single_quoted_and_real_dquote_match(self):
        # Controls that already MATCH (kept green): single-quoted + real-dquote.
        for cmd in (r"""declare -A h; h[q]=7; [[ 'h[\"q\"]' -eq 7 ]]; echo $?""",
                    r'declare -A h; h[q]=7; [[ h["q"] -eq 7 ]]; echo $?'):
            assert _run([BASH], cmd).stdout.strip() == _run(PSH, cmd).stdout.strip()

    def test_composed_arith_write_double_bracket_read_inconsistent(self):
        # COMPOSED (ruled within #31): (( ))-write keys "q" (CV1-fixed) but
        # [[-read keys q -> psh read MISSES (rc 1); bash keys "q" both -> rc 0.
        # Both arrays end up holding the "q" key (the write side agrees).
        cmd = (r"""declare -A h; k='"q"'; (( h[$k]=7 )); """
               r"""[[ h[$k] -eq 7 ]]; echo "read-eq=$?"; """
               r"""for K in "${!h[@]}"; do echo "key=[$K]"; done""")
        assert _run([BASH], cmd).stdout.strip() == 'read-eq=0\nkey=["q"]'
        assert _run(PSH, cmd).stdout.strip() == 'read-eq=1\nkey=["q"]'


class TestExecutableSpecialFileEarlier:
    """Carry #30 (CV2 R3, DESIRABLE deviation): an EXECUTABLE-bit special file
    (FIFO or SOCKET) earlier on PATH with a real executable later. bash's tier-1
    is access(X_OK) on ANY type, so it takes the special file and execve's it —
    a FIFO HANGS, a socket fails 126. psh's tier-1 requires a REGULAR FILE, so it
    treats the special file as a stat-exists fallback and runs the later real
    executable instead (no hang, no spurious 126). Pinned via the socket face
    (the FIFO face would hang bash). bash 5.2- and 5.3.15-verified."""

    def test_socket_earlier_bash_126_psh_runs_later(self):
        import os
        import shutil
        import socket
        import tempfile
        # A SHORT temp dir — AF_UNIX socket paths are capped (~104 bytes), too
        # short for a pytest tmp_path; bind relative from inside the dir.
        work = tempfile.mkdtemp(prefix="cvs")
        cwd0 = os.getcwd()
        s = socket.socket(socket.AF_UNIX)
        try:
            os.makedirs(os.path.join(work, "sock"))
            os.makedirs(os.path.join(work, "late"))
            os.chdir(os.path.join(work, "sock"))
            try:
                s.bind("cvs")                    # relative bind → short path
            except PermissionError:
                # macOS seatbelt `(deny network*)` covers an AF_UNIX bind, so
                # a sandboxed gate cannot even build the fixture: neither
                # shell has run and nothing was compared — SKIP, never FAIL
                # (D4). Unsandboxed the bind succeeds and the row runs.
                pytest.skip("AF_UNIX bind denied (sandboxed gate); the "
                            "socket-on-PATH fixture cannot be created")
            os.chmod("cvs", 0o755)
            os.chdir(cwd0)
            late = os.path.join(work, "late", "cvs")
            with open(late, "w") as f:
                f.write("#!/bin/sh\necho LATE\n")
            os.chmod(late, 0o755)
            cmd = (f"PATH={work}/sock:{work}/late; cvs 2>/dev/null; echo rc=$?")
            b = _run([BASH], cmd)
            p = _run(PSH, cmd)
            assert "rc=126" in b.stdout          # bash takes the socket (tier-1)
            assert "LATE" in p.stdout and "rc=0" in p.stdout   # psh runs later
        finally:
            os.chdir(cwd0)
            s.close()
            shutil.rmtree(work, ignore_errors=True)


class TestMixedValidMalformedExactCountHybrid:
    """Carry #21 (I1): ``read -N`` over a MIX of valid and malformed multibyte
    bytes lands on a count boundary that matches NEITHER the UTF-8 nor the
    C-locale bash oracle — a deliberate HYBRID model, not "just mbrtowc quirks".

    psh is Unicode-native for a VALID multibyte sequence (one character, like
    UTF-8 bash) and byte-per-character for a MALFORMED byte (one surrogate, like
    C-locale bash). Neither bash mode does both: UTF-8 bash lets an incomplete
    lead swallow the following byte, C bash counts every byte as a character.
    The HYBRID model itself is documented at ``psh/builtins/input_reader.py``
    (the "deliberate HYBRID" design note). The user guide's "Byte vs. character
    model" section (``docs/user_guide/17_differences_from_bash.md``) documents
    the GENERAL Unicode-native-vs-C-locale difference and the ``read -N1`` /
    ``-n1`` character model; it does NOT describe this MIXED-input count
    boundary, which lives only in the design note and in carry #21.

    RE-RULED **RE-CARRY** at slot 4B.2 (2026-08-07), which owns the decoder-seam
    fix that touches this code. The carry required fresh probes and forbade a
    silent behaviour change; the seam fix leaves every cell here byte-identical
    because none of them involves a timed read, so nothing is ever stranded at
    the drain seam. These pins are the standing guard for that.

    Characterization only: psh's model AND both bash oracles are asserted, so an
    accidental move on ANY of the three fails.
    """

    _CMD = ("read -N {n} x; printf 'rc=%s ' \"$?\"; "
            "printf '%s' \"$x\" | od -An -tx1 | tr -d ' \\n'")

    def _three_ways(self, n, payload):
        cmd = self._CMD.format(n=n)
        psh = run_psh(["-c", cmd], stdin_data=payload, stdin_mode="pipe",
                      timeout=20, env={"LC_ALL": "en_US.UTF-8"})
        utf8 = run_bash(["-c", cmd], stdin_data=payload, stdin_mode="pipe",
                        timeout=20, env={"LC_ALL": "en_US.UTF-8"})
        c = run_bash(["-c", cmd], stdin_data=payload, stdin_mode="pipe",
                     timeout=20, env={"LC_ALL": "C", "LANG": "C"})
        for r in (psh, utf8, c):
            assert is_comparable(r), r
        return psh.stdout.strip(), utf8.stdout.strip(), c.stdout.strip()

    @pytest.mark.parametrize("n,payload,psh_out,utf8_out,c_out", [
        # é then a lone lead C3 then A: at -N 2 psh takes é + the surrogate C3;
        # UTF-8 bash lets the incomplete lead swallow the A; C bash counts bytes.
        (2, b"\xc3\xa9\xc3A\n", "rc=0 c3a9c3", "rc=0 c3a9c341", "rc=0 c3a9"),
        (3, b"\xc3\xa9\xc3A\n", "rc=0 c3a9c341", "rc=0 c3a9c3410a", "rc=0 c3a9c3"),
        # € then a lone lead E2 then Z.
        (2, b"\xe2\x82\xac\xe2Z\n", "rc=0 e282ace2", "rc=0 e282ace25a",
         "rc=0 e282"),
        (3, b"\xe2\x82\xac\xe2Z\n", "rc=0 e282ace25a", "rc=0 e282ace25a0a",
         "rc=0 e282ac"),
    ])
    def test_hybrid_matches_neither_oracle(self, n, payload, psh_out, utf8_out,
                                           c_out):
        psh, utf8, c = self._three_ways(n, payload)
        assert psh == psh_out, f"psh model moved: {psh!r}"
        assert utf8 == utf8_out, f"UTF-8 bash oracle moved: {utf8!r}"
        assert c == c_out, f"C bash oracle moved: {c!r}"
        assert psh != utf8 and psh != c, (
            "carry #21 asserts psh matches NEITHER oracle here; it now matches "
            f"one (psh={psh!r} utf8={utf8!r} c={c!r}). Re-rule the carry.")

    def test_all_valid_input_matches_utf8_bash(self):
        """CONTROL: with no malformed byte, psh IS the UTF-8 oracle."""
        psh, utf8, c = self._three_ways(2, b"\xc3\xa9\xe2\x82\xac\n")
        assert psh == utf8 == "rc=0 c3a9e282ac"
        assert c == "rc=0 c3a9", "C bash counts bytes, so it must differ here"

    def test_all_malformed_input_matches_c_bash(self):
        """CONTROL: with no valid sequence, psh IS the C-locale oracle."""
        psh, utf8, c = self._three_ways(2, b"\xc3\xc3A\n")
        assert psh == c == "rc=0 c3c3"
        assert utf8 == "rc=0 c3c341", "UTF-8 bash swallows the byte after a lead"
