"""S3 syntax-template timing matrix (campaign: boundary integrity).

The full read-time / lazy timing matrix for the syntax-bearing regions whose
OWN grammar is lazy but whose NESTED shell grammar bash validates at read time:
parameter-expansion operands, arithmetic templates, and array subscripts.

Axes (Ruling-2 rider): operand selection (set/unset) × quoting (unquoted /
double-quoted / single-quoted-literal) × channel (-c / file / stdin / -n) ×
dead-branch × backtick-vs-$(). Each case is self-contained (order-independent).

Comparison is CHANNEL-AWARE and rc-value-agnostic:

* REJECT cases: bash and psh must produce IDENTICAL stdout and BOTH a nonzero
  exit — the read-time-rejection TIMING match. (In -c the whole buffer is one
  parse unit so nothing runs; in file/stdin an earlier command on its own line
  runs before the offending line rejects — bash and psh agree either way.)
  These rows assert the TIMING only, so they stay agnostic about the exact
  status; the status itself is pinned at the bottom (it is channel-dependent —
  127 under ``-c``, 2 for a script file and stdin — not a single number).
* ACCEPT cases: identical stdout AND identical rc (valid, dynamic, lazy-dead,
  single-quoted-literal, and deferred-backtick cases must behave the same).

eval/source FATALITY is CLOSED (slot 2.4): a substitution-body syntax error
aborts the enclosing frame in psh as it does in bash, for both error kinds.
It is pinned at the bottom as an equality, not as a divergence. What remains
declared there is narrower: the mid-script trap-action status, and the status
bash's own EXIT trap observes.
"""

import os
import tempfile

import pytest
from shell_oracle import is_comparable, resolve_bash, run_bash, run_psh

_ORACLE = resolve_bash()   # loud: raises BashOracleUnavailable if absent
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

# Scratch directory for the "file" channel's throwaway scripts. Supplied by
# the autouse fixture below rather than <repo>/tmp, which exists only once
# someone has created it by hand — a fresh worktree failed every file-channel
# case with FileNotFoundError.
_SCRIPT_DIR: str = ""


@pytest.fixture(autouse=True, scope="module")
def _script_dir(tmp_path_factory):
    """Per-module, pytest-managed scratch dir for the file channel.

    Module-scoped so the file-channel cases share one directory, and
    per-worker under xdist (each worker imports its own copy of this module),
    so parallel runs cannot collide.
    """
    global _SCRIPT_DIR
    _SCRIPT_DIR = str(tmp_path_factory.mktemp("syntax-template-scripts"))
    yield
    _SCRIPT_DIR = ""


def _run_channel(runner, script, channel, *, is_psh):
    """runner is run_psh/run_bash; run `script` through `channel`."""
    if channel == "c":
        r = runner(["-c", script], cwd=_ROOT, timeout=30)
    elif channel == "stdin":
        r = runner([], stdin_data=script + "\n", stdin_mode="pipe",
                   cwd=_ROOT, timeout=30)
    elif channel == "validate":
        flag = "--validate" if is_psh else "-n"
        r = runner([flag, "-c", script], cwd=_ROOT, timeout=30)
    elif channel == "file":
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                         dir=_SCRIPT_DIR) as f:
            f.write(script + "\n")
            path = f.name
        try:
            r = runner([path], cwd=_ROOT, timeout=30)
        finally:
            os.unlink(path)
    else:
        raise ValueError(channel)
    assert is_comparable(r), r
    return r


def _psh(script, channel):
    return _run_channel(run_psh, script, channel, is_psh=True)


def _bash(script, channel):
    return _run_channel(run_bash, script, channel, is_psh=False)


_CHANNELS = ["c", "file", "stdin", "validate"]

# ---- REJECT: invalid nested modern substitution in a syntax-bearing region.
# id -> script (prefixed with `echo before;` so file/stdin have a prior command).
_REJECT = {
    "operand_unset": "echo before; unset x; echo ${x:-$(if)}; echo after",
    "operand_set": "echo before; x=set; echo ${x:-$(if)}; echo after",
    "operand_dquoted": 'echo before; x=set; echo ${x:-"$(if)"}; echo after',
    "operand_assign": "echo before; unset x; echo ${x:=$(if)}; echo after",
    "operand_altplus": "echo before; x=y; echo ${x:+$(if)}; echo after",
    "operand_errop": "echo before; x=y; echo ${x:?$(if)}; echo after",
    "operand_prefix": "echo before; x=abc; echo ${x#$(if)}; echo after",
    "operand_suffix": "echo before; x=abc; echo ${x%$(if)}; echo after",
    "operand_subst": "echo before; x=abc; echo ${x/$(if)/z}; echo after",
    "operand_nested": "echo before; x=set; echo ${x:-${y:-$(if)}}; echo after",
    "operand_procsub": "echo before; x=set; echo ${x:-<(if)}; echo after",
    "arith_expansion": "echo before; echo $(( $(if) + 1 )); echo after",
    "arith_command": "echo before; (( $(if) )); echo after",
    "arith_param_nested": "echo before; echo $(( ${x:-$(if)} )); echo after",
    "cstyle_init": "echo before; for ((i=$(if); i<2; i++)); do echo x; done; echo after",
    "cstyle_cond": "echo before; for ((i=0; $(if); i++)); do echo x; done; echo after",
    "cstyle_update": "echo before; for ((i=0; i<2; i=$(if))); do echo x; done; echo after",
    "subscript_ref": "echo before; a=(1 2); echo ${a[$(if)]}; echo after",
    "subscript_assign": "echo before; a[$(if)]=v; echo after",
    "subscript_lvalue": "echo before; (( a[$(if)] = 1 )); echo after",
    # dead-branch: read-time even though the region never executes.
    "dead_or_operand": "echo before; true || echo ${x:-$(if)}; echo after",
    "dead_if_arith": "echo before; if false; then echo $(( $(if) )); fi; echo after",
    "unreached_case_subscript": "echo before; case a in a) :;; b) echo ${z[$(if)]};; esac; echo after",
}


@pytest.mark.parametrize("channel", _CHANNELS)
@pytest.mark.parametrize("cid", list(_REJECT), ids=list(_REJECT))
def test_reject_matches_bash_timing(cid, channel):
    script = _REJECT[cid]
    p = _psh(script, channel)
    b = _bash(script, channel)
    assert b.returncode != 0, (cid, channel, "bash should reject", b.stdout)
    assert p.returncode != 0, (cid, channel, "psh should reject", p.stdout)
    # Identical stdout (channel-aware: -c => empty; file/stdin => "before").
    assert p.stdout == b.stdout, (cid, channel, repr(p.stdout), repr(b.stdout))
    assert "after" not in p.stdout, (cid, channel, repr(p.stdout))


