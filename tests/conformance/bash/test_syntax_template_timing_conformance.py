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
  runs before the offending line rejects — bash and psh agree either way.) The
  exact code differs (bash 127 in string channels, psh's uniform 2); that is a
  documented divergence owned by I3, not asserted here.
* ACCEPT cases: identical stdout AND identical rc (valid, dynamic, lazy-dead,
  single-quoted-literal, and deferred-backtick cases must behave the same).

eval/source FATALITY (bash aborts the enclosing frame on a substitution-body
error; psh continues) is a separate pre-existing divergence carried to I3 and is
pinned as a divergence at the bottom, not in the match matrix.
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
    the ruling put out of scope; the ``-c`` channel and all stdout agree."""
    nested = ("trap 'echo TA; eval \"echo \\$(if)\"; echo TA2' USR1\n"
              "echo B\nkill -USR1 $$\nsleep 0.2\necho AFTER")
    for channel, expected in (("c", 127), ("file", 1), ("stdin", 1)):
        b, p = _bash(nested, channel), _psh(nested, channel)
        assert b.returncode == p.returncode == expected, (channel, b, p)
        assert b.stdout == p.stdout == "B\nTA\n", (channel, b.stdout, p.stdout)
    own = ("trap ' echo TA; echo $(if); echo TA2' USR1\n"
           "echo B\nkill -USR1 $$\nsleep 0.2\necho AFTER")
    bc, pc = _bash(own, "c"), _psh(own, "c")
    assert bc.returncode == pc.returncode == 127, (bc, pc)   # -c agrees
    for channel in ("file", "stdin"):
        b, p = _bash(own, channel), _psh(own, channel)
        assert b.stdout == p.stdout == "B\n", (channel, b.stdout, p.stdout)
        assert b.returncode == 2 and p.returncode == 1, (channel, b, p)


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
