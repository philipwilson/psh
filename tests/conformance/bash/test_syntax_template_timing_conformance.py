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

    DOMAIN — the declaration's universe, probed rather than assumed: the
    divergence is UNIFORM across every action-bearing trap kind that fires
    MID-SCRIPT (a signal trap, DEBUG, ERR, RETURN), which is why the corpus
    below samples them rather than USR1 alone. It explicitly EXCLUDES the EXIT
    trap at teardown, which is a different shape and MATCHES bash exactly —
    see ``test_exit_trap_teardown_action_error_changes_nothing``."""
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


def test_main_shell_suppressed_errexit_status_is_carried():
    """DECLARED + CARRIED (round 4): in the MAIN shell, a suppressing context
    (``||``, an ``if`` condition) leaves psh at 2 where bash uses its ordinary
    channel status (127 under ``-c``, 1 for a file).

    This diverges AT BASE too — it is not introduced by this slot — and fixing
    it means applying the same effective-errexit question to the MAIN policy at
    every frame, which is its own bounded piece of work. Carried to the
    successor queue; the child-side plumbing added this round is the natural
    starting point."""
    for script in ("set -e\neval 'echo $(fi)' || echo GOT",
                   "set -e\nif eval 'echo $(fi)'; then echo T; fi"):
        b_c, p_c = _bash(script, "c"), _psh(script, "c")
        assert b_c.returncode == 127 and p_c.returncode == 2, (script, b_c, p_c)
        b_f, p_f = _bash(script, "file"), _psh(script, "file")
        assert b_f.returncode == 1 and p_f.returncode == 2, (script, b_f, p_f)


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