# ---- ACCEPT: valid / lazy / literal / deferred / dynamic — identical behavior.
_ACCEPT = {
    "operand_valid": "x=set; echo ${x:-$(echo ok)}",
    "operand_valid_unset": "unset x; echo ${x:-$(echo ok)}",
    "operand_squote_literal": "x=set; echo ${x:-'$(if)'}",
    "operand_backtick_deferred": "x=set; echo ${x:-`if`}z",
    "operand_nested_valid": "unset x y; echo ${x:-${y:-deep}}",
    "arith_valid": "echo $(( 1 + 2 * 3 ))",
    "arith_dynamic_op": "op='+'; echo $((1 $op 2))",
    "arith_dynamic_expr": "e='1+2'; echo $((e))",
    "arith_dynamic_dollar": "e='1+2'; echo $(($e))",
    "arith_shift": "echo $(( 1 << 4 ))",
    "arith_lt": "echo $(( 3 < 5 ))",
    "arith_backtick_deferred": "echo $(( `false` 0 + 1 ))",
    "arith_cmd_valid": "(( 2 + 2 )); echo $?",
    "cstyle_valid": "for ((i=0;i<3;i++)); do printf %s $i; done; echo",
    "cstyle_dynamic": "inc='i++'; for ((i=0;i<3;$inc)); do printf %s $i; done; echo",
    # dead-branch arithmetic (bad arith, never evaluated) stays lazy -> no error.
    "dead_arith_or": "true || echo $((1+)); echo done",
    "dead_arith_if": "if false; then echo $((1+)); fi; echo done",
    "unselected_operand_arith": "x=set; echo ${x:-$((1+))}",
    "subscript_valid": "a=(0 1 2 3); echo ${a[1+1]}",
    "subscript_assign_valid": "a=(); a[1+1]=v; echo ${a[2]}",
    "subscript_cmdsub_valid": "a=(0 1 2); echo ${a[$(echo 1)]}",
}


@pytest.mark.parametrize("channel", ["c", "file", "stdin"])
@pytest.mark.parametrize("cid", list(_ACCEPT), ids=list(_ACCEPT))
def test_accept_matches_bash(cid, channel):
    script = _ACCEPT[cid]
    p = _psh(script, channel)
    b = _bash(script, channel)
    assert p.stdout == b.stdout, (cid, channel, repr(p.stdout), repr(b.stdout))
    assert p.returncode == b.returncode, (cid, channel, p.returncode, b.returncode)


# ---- Backtick timing tuple (Ruling 2c): non-fatal, empty, command runs, rc 0.
def test_backtick_inner_error_is_nonfatal_and_continues():
    """`echo x`if`y` runs echo (prints "xy"), the backtick yields empty, exit 0,
    and a diagnostic goes to stderr — bash's deferred-backtick policy, matched."""
    for shell in (_psh, _bash):
        r = shell("echo before; echo x`if`y; echo after", "c")
        assert r.returncode == 0, (shell, r.returncode, r.stderr)
        assert r.stdout == "before\nxy\nafter\n", (shell, repr(r.stdout))
        assert r.stderr != "", (shell, "expected a diagnostic on stderr")


# ---- CLOSED (slot 2.4): eval/source frame fatality — the I3 consumer.
def test_eval_source_frame_fatality_matches_bash():
    """CLOSED I3 divergence: a substitution-body syntax error inside an eval
    BODY now ABORTS the enclosing frame in psh too, exactly as in bash.

    The typed ``SubstitutionSyntaxError`` is consumed by
    ``core/exceptions.py#SubstitutionSyntaxAbort``, which no non-fork frame
    catches — so eval, source, functions, ``if`` conditions and ``&&`` lists
    all fail to contain it, matching bash's process-scoped abort.

    SCOPE OF THIS ROW: the body here is the UNTERMINATED error kind. The
    non-containment claim above holds for the other kind only because the
    accumulator's trial-parse exit is wired too — pinned separately by
    ``test_frame_fatality_for_complete_but_invalid_bodies``, which is the row
    that fails if that second site regresses.

    NOTE the ESCAPED ``\\$(if)``: the error must occur when EVAL parses its
    argument, not at the outer read. An UNESCAPED ``$(if)`` inside the
    double-quoted eval argument is an outer-read command substitution that S3
    validates wholesale (a different path to the same observable)."""
    b = _bash('eval "echo \\$(if)"; echo AFTER', "c")
    p = _psh('eval "echo \\$(if)"; echo AFTER', "c")
    assert b.returncode == p.returncode == 127       # both: fatal frame under -c
    assert "AFTER" not in b.stdout and "AFTER" not in p.stdout
    # A PLAIN (non-substitution) syntax error in eval stays non-fatal in BOTH —
    # the fatality is substitution-ORIGIN-specific, which is exactly the fact
    # the typed error carries. This control is what makes the pin meaningful.
    b2 = _bash('eval "if"; echo AFTER', "c")
    p2 = _psh('eval "if"; echo AFTER', "c")
    assert "AFTER" in b2.stdout and "AFTER" in p2.stdout
    assert b2.returncode == p2.returncode == 0
    # An operand-family error inside the eval body aborts identically
    # (structural identity with the top-level $() case).
    b3 = _bash('x=set; eval "echo \\${x:-\\$(if)}"; echo AFTER', "c")
    p3 = _psh('x=set; eval "echo \\${x:-\\$(if)}"; echo AFTER', "c")
    assert b3.returncode == p3.returncode == 127
    assert "AFTER" not in b3.stdout and "AFTER" not in p3.stdout


def test_frame_fatality_for_complete_but_invalid_bodies(tmp_path):
    """ERROR-KIND twin of the fatality pin above — the axis the round-1 corpus
    held constant, which left half of HIGH-9 alive.

    ``$(if)`` is UNTERMINATED (accumulator NeedMore -> flushed -> the
    ``_execute_buffered_command`` exit). ``$(fi)`` is COMPLETE but ill-formed:
    the trial parse completes carrying the same typed error and leaves by
    ``_run_from_source``'s error branch. A fix wired to only one exit still
    lets eval/source frames CONTINUE for this kind, so pin the frames for it
    directly, in every channel."""
    inner = tmp_path / "inner.sh"
    inner.write_text("echo IB\necho $(fi)\necho IA\n")
    rows = [
        ("echo B; eval 'echo $(fi)'; echo AFTER", "B\n"),
        ("echo B; eval 'cat <(fi)'; echo AFTER", "B\n"),
        (f"echo B; source {inner}; echo AFTER", "B\nIB\n"),
        ("f() { eval \"echo \\$(fi)\"; }; echo B; f; echo AFTER", "B\n"),
        ("echo B; eval 'echo $(fi)' && echo AND; echo AFTER", "B\n"),
        ("echo B; if eval 'echo $(fi)'; then echo T; fi; echo AFTER", "B\n"),
    ]
    for script, expect_out in rows:
        for channel, status in (("c", 127), ("file", 1), ("stdin", 1)):
            b, p = _bash(script, channel), _psh(script, channel)
            assert b.returncode == p.returncode == status, (script, channel, b, p)
            assert b.stdout == p.stdout == expect_out, (script, channel, b.stdout, p.stdout)


