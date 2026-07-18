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
import subprocess
import sys
import tempfile

import pytest
from shell_oracle import resolve_bash

BASH = resolve_bash().path
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
_ENV = dict(os.environ, PYTHONPATH=_ROOT)
_PSH = [sys.executable, "-m", "psh"]


def _run(argv, stdin=None):
    return subprocess.run(argv, capture_output=True, text=True, timeout=30,
                          cwd=_ROOT, env=_ENV,
                          input=stdin,
                          stdin=None if stdin is not None else subprocess.DEVNULL)


def _run_channel(base, script, channel):
    """base is the psh/bash argv prefix; run `script` through `channel`."""
    if channel == "c":
        return _run(base + ["-c", script])
    if channel == "stdin":
        return _run(base, stdin=script + "\n")
    if channel == "validate":
        flag = "--validate" if base is _PSH else "-n"
        return _run(base + [flag, "-c", script])
    if channel == "file":
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                         dir=os.path.join(_ROOT, "tmp")) as f:
            f.write(script + "\n")
            path = f.name
        try:
            return _run(base + [path])
        finally:
            os.unlink(path)
    raise ValueError(channel)


def _psh(script, channel):
    return _run_channel(_PSH, script, channel)


def _bash(script, channel):
    return _run_channel([BASH], script, channel)


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


@pytest.mark.skipif(BASH is None, reason="bash not available")
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


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("channel", ["c", "file", "stdin"])
@pytest.mark.parametrize("cid", list(_ACCEPT), ids=list(_ACCEPT))
def test_accept_matches_bash(cid, channel):
    script = _ACCEPT[cid]
    p = _psh(script, channel)
    b = _bash(script, channel)
    assert p.stdout == b.stdout, (cid, channel, repr(p.stdout), repr(b.stdout))
    assert p.returncode == b.returncode, (cid, channel, p.returncode, b.returncode)


# ---- Backtick timing tuple (Ruling 2c): non-fatal, empty, command runs, rc 0.
@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_backtick_inner_error_is_nonfatal_and_continues():
    """`echo x`if`y` runs echo (prints "xy"), the backtick yields empty, exit 0,
    and a diagnostic goes to stderr — bash's deferred-backtick policy, matched."""
    for shell in (_psh, _bash):
        r = shell("echo before; echo x`if`y; echo after", "c")
        assert r.returncode == 0, (shell, r.returncode, r.stderr)
        assert r.stdout == "before\nxy\nafter\n", (shell, repr(r.stdout))
        assert r.stderr != "", (shell, "expected a diagnostic on stderr")


# ---- Documented divergence: eval/source frame fatality (carried to I3).
@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_divergence_eval_source_fatality_is_i3():
    """A substitution-body syntax error inside an eval BODY ABORTS the enclosing
    -c script in bash (rc 127, AFTER absent); psh continues (AFTER prints — its
    typed SubstitutionSyntaxError is not yet consumed by the eval/source frame).
    Same bash mechanism as the 127 rc — carried to I3. Pin the boundary so it
    stays explicit; S3's timing job is the DIRECT channels above.

    NOTE the ESCAPED ``\\$(if)``: the error must occur when EVAL parses its
    argument, not at the outer read. An UNESCAPED ``$(if)`` inside the
    double-quoted eval argument is an outer-read command substitution that S3
    validates wholesale (both shells reject the whole buffer — a match, not this
    divergence)."""
    b = _bash('eval "echo \\$(if)"; echo AFTER', "c")
    p = _psh('eval "echo \\$(if)"; echo AFTER', "c")
    assert b.returncode == 127 and "AFTER" not in b.stdout   # bash: fatal frame
    assert p.returncode == 0 and "AFTER" in p.stdout          # psh: continues (I3)
    # A PLAIN (non-substitution) syntax error in eval is non-fatal in BOTH — so
    # the divergence is substitution-specific, exactly like the 127 rc.
    b2 = _bash('eval "if"; echo AFTER', "c")
    p2 = _psh('eval "if"; echo AFTER', "c")
    assert "AFTER" in b2.stdout and "AFTER" in p2.stdout
    # An operand-family error inside the eval body is equally inert in psh
    # (structural identity with the top-level $() case — both go to I3).
    p3 = _psh('x=set; eval "echo \\${x:-\\$(if)}"; echo AFTER', "c")
    assert p3.returncode == 0 and "AFTER" in p3.stdout
