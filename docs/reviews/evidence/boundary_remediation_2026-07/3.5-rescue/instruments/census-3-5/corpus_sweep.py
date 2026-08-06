"""DEADNESS evidence for the outer ValueError legs (DELETED-DECIDER RULE).

The forcing run proved the legs FIRE if a VE arrives. This sweep asks the
other, decisive half: can a USER-REACHABLE input make one arrive?

Every leg under scrutiny guards a call to ``evaluate_arithmetic``. That
function's own body outside ``_evaluate_arithmetic_inner``'s try has no VE
source, and the inner converts ``(ValueError, OverflowError, MemoryError)``
into ``ShellArithmeticError`` (evaluator.py:752). So the claim under test is:

    NO user-reachable arithmetic input causes a bare ValueError to escape
    evaluate_arithmetic — hence every outer VE leg is DEAD.

The instrument: a wide corpus of arithmetic-error inputs x every calling
context, run under PSH_STRICT_ERRORS=1 (so an escaped internal defect cannot
hide), scanning for the 797 marker "unexpected arithmetic error" and for any
Python traceback. Bash is recorded beside each row for the message/rc
observables (subtlety 2).

A hit = the claim is REFUTED and the leg is live. Zero hits across the corpus
= the deadness claim's evidence.
"""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASH = "/opt/homebrew/bin/bash"
ENV = {**os.environ, "PYTHONPATH": str(ROOT), "PSH_STRICT_ERRORS": "1"}
PSH = [sys.executable, "-m", "psh"]

# --- user-reachable arithmetic failures (the EXPR slot) ---------------------
EXPRS = [
    ("div0",          "1/0"),
    ("mod0",          "1%0"),
    ("syntax_trail",  "1+"),
    ("syntax_bare",   "+"),
    ("syntax_two",    "1 2"),
    ("syntax_at",     "@@"),
    ("syntax_star",   "*"),
    ("syntax_lparen", "(1"),
    ("bad_octal",     "08"),
    ("bad_base_dig",  "2#5"),
    ("bad_base_hi",   "99#1"),
    ("bad_hex",       "0x"),
    ("bad_base_g",    "16#g"),
    ("digit_limit",   "9" * 4400),          # CPython str->int limit -> VE@752
    ("huge_pow",      "2**999999999"),      # OverflowError/MemoryError class
    ("neg_shift",     "1<<-1"),
    ("self_ref",      "SELFREF"),           # x='SELFREF' -> recursion guard
    ("undef_arith",   "nosuchvar"),         # unset -> 0 (NOT an error)
    ("bad_indirect",  "${!zz}"),
    ("empty",         ""),
]

# --- calling contexts: script template with {E} = the expression ------------
# NOTE: every loop body BREAKS. A corpus expression that evaluates to a large
# NON-ZERO value is a perfectly valid loop condition, so an unbounded body
# would spin forever on the success rows and the sweep would measure the
# harness, not the shell (round-1 harness defect, fixed here).
CTXS = [
    ("arith_exp",   'echo A$(({E}))B'),
    ("substring",   'v=abcdefgh; echo X${{v:{E}:2}}Y'),
    ("arith_cmd",   '(( {E} )); echo rc=$?'),
    ("cfor_init",   'for (({E}; 0; 0)); do break; done; echo rc=$?'),
    ("cfor_cond",   'for ((i=0; {E}; i++)); do break; done; echo rc=$?'),
    ("enh_test",    '[[ {E} -eq 0 ]]; echo rc=$?'),
    ("subscript",   'a=(1 2 3); echo X${{a[{E}]}}Y'),
    ("let_cmd",     'let "{E}"; echo rc=$?'),
    ("arr_assign",  'a=(1 2 3); a[{E}]=9; echo rc=$?'),
    ("declare_i",   'declare -i n="{E}"; echo rc=$?'),
]

PRELUDE = "SELFREF='SELFREF+1'; "

MARK_797 = "unexpected arithmetic error"
MARK_UNEXP = "unexpected error"


class Timed:
    """A timeout is DATA (a divergence in its own right), not a crash."""
    returncode, stdout, stderr, timedout = -1, "<TIMEOUT>", "<TIMEOUT>", True


def run(argv, script):
    try:
        r = subprocess.run(argv + ["-c", PRELUDE + script], cwd=str(ROOT),
                           capture_output=True, text=True, env=ENV, timeout=20)
        r.timedout = False
        return r
    except subprocess.TimeoutExpired:
        return Timed()


def main():
    disc = subprocess.run(
        [sys.executable, "-c",
         "import psh, psh.version as v; print(psh.__file__, v.__version__)"],
        cwd=str(ROOT), capture_output=True, text=True, env=ENV)
    assert disc.stdout.split()[0] == str(ROOT / "psh" / "__init__.py"), disc.stdout
    print("# tree :", disc.stdout.strip())
    print("# bash :", subprocess.run([BASH, "--version"], capture_output=True,
                                     text=True).stdout.splitlines()[0])
    print("# env  : PSH_STRICT_ERRORS=1 (an escaped internal defect CANNOT hide)")
    print(f"# cells: {len(EXPRS)} exprs x {len(CTXS)} contexts = "
          f"{len(EXPRS)*len(CTXS)}")
    print()

    hits797, hitsunexp, tracebacks, rcdiff = [], [], [], []
    n = 0
    for ename, expr in EXPRS:
        for cname, tmpl in CTXS:
            n += 1
            script = tmpl.format(E=expr)
            p = run(PSH, script)
            b = run([BASH], script)
            err = p.stderr
            if MARK_797 in err:
                hits797.append((ename, cname, err.strip()[:90]))
            elif MARK_UNEXP in err:
                hitsunexp.append((ename, cname, err.strip()[:90]))
            if "Traceback (most recent call last)" in err:
                tracebacks.append((ename, cname, err.strip()[-120:]))
            if p.returncode != b.returncode or p.stdout != b.stdout:
                rcdiff.append((ename, cname, b.returncode, p.returncode,
                               b.stdout.strip()[:22], p.stdout.strip()[:22]))

    print(f"=== SWEEP RESULT over {n} cells ===")
    print(f"  797 net ('{MARK_797}') hits : {len(hits797)}")
    for h in hits797:
        print("     ", h)
    print(f"  generic 'unexpected error' hits : {len(hitsunexp)}")
    for h in hitsunexp:
        print("     ", h)
    print(f"  python tracebacks (escaped internal defects) : {len(tracebacks)}")
    for h in tracebacks:
        print("     ", h)
    print()
    print(f"=== psh-vs-bash rc/stdout differences: {len(rcdiff)} "
          f"(context, recorded NOT chased — pre-existing wording/behaviour) ===")
    print(f"  {'expr':<14} {'ctx':<12} {'b_rc':>4} {'p_rc':>4}  "
          f"{'bash out':<24} {'psh out':<24}")
    for e, c, br, pr, bo, po in rcdiff:
        print(f"  {e:<14} {c:<12} {br:>4} {pr:>4}  {bo:<24} {po:<24}")


if __name__ == "__main__":
    main()