def test_forked_child_exit_trap_sees_its_own_status():
    """The forked child exits 1, and its OWN EXIT trap must observe that 1 —
    not the ordinary syntax-error 2 the raise site left behind. Guards
    ``executor/child_policy.py#sync_child_status_for_exit_trap``.

    A command-substitution child matches bash EXACTLY here (both show 1). For
    a SUBSHELL child bash instead prints its internal pre-truncation
    ``EX_BADSYNTAX`` 257 while its process status is still 1 — the same
    declared O4 choice as the main shell's EXIT trap: psh reports the true
    status."""
    for body in ("echo $(if)", "echo $(fi)"):     # BOTH error kinds
        cmd = ("x=$( trap 'echo T rc=$? >&2' EXIT; eval '%s' ); echo RC=$?"
               % body)
        b, p = _bash(cmd, "c"), _psh(cmd, "c")
        assert b.stdout == p.stdout == "RC=1\n", (body, b.stdout, p.stdout)
        assert "T rc=1" in b.stderr and "T rc=1" in p.stderr, (body, b.stderr, p.stderr)
        sub = ("( trap 'echo T rc=$? >&2' EXIT; eval '%s' ); echo RC=$?" % body)
        bs, ps = _bash(sub, "c"), _psh(sub, "c")
        assert bs.stdout == ps.stdout == "RC=1\n", (body, bs.stdout, ps.stdout)
        assert "T rc=257" in bs.stderr, (body, bs.stderr)   # bash's internal
        assert "T rc=1" in ps.stderr, (body, ps.stderr)     # psh: true status
    # CONTROL: an explicit `exit 1` in the same position agrees in both shells,
    # so the sync is about THIS outcome, not about traps generally.
    ctl = "( trap 'echo T rc=$? >&2' EXIT; exit 1 ); echo RC=$?"
    bc, pc = _bash(ctl, "c"), _psh(ctl, "c")
    assert bc.stdout == pc.stdout == "RC=1\n"
    assert "T rc=1" in bc.stderr and "T rc=1" in pc.stderr


def test_eval_frame_fatality_status_is_channel_dependent():
    """The frame abort's STATUS is not one number: bash uses 127 only in the
    ``-c`` channel and 1 (its EX_BADSYNTAX truncated to 8 bits) for a script
    FILE or stdin. Pins the per-channel mapping in
    ``core/internal_errors.py#substitution_abort_status`` against live bash so
    a future "simplification" to a single status is caught."""
    script = 'eval "echo \\$(if)"; echo AFTER'
    for channel, expected in (("c", 127), ("file", 1), ("stdin", 1)):
        b, p = _bash(script, channel), _psh(script, channel)
        assert b.returncode == p.returncode == expected, (channel, b, p)
        assert "AFTER" not in b.stdout and "AFTER" not in p.stdout, channel


def test_substitution_fatality_is_contained_by_forks():
    """A FORK contains the fatality (it is an ``exit`` of that process): the
    child dies with 1 and the parent runs on — in every channel, including
    ``-c`` where the main shell itself would have used 127. Non-fork frames do
    NOT contain it (pinned above), so this is the model's other half."""
    for channel in ("c", "file", "stdin"):
        for script in ("( eval 'echo $(if)' ); echo AFTER rc=$?",
                       "x=$(eval 'echo $(if)'); echo AFTER rc=$?",
                       "eval 'echo $(if)' | cat; echo AFTER rc=$?"):
            b, p = _bash(script, channel), _psh(script, channel)
            assert b.returncode == p.returncode == 0, (channel, script, b, p)
            assert b.stdout == p.stdout, (channel, script, b.stdout, p.stdout)


def test_substitution_fatality_status_under_errexit_is_2():
    """``set -e`` overrides the channel mapping: bash exits **2** for this
    fatality in every channel, direct or eval-nested — which is why errexit is
    checked FIRST in substitution_abort_status. psh matched this before the I3
    consumer landed (its eval returned 2 and errexit exited with it); the pin
    exists so the consumer did not silently break that accidental parity.

    ``set -e`` must be on its OWN LINE: a one-liner ``set -e; echo $(if)`` is
    parsed as a single buffer, so the read-time error happens BEFORE errexit is
    in effect and the ordinary channel status applies (pinned below)."""
    for script in ("set -e\necho B\necho $(if)\necho AFTER",
                   "set -e\necho B\neval 'echo $(if)'\necho AFTER"):
        for channel in ("c", "file", "stdin"):
            b, p = _bash(script, channel), _psh(script, channel)
            assert b.returncode == p.returncode == 2, (channel, script, b, p)
            assert "AFTER" not in b.stdout and "AFTER" not in p.stdout


def test_same_line_set_e_does_not_reach_the_read_time_error():
    """Control for the pin above: with ``set -e`` on the SAME line, the whole
    buffer is parsed before ``set -e`` ever runs, so errexit is NOT yet active
    when the substitution-body error is found — both shells fall back to the
    ordinary channel status (127 under ``-c``). Pins the ordering so the
    errexit branch cannot be "fixed" into applying to this shape."""
    script = "set -e; echo B; echo $(if); echo AFTER"
    b, p = _bash(script, "c"), _psh(script, "c")
    assert b.returncode == p.returncode == 127, (b, p)
    assert b.stdout == p.stdout == "", (b.stdout, p.stdout)


def test_substitution_fatality_runs_exit_trap_not_err_trap():
    """It is a real shell EXIT: the EXIT trap runs and observes the abort
    status, while the ERR trap does NOT fire. Both verified against live bash.

    DECLARED DIVERGENCE (slot 2.4, ruling O4): in the FILE/STDIN channels the
    status bash's EXIT trap observes is **257** — its internal ``EX_BADSYNTAX``
    before the 8-bit truncation that yields the process status 1. psh reports
    the real status (1) rather than replicating a pre-truncation internal, so
    the trap-visible ``$?`` differs while the PROCESS STATUS matches."""
    trap_script = "trap 'echo T rc=$?' EXIT; echo B; eval 'echo $(if)'"
    b, p = _bash(trap_script, "c"), _psh(trap_script, "c")
    assert b.returncode == p.returncode == 127
    assert b.stdout == p.stdout == "B\nT rc=127\n", (b.stdout, p.stdout)
    bf, pf = _bash(trap_script, "file"), _psh(trap_script, "file")
    assert bf.returncode == pf.returncode == 1          # process status matches
    assert bf.stdout == "B\nT rc=257\n", bf.stdout      # bash leaks EX_BADSYNTAX
    assert pf.stdout == "B\nT rc=1\n", pf.stdout        # psh: the real status
    # ERR trap must NOT fire in either shell.
    err_script = ("set -E; trap 'echo ERRTRAP' ERR; echo B; "
                  "eval 'echo $(if)'; echo AFTER")
    be, pe = _bash(err_script, "c"), _psh(err_script, "c")
    assert be.returncode == pe.returncode == 127
    assert be.stdout == pe.stdout == "B\n", (be.stdout, pe.stdout)


def test_substitution_fatality_not_stripped_by_command_or_builtin():
    """``command``/``builtin`` strip the POSIX special-builtin property, which
    suppresses the POSIX-mode syntax-exit policy — but NOT this fatality: bash
    still aborts. Pins that the consumer is deliberately NOT routed through
    ``SpecialBuiltinUsageError`` (which ``command`` does strip)."""
    for script in ("echo B; command eval 'echo $(if)'; echo AFTER",
                   "echo B; builtin eval 'echo $(if)'; echo AFTER"):
        for channel in ("c", "file", "stdin"):
            b, p = _bash(script, channel), _psh(script, channel)
            assert b.returncode == p.returncode, (channel, script, b, p)
            assert b.stdout == p.stdout == "B\n", (channel, script, p.stdout)
    # CONTROL: a PLAIN syntax error under `command eval` stays non-fatal.
    ctl = "echo B; command eval 'if'; echo AFTER"
    bc, pc = _bash(ctl, "c"), _psh(ctl, "c")
    assert bc.returncode == pc.returncode == 0
    assert bc.stdout == pc.stdout == "B\nAFTER\n"


def test_substitution_fatality_from_a_trap_action():
    """A TRAP ACTION is not one of the chartered frames, but it rides the same
    consumer, so its behavior is characterized here rather than left unpinned.

    An ``eval`` nested INSIDE the action is a fresh input and aborts in both
    shells, at the ordinary channel status. When the ACTION STRING'S OWN parse
    is what fails, both shells still abort and both print the same stdout, but
    the status differs in the FILE/STDIN channels — bash 2, psh 1 — because psh
    reaches it through the same nested-string branch that eval/source use.

    DECLARED DIVERGENCE (slot 2.4, ruling O3): matching bash's 2 would need
    bespoke trap-action plumbing distinct from the eval/source branch, which
    the ruling put out of scope; the ``-c`` channel and all stdout agree.

    DOMAIN — stated as what was actually probed, and no wider. The divergence
    is uniform across every action-bearing trap kind that fires MID-SCRIPT (a
    signal trap, DEBUG, ERR, RETURN) **in the NON-FORK case**, which is what
    the corpus below samples. It excludes two neighbours that behave
    differently and are pinned separately:

    * the EXIT trap at TEARDOWN, which MATCHES bash exactly —
      ``test_exit_trap_teardown_action_error_changes_nothing``;
    * the same actions inside a FORK, where the status is bash 2 / psh 1 in
      every channel unless effective errexit applies in the child —
      ``test_fork_times_midscript_trap_action_status``.

    RECORD CORRECTION (round 4 → 5): this paragraph previously claimed the
    universe was "probed rather than assumed" and "UNIFORM across every
    action-bearing trap kind". The fork axis was never in that corpus, so the
    claim was false on it. Round 4's ledger and completion report both stated
    this correction had been made HERE; it had not — the correcting sentence
    was written only into the new fork pin's docstring. Corrected in round 5."""
    nested = ("trap 'echo TA; eval \"echo \\$(if)\"; echo TA2' USR1\n"
              "echo B\nkill -USR1 $$\nsleep 0.2\necho AFTER")
    for channel, expected in (("c", 127), ("file", 1), ("stdin", 1)):
        b, p = _bash(nested, channel), _psh(nested, channel)
        assert b.returncode == p.returncode == expected, (channel, b, p)
        assert b.stdout == p.stdout == "B\nTA\n", (channel, b.stdout, p.stdout)
    # The action string's OWN parse failing, across the trap-kind universe.
    kinds = [
        ("trap ' echo TA; echo $(if); echo TA2' USR1\n"
         "echo B\nkill -USR1 $$\nsleep 0.2\necho AFTER", "B\n"),
        ("trap ' echo TA; echo $(fi); echo TA2' TERM\n"
         "echo B\nkill -TERM $$\nsleep 0.2\necho AFTER", "B\n"),
        ("trap ' echo $(fi)' DEBUG\necho B\necho AFTER", ""),
        ("set -E\ntrap ' echo $(fi)' ERR\necho B\nfalse\necho AFTER", "B\n"),
        ("set -T\ntrap ' echo $(fi)' RETURN\nf() { echo IN; }\n"
         "echo B\nf\necho AFTER", "B\nIN\n"),
    ]
    for own, expect_out in kinds:
        bc, pc = _bash(own, "c"), _psh(own, "c")
        assert bc.returncode == pc.returncode == 127, (own, bc, pc)   # -c agrees
        assert bc.stdout == pc.stdout == expect_out, (own, bc.stdout, pc.stdout)
        for channel in ("file", "stdin"):
            b, p = _bash(own, channel), _psh(own, channel)
            assert b.stdout == p.stdout == expect_out, (own, channel, b.stdout, p.stdout)
            assert b.returncode == 2 and p.returncode == 1, (own, channel, b, p)


def test_exit_trap_teardown_action_error_changes_nothing():
    """An EXIT trap whose ACTION TEXT carries a substitution-body error is
    REPORTED AND SWALLOWED at teardown, changing nothing — matching bash.

    This is the shape that shipped as a CLI-reachable Python traceback: the
    teardown callers guard ``SystemExit``/``Exception``, and the abort derives
    from ``BaseException``, so it escaped to the interpreter. It is consumed in
    ``core/trap_manager.py#TrapManager.execute_exit_trap``, which is the one
    method every teardown path calls, and deliberately NOT in ``execute_trap``
    — so the mid-script trap shape above still aborts.

    Distinct from ruling O3: at teardown there is nothing left to abort, and
    bash exits with the status it already had. NONE of the action runs."""
    rows = [
        # (script, expected rc, expected stdout)
        ("trap 'echo T; echo %s; echo T2' EXIT\necho B", 0, "B\n"),
        ("trap 'echo T; echo %s' EXIT\necho B\nexit 3", 3, "B\n"),
        ("trap 'echo %s' EXIT\necho B\nexit 0", 0, "B\n"),
        ("( trap 'echo CT; echo %s' EXIT; echo IN )\necho AFTER rc=$?",
         0, "IN\nAFTER rc=0\n"),
        ("x=$( trap 'echo %s' EXIT; echo IN )\necho AFTER rc=$? x=$x",
         0, "AFTER rc=0 x=IN\n"),
    ]
    for template, rc, out in rows:
        for body in ("$(if)", "$(fi)"):          # BOTH error kinds
            script = template % body
            for channel in ("c", "file", "stdin"):
                b, p = _bash(script, channel), _psh(script, channel)
                assert b.returncode == p.returncode == rc, (script, channel, b, p)
                assert b.stdout == p.stdout == out, (script, channel, b.stdout, p.stdout)
                assert "Traceback (most recent call last)" not in p.stderr, p.stderr[-400:]
    # CONTROL: a VALID EXIT action still runs and still leaves the status alone.
    ctl = "trap 'echo VALID' EXIT\necho B"
    bc, pc = _bash(ctl, "c"), _psh(ctl, "c")
    assert bc.returncode == pc.returncode == 0
    assert bc.stdout == pc.stdout == "B\nVALID\n"


def test_exit_trap_teardown_under_errexit_is_a_declared_divergence():
    """DECLARED DIVERGENCE (base-identical, NOT the consumer's doing): with
    ``set -e`` ACTIVE, bash's teardown-time abort still moves the status to 2;
    psh's teardown swallow leaves the status it already had.

    The pin above covers the same shapes WITHOUT errexit, which is exactly how
    this corner escaped five rounds of probing (round-5 verifier finding). The
    swallow is right — the action must not run and must not abort anything, and
    at teardown there is nothing left to abort — but bash's errexit still marks
    the shell, and psh's does not.

    Measured at base 1b271d77 and at this tip, both error kinds, all three
    channels, both parsers (``tmp/r24-probes/r6f.py`` -> ``r6f-*.txt``): psh's
    value is UNCHANGED across the whole branch, so nothing in slot 2.4 moved
    it. Pinned both-sides so the difference is a record rather than a surprise;
    closing it belongs to whoever owns errexit-at-teardown, not to HIGH-9."""
    rows = [
        # (script, bash rc, psh rc, shared stdout)
        ("( set -e; trap 'echo %s' EXIT; echo IN )\necho AFTER rc=$?",
         0, 0, None),                      # stdout differs only in the rc echo
        ("set -e\ntrap 'echo %s' EXIT\necho IN", 2, 0, "IN\n"),
    ]
    for template, brc, prc, out in rows:
        for body in ("$(if)", "$(fi)"):    # BOTH error kinds
            script = template % body
            for channel in ("c", "file", "stdin"):
                b, p = _bash(script, channel), _psh(script, channel)
                assert b.returncode == brc, (script, channel, b)
                assert p.returncode == prc, (script, channel, p)
                if out is not None:
                    assert b.stdout == p.stdout == out, (script, channel,
                                                         b.stdout, p.stdout)
                else:
                    # The fork shape: the divergence surfaces in $? AFTER the
                    # subshell, not in its exit status.
                    assert b.stdout == "IN\nAFTER rc=2\n", (script, channel, b)
                    assert p.stdout == "IN\nAFTER rc=0\n", (script, channel, p)
                assert "Traceback (most recent call last)" not in p.stderr, \
                    p.stderr[-400:]
    # CONTROL: the same fork shape WITHOUT errexit is an EQUALITY (the row the
    # pin above owns) — so this divergence is errexit's, not the swallow's.
    ctl = "( trap 'echo $(fi)' EXIT; echo IN )\necho AFTER rc=$?"
    bc, pc = _bash(ctl, "c"), _psh(ctl, "c")
    assert bc.returncode == pc.returncode == 0
    assert bc.stdout == pc.stdout == "IN\nAFTER rc=0\n"


def test_posix_relative_source_divergence_and_its_abort_status(tmp_path):
    """PRE-EXISTING divergence (NOT the substitution consumer's), pinned here
    because the I3 consumer MOVED psh's value inside it.

    ROOT CAUSE, established with the VALID-file control below: under
    ``set -o posix`` bash resolves ``.``/``source`` against ``$PATH`` ONLY, so
    a bare relative operand is refused outright (``source: sub.sh: file not
    found``, rc 1) and the file never runs. psh searches the current directory
    and sources it. That divergence is owned elsewhere (campaign successor
    row), and this pin does NOT assert it away.

    What the substitution consumer changed: because psh DOES source the file,
    it reaches the substitution-body syntax error inside it and now applies the
    per-channel abort status — so psh's ``-c`` value moved 2 -> 127 (bash stays
    1, having never opened the file). Pinned both-sides so the value move is
    recorded rather than merely narrated."""
    sub = tmp_path / "sub.sh"
    sub.write_text("echo IB\necho $(if)\necho IA\n")
    script = "set -o posix\necho B\nsource sub.sh\necho A\n"
    (tmp_path / "main.sh").write_text(script)

    # VALID-file CONTROL: bash refuses the relative source even with no syntax
    # error anywhere, which is what proves the root cause is `.`-lookup and not
    # anything to do with substitutions.
    ok = tmp_path / "ok.sh"
    ok.write_text("echo IB\necho IA\n")
    (tmp_path / "ctl.sh").write_text("set -o posix\necho B\nsource ok.sh\necho A\n")
    bctl = run_bash(["ctl.sh"], cwd=str(tmp_path), timeout=30)
    pctl = run_psh(["ctl.sh"], cwd=str(tmp_path), timeout=30)
    assert bctl.returncode == 1 and bctl.stdout == "B\n", bctl   # never sourced
    assert pctl.returncode == 0 and pctl.stdout == "B\nIB\nIA\nA\n", pctl

    # The substitution-error shape: bash still never opens the file (rc 1);
    # psh sources it, prints IB, then aborts with the per-channel status.
    b_file = run_bash(["main.sh"], cwd=str(tmp_path), timeout=30)
    p_file = run_psh(["main.sh"], cwd=str(tmp_path), timeout=30)
    assert b_file.returncode == 1 and b_file.stdout == "B\n", b_file
    assert p_file.returncode == 1 and p_file.stdout == "B\nIB\n", p_file
    b_c = run_bash(["-c", script], cwd=str(tmp_path), timeout=30)
    p_c = run_psh(["-c", script], cwd=str(tmp_path), timeout=30)
    assert b_c.returncode == 1 and b_c.stdout == "B\n", b_c
    assert p_c.returncode == 127 and p_c.stdout == "B\nIB\n", p_c  # moved 2->127


def test_eval_source_procsub_joined_family_matches_bash(tmp_path):
    """CLOSED (slot 2.4), co-flip of the fatality pin above: the PROCSUB
    spelling at an eval/source frame now aborts like bash, as does the cmdsub
    control — one consumer covers both spellings.

    History: 2.3's D3 routed the procsub spelling onto the same typed
    ``SubstitutionSyntaxError`` path as ``$()``, which JOINED it to the
    pre-existing I3 family. Before 2.3, psh matched bash here only by
    ACCIDENT — the un-validated spelling reached the runtime indexed-arith
    path, whose fatal discard produced the same observables by a different
    mechanism. Now both spellings abort through the one typed outcome, so the
    match is structural rather than coincidental."""
    src_file = tmp_path / 'z4src.sh'
    src_file.write_text('a[<(if)]=1\n')
    rows = [
        ("eval 'a[<(if)]=1'; echo ran rc=$?", 'eval+procsub'),
        ("eval 'a[$(if)]=1'; echo ran rc=$?", 'eval+cmdsub (pre-existing control)'),
        (f"source {src_file}; echo ran rc=$?", 'source+procsub'),
    ]
    for script, label in rows:
        b = _bash(script, "file")
        pr = _psh(script, "file")
        assert b.returncode == pr.returncode == 1, (label, b, pr)
        assert 'ran' not in b.stdout and 'ran' not in pr.stdout, (label, b, pr)
    # Dead-branch control: the frame never runs -> parity (nothing eager).
    dead = "true || eval 'a[<(if)]=1'; echo ran"
    bd, pd = _bash(dead, "file"), _psh(dead, "file")
    assert bd.stdout == pd.stdout == 'ran\n'
    assert bd.returncode == pd.returncode == 0


# ==========================================================================
# ROUND 4 (verification round 3 bounce): the AXIS INTERSECTIONS the earlier
# corpora missed. Each earlier corpus varied ONE axis while holding the others
# fixed, so every one of these rows was invisible to it.
# ==========================================================================

def test_fork_times_errexit_uses_effective_errexit():
    """A forked child's abort status honours EFFECTIVE errexit — the flag MINUS
    the suppression context — not the raw flag.

    Guards ``core/internal_errors.py#substitution_child_abort_status``. The two
    shapes are indistinguishable from the child's ShellState (both read
    ``errexit=True``), which is why the fork sites pass their suppression depth
    in; a fix that consults only the flag regresses the suppressed row, and one
    that consults only the state cannot tell them apart at all."""
    inner = "eval 'echo $(fi)'"
    # UNSUPPRESSED, errexit set INSIDE the child -> child 2, parent continues.
    script = "( set -e; %s )\necho AFTER rc=$?" % inner
    for channel in ("c", "file"):
        b, p = _bash(script, channel), _psh(script, channel)
        assert b.stdout == p.stdout == "AFTER rc=2\n", (script, channel, b.stdout, p.stdout)
    # errexit OUTSIDE and UNSUPPRESSED: the failing subshell trips the parent's
    # errexit, so the parent exits and AFTER never runs — in both shells.
    outer = "set -e\n( %s )\necho AFTER rc=$?" % inner
    for channel in ("c", "file"):
        b, p = _bash(outer, channel), _psh(outer, channel)
        assert b.stdout == p.stdout == "", (outer, channel, b.stdout, p.stdout)
    # SUPPRESSED contexts: errexit does NOT apply -> 1, in bash and psh alike.
    # `||` and an `if` condition expose the child's own 1; `!` INVERTS it to 0.
    # Each row pins the value both shells actually produce, not the child's
    # internal status.
    suppressed = [
        ("set -e\n( %s ) || echo GOT rc=$?" % inner, "GOT rc=1\n"),
        ("set -e\nif ( %s ); then echo T; else echo GOT rc=$?; fi" % inner,
         "GOT rc=1\n"),
        ("set -e\n! ( %s )\necho GOT rc=$?" % inner, "GOT rc=0\n"),
    ]
    for script, expected in suppressed:
        for channel in ("c", "file"):
            b, p = _bash(script, channel), _psh(script, channel)
            assert b.stdout == p.stdout == expected, (script, channel, b.stdout, p.stdout)
    # NO errexit at all -> 1 (the row the flat-constant mapping got right).
    plain = "( %s )\necho AFTER rc=$?" % inner
    b, p = _bash(plain, "c"), _psh(plain, "c")
    assert b.stdout == p.stdout == "AFTER rc=1\n", (b.stdout, p.stdout)


def test_fork_times_midscript_trap_action_status():
    """DECLARED DIVERGENCE (round-4 amendment to ruling O3): a MID-SCRIPT trap
    action whose own text carries the error, inside a FORK.

    The TIMING half matches bash (the child aborts — at base it did not abort
    at all). The STATUS differs: bash's child is 2, psh's is 1, joining the
    same declared family as the non-fork file/stdin 2-vs-1 row.

    EXCEPT when EFFECTIVE errexit is active in the child, where both are 2 —
    the composition row. Round 3's docstring claimed this domain was 'probed
    rather than assumed'; the fork axis was NOT in that corpus and the claim
    was false on it. Corrected here and in the O3 paragraph above."""
    dbg = "set -T; trap 'echo $(fi)' DEBUG; echo IN"
    err = "set -E; trap 'echo $(fi)' ERR; false"
    for body in (dbg, err):
        for channel in ("c", "file"):
            script = "( %s )\necho AFTER rc=$?" % body
            b, p = _bash(script, channel), _psh(script, channel)
            assert b.stdout == "AFTER rc=2\n", (body, channel, b.stdout)
            assert p.stdout == "AFTER rc=1\n", (body, channel, p.stdout)
    # COMPOSITION: fork x trap-action x EFFECTIVE errexit -> both 2.
    comp = "( set -e; %s )\necho AFTER rc=$?" % dbg
    for channel in ("c", "file"):
        b, p = _bash(comp, channel), _psh(comp, channel)
        assert b.stdout == p.stdout == "AFTER rc=2\n", (channel, b.stdout, p.stdout)
    # ...and with errexit SUPPRESSED it returns to the declared 2-vs-1.
    supp = "set -e\n( %s ) || echo GOT rc=$?" % dbg
    b, p = _bash(supp, "c"), _psh(supp, "c")
    assert b.stdout == "GOT rc=2\n" and p.stdout == "GOT rc=1\n", (b.stdout, p.stdout)


def test_main_shell_suppressed_errexit_status_matches_bash():
    """CLOSED (round 5): in the MAIN shell a suppressing context (``||``,
    ``&&`` non-final, an ``if``/``while`` condition, ``!``) now yields bash's
    ordinary CHANNEL status rather than the errexit 2.

    FLIP DECLARED, not silent: rounds 4-5 pinned this as a DIVERGENCE (psh 2 vs
    bash 127/-c, 1/file) and carried it to a successor. Extending the
    stamp-at-raise to ``substitution_abort_status`` closed it in-slot, so the
    row is flipped to EQUALITY here and the carry is WITHDRAWN. errexit is
    EFFECTIVE errexit at the main shell too, exactly as in the child half.

    Matrix behind this row: 6 suppression contexts x eval/direct x both error
    kinds x 3 channels x both parsers = 144 rows, 0 mismatches.

    RECORD CORRECTION preserved through the flip (round 4 -> 5): round 4
    described this family as "base-identical / not mine". That was MEASURED
    FALSE against a base worktree at 1b271d77 — BASE continued with rc 0 and
    printed ``GOT rc=2`` / ``AFTER rc=0``, while the round-4 tip ABORTED with
    rc 2 and no output, so the slot HAD moved the observable. What was
    genuinely pre-existing is only that psh's status never matched bash's.
    Kept here because the flip withdrew the carry row that used to hold this
    history, and a corrected record must outlive the thing it corrects."""
    for script in ("set -e\neval 'echo $(fi)' || echo GOT",
                   "set -e\nif eval 'echo $(fi)'; then echo T; fi",
                   "set -e\n! eval 'echo $(fi)'",
                   "set -e\neval 'echo $(fi)' && echo AND"):
        for channel in ("c", "file", "stdin"):
            b, p = _bash(script, channel), _psh(script, channel)
            assert b.returncode == p.returncode, (script, channel, b, p)
            assert b.stdout == p.stdout, (script, channel, b.stdout, p.stdout)
    # CONTROL: UNsuppressed errexit still uses the errexit status 2.
    plain = "set -e\necho B\neval 'echo $(fi)'\necho AFTER"
    for channel in ("c", "file", "stdin"):
        b, p = _bash(plain, channel), _psh(plain, channel)
        assert b.returncode == p.returncode == 2, (channel, b, p)


def test_unclosed_cmdsub_classified_bodies_are_carried(tmp_path):
    """DECLARED + CARRIED (round 4, ruling R4-C): the THIRD route.

    psh's cmdsub SCANNER classifies some bodies as an unclosed substitution
    rather than handing them to the nested parser, so they raise a PLAIN
    ParseError with ``substitution_origin`` False — neither the 2.3 producer
    typing nor either 2.4 consumer fires, and the pre-2.4 behaviour survives.

    THE DOMAIN is not "case bodies": it is the bodies that defeat the scanner's
    PAREN/QUOTE BALANCING. Censused over every compound opener plus the
    grouping and quote forms (23 forms x both spellings); exactly these six are
    untyped in the ``$( )`` spelling — a `case` with a pattern-closing paren,
    a bare ``case x in``, a nested ``(``, a nested ``$((``, and the two
    unterminated-quote forms. Every other opener (for/while/until/if/select/
    brace-group/function-body/``[[``) IS typed end-to-end. The ``<( )``
    spelling of the SAME bodies is scanner-classified as well — an isolated
    parse-API census reports it typed, but the end-to-end route disagrees
    because the scanner runs first, and the end-to-end behaviour is what this
    carry records. Base-identical, so not a regression — carried to the r18
    lexer successor, which owns scanner classification."""
    for body in ("case x in a) :;", "case x in"):
        script = "echo B\necho $(%s)\necho AFTER" % body
        b, p = _bash(script, "c"), _psh(script, "c")
        assert b.returncode == 127 and p.returncode == 2, (body, b, p)
        assert b.stdout == p.stdout == "B\n", (body, b.stdout, p.stdout)
        # The frame fatality is likewise NOT consumed for this route.
        ev = "echo B\neval 'echo $(%s)'\necho AFTER" % body
        be, pe = _bash(ev, "c"), _psh(ev, "c")
        assert be.returncode == 127 and "AFTER" not in be.stdout, (body, be)
        assert pe.returncode == 0 and "AFTER" in pe.stdout, (body, pe)
    # The `<( )` spelling of the SAME body is scanner-classified too, so it
    # carries with the family. (An isolated parse-API census reports this shape
    # as typed; the end-to-end route disagrees, because the scanner runs first.
    # The end-to-end behaviour is what the carry records.)
    proc = "echo B\ncat <(case x in a) :;)\necho AFTER"
    bp, pp_ = _bash(proc, "c"), _psh(proc, "c")
    assert bp.returncode == 127 and pp_.returncode == 2, (bp, pp_)
    typed = "echo B\necho $(while true)\necho AFTER"
    bt, pt = _bash(typed, "c"), _psh(typed, "c")
    assert bt.returncode == pt.returncode == 127, (bt, pt)


def test_posix_option_times_fork_matrix():
    """OPTION x FORK matrix for the abort status — the pin that round 4's
    ledger CLAIMED existed. It did not: round 4 ran this as a probe only and
    recorded it as "pinned". Added in round 5 with the record corrected.

    ``set -o posix`` does not change the child's status (1, or 2 under
    effective errexit, exactly as without it); the errexit column is the
    R4-A rule; the pipeline column is the member's own containment."""
    inner = "eval 'echo $(fi)'"
    rows = [
        # (option prefix inside the fork, fork shape, expected stdout)
        ("",              "( %s )",            "AFTER rc=1\n"),
        ("set -o posix; ", "( %s )",           "AFTER rc=1\n"),
        ("set -e; ",      "( %s )",            "AFTER rc=2\n"),
        ("",              "x=$( %s )",         "AFTER rc=1\n"),
        ("set -o posix; ", "x=$( %s )",        "AFTER rc=1\n"),
        ("set -e; ",      "x=$( %s )",         "AFTER rc=2\n"),
        ("",              "( %s ) | cat",      "AFTER rc=0\n"),
        ("set -o posix; ", "( %s ) | cat",     "AFTER rc=0\n"),
        ("set -e; ",      "( %s ) | cat",      "AFTER rc=0\n"),
    ]
    for opt, shape, expected in rows:
        script = (shape % (opt + inner)) + "\necho AFTER rc=$?"
        for channel in ("c", "file"):
            b, p = _bash(script, channel), _psh(script, channel)
            assert b.stdout == p.stdout == expected, (script, channel, b.stdout, p.stdout)


def test_interactive_dash_c_channel_disposition():
    """DECLARED (round 5, ruling R5-F): the ``-i -c`` channel.

    psh gates the abort on ``state.is_script_mode``, which ``-i -c`` turns off,
    so the consumer never fires there. Probed against ``bash -i -c`` rather
    than assumed:

    * an EVAL frame's CONTINUATION: BOTH shells continue (rc 0, ``AFTER``
      prints). bash does not abort an interactive shell's frame either, so
      psh's exemption is right and this row MATCHES.
    * the DIRECT shape: both reject the buffer and print nothing, but the
      status differs — bash 1, psh 2.
    * the eval frame's STATUS, and the FORK shapes: psh leaves 2 where bash
      leaves 1.

    RECORD CORRECTION (round 5 -> 6). The round-5 text of this pin said "Only
    the status differs, and only on the direct shape". The second half was
    FALSE and the tree falsified it: within this very channel the fork shapes
    differ too (``( set -e; eval 'echo $(if)' ) || echo SUPPRC=$?`` -> bash 1,
    psh 2), as does the eval frame's own ``$?``. They are added as rows below
    rather than left to prose. Cause of the false absolute: the round-5 rows
    observed only the SHELL's exit status, so every shape whose divergence
    shows up in ``$?`` INSIDE the frame was invisible to the instrument.

    All rows here are BASE-IDENTICAL (measured at 1b271d77 and at the slot tip,
    both parsers: ``tmp/r24-probes/r6c_flags.py`` -> ``r6c-flags-*.txt``), so
    the slot moved nothing in this channel. Interactivity semantics are
    deliberately NOT touched to close them (out of scope); the mechanism is the
    per-shell ``is_script_mode`` gate, which a forked child of an interactive
    shell inherits — see the interactive PTY pin
    ``tests/system/interactive/test_substitution_abort_interactive_pty.py``,
    which pins the same family at a real terminal."""
    ev = "echo B; eval 'echo $(fi)'; echo AFTER"
    direct = "echo B; echo $(fi); echo AFTER"
    # Routed through the typed runners, not raw subprocess: the oracle-bearing
    # module ratchet requires every launch to keep the is_comparable net.
    b_ev = run_bash(["-i", "-c", ev], cwd=_ROOT, timeout=30)
    p_ev = run_psh(["-i", "-c", ev], cwd=_ROOT, timeout=30)
    assert b_ev.returncode == p_ev.returncode == 0, (b_ev, p_ev)
    assert b_ev.stdout == p_ev.stdout == "B\nAFTER\n", (b_ev.stdout, p_ev.stdout)
    b_d = run_bash(["-i", "-c", direct], cwd=_ROOT, timeout=30)
    p_d = run_psh(["-i", "-c", direct], cwd=_ROOT, timeout=30)
    assert b_d.stdout == p_d.stdout == "", (b_d.stdout, p_d.stdout)
    assert b_d.returncode == 1 and p_d.returncode == 2, (b_d, p_d)

    # The rows the round-5 instrument could not see: the divergence lands in
    # $? INSIDE the frame, while the shell itself exits 0.
    for script, bash_out, psh_out in [
        # a FORK inside the interactive shell, with and without errexit
        ("( set -e; eval 'echo $(if)' ) || echo SUPPRC=$?",
         "SUPPRC=1\n", "SUPPRC=2\n"),
        ("( eval 'echo $(if)' ) || echo SUPPRC=$?",
         "SUPPRC=1\n", "SUPPRC=2\n"),
        # the eval frame's own status (its CONTINUATION already matches above)
        ("eval 'echo $(fi)'; echo AFTERRC=$?", "AFTERRC=1\n", "AFTERRC=2\n"),
    ]:
        b = run_bash(["-i", "-c", script], cwd=_ROOT, timeout=30)
        p = run_psh(["-i", "-c", script], cwd=_ROOT, timeout=30)
        assert b.returncode == p.returncode == 0, (script, b, p)
        assert b.stdout == bash_out, (script, b.stdout)
        assert p.stdout == psh_out, (script, p.stdout)
    # CONTROL: with errexit ACTIVE and UNSUPPRESSED the fork agrees — so the
    # divergence above is the suppression/child gate, not the fork itself.
    ctl = "( set -e; eval 'echo $(if)' ); echo AFTERRC=$?"
    bc = run_bash(["-i", "-c", ctl], cwd=_ROOT, timeout=30)
    pc = run_psh(["-i", "-c", ctl], cwd=_ROOT, timeout=30)
    assert bc.stdout == pc.stdout == "AFTERRC=2\n", (bc.stdout, pc.stdout)


def test_function_member_channel_rule_is_a_declared_divergence():
    """A FUNCTION-call pipeline member: bash applies the MAIN-SHELL channel
    rule inside the forked member, psh applies the child rule.

    `-c` channel: bash 127, psh 1. File and stdin: both 1, so the divergence
    is the CHANNEL rule and nothing else. It shows up only for a member that
    calls a FUNCTION — the brace-group and subshell member spellings give 1 in
    every channel in BOTH shells (controls below).

    DECLARED, NOT FIXED, and pinned because THE SLOT MOVED IT TWICE: at base
    1b271d77 this shape did not abort at all (the function frame contained the
    error and INFUNC printed), round 4 made it 2, and it is 1 now. An
    unpinned behaviour delta is a bounce even when it is an improvement, and
    this one is still short of bash.

    WHY NOT FIXED HERE: psh's forked children deliberately do NOT use the
    channel rule — `core/internal_errors.py#substitution_child_abort_status`
    drops it precisely because a subshell, command substitution, backtick,
    pipeline member or background job inside a `-c` shell exits 1 and not 127,
    which five rounds of probing established and several pins now assert. bash
    disagrees with itself here (its brace-group and subshell members answer 1
    in `-c`, its function member answers 127), so matching it means teaching
    psh's child policy a shape-dependent exception to a rule the rest of the
    suite pins. That is a policy change, not a frame-outcome fix, and it
    belongs to whoever owns the child-vs-main split.

    Measured over bash 5.2.26, both parsers, chain-replayed at base 1b271d77,
    round-4 f0cc466e and the slot tip (``tmp/r24-probes/r6b2.py``,
    ``r6b4.py`` -> the ``s3``/``p12``/``k5``/``k10`` rows)."""
    function_members = [
        # a plain function call as the member
        "f() { eval 'echo $(if)'; }\nset -e\n{ true | f; } || echo GOT rc=$?",
        # the same function reached through an expansion
        "f() { eval 'echo $(if)'; }\nQ=f\nset -e\n{ true | $Q; } || echo GOT rc=$?",
        # a function whose BODY is itself a compound
        "f() { { eval 'echo $(if)'; }; }\nset -e\n{ true | f; } || echo GOT rc=$?",
    ]
    for script in function_members:
        b_c, p_c = _bash(script, "c"), _psh(script, "c")
        assert b_c.stdout == "GOT rc=127\n", (script, b_c.stdout)
        assert p_c.stdout == "GOT rc=1\n", (script, p_c.stdout)
        # file and stdin AGREE at 1 — the divergence is the channel rule.
        for channel in ("file", "stdin"):
            b, p = _bash(script, channel), _psh(script, channel)
            assert b.stdout == p.stdout == "GOT rc=1\n", (script, channel,
                                                          b.stdout, p.stdout)
    # CONTROLS: the OTHER compound member spellings agree with bash in the
    # `-c` channel too, which is what makes this specific to a function frame.
    for member in ["{ eval 'echo $(if)'; }", "( eval 'echo $(if)' )"]:
        script = "set -e\n{ true | %s; } || echo GOT rc=$?" % member
        b, p = _bash(script, "c"), _psh(script, "c")
        assert b.stdout == p.stdout == "GOT rc=1\n", (member, b.stdout, p.stdout)


def test_static_check_spellings_dash_n_and_validate():
    """psh's ``-n`` matches bash's ``-n``; psh's ``--validate`` does not.

    IMPROVEMENT PINNED (slot 2.4): psh's noexec spelling moved 2 -> 127 in the
    ``-c`` channel for every substitution-body shape, which is what bash gives.
    It rode in on the channel rule rather than being aimed at, and an unpinned
    improvement is indistinguishable from an accident — so it is pinned here,
    with the divergent sibling beside it.

    DECLARED ASYMMETRY: ``--validate`` is psh's own static-check spelling (bash
    has no equivalent; the timing matrix above uses it as the analogue of bash
    ``-n``). It still answers 2 on the same input, so psh's two static checks
    now disagree with each other. Recorded rather than fixed: which of the two
    should carry the channel rule is a CLI-surface question, not a frame-outcome
    one. Measured at base 1b271d77 and at the slot tip, both parsers
    (``tmp/r24-probes/r6c_flags.py`` -> ``r6c-flags-*.txt``): at base psh ``-n``
    answered 2 in the ``-c`` channel, so this row is red-on-base."""
    substitution_shapes = ["echo $(if)", "echo $(fi)", "cat <(if)"]
    for script in substitution_shapes:
        b_c = run_bash(["-n", "-c", script], cwd=_ROOT, timeout=30)
        p_c = run_psh(["-n", "-c", script], cwd=_ROOT, timeout=30)
        assert b_c.returncode == 127, (script, b_c)
        assert p_c.returncode == 127, (script, p_c)          # moved 2 -> 127
        v_c = run_psh(["--validate", "-c", script], cwd=_ROOT, timeout=30)
        assert v_c.returncode == 2, (script, v_c)            # the asymmetry
    # CONTROLS. A plain syntax error is not substitution-origin, so the channel
    # rule does not apply to it and all three spellings agree at 2; valid input
    # is 0 everywhere. Both hold at base too — they are what makes the row
    # above a MOVE rather than a wholesale change of the flag's meaning.
    for script, expected in [("if", 2), ("echo hi", 0)]:
        b_c = run_bash(["-n", "-c", script], cwd=_ROOT, timeout=30)
        p_c = run_psh(["-n", "-c", script], cwd=_ROOT, timeout=30)
        v_c = run_psh(["--validate", "-c", script], cwd=_ROOT, timeout=30)
        assert b_c.returncode == p_c.returncode == v_c.returncode == expected, \
            (script, b_c, p_c, v_c)
