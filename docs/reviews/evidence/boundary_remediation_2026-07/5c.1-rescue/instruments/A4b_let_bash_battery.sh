#!/opt/homebrew/bin/bash
# A4b — shell-level `let` diagnostic battery, psh vs bash, BOTH SIDES.
#
# The A4 instrument measured which exception TYPE reaches the handler. This
# measures what the USER sees — stdout, stderr and exit code — for the same
# shapes, against the live bash oracle. It is the both-sides cell the brief
# requires before any `let` diagnostic is touched, and it establishes the
# base-side record so a Phase B re-run can be diffed against it.
#
# Oracle: PATH bash, asserted below. NEVER /bin/bash. Explicit argv always
# (the zsh unquoted-$var 127 trap).
#
# Usage: A4b_let_bash_battery.sh <ROOT>
set -u

ROOT="${1:?usage: $0 <ROOT>}"
BASH_BIN="$(command -v bash)"
echo "oracle: $BASH_BIN"
"$BASH_BIN" --version | head -1
if [ "$BASH_BIN" = "/bin/bash" ]; then
    echo "REFUSING: /bin/bash is not the oracle" >&2
    exit 2
fi
echo "tree:   $ROOT"
cd "$ROOT" || exit 2
# Discriminator: prove which psh this ROOT actually runs.
PYTHONPATH="$ROOT" python3 -c "import psh,os,sys; p=os.path.dirname(psh.__file__); \
    sys.exit(0) if p==os.path.join('$ROOT','psh') else (print('DISCRIMINATOR FAILED: '+p),sys.exit(2))" \
    || exit 2
echo "discriminator OK"
echo

run_cell () {
    local label="$1" script="$2"
    local b_out b_rc p_out p_rc
    b_out="$("$BASH_BIN" -c "$script" 2>&1)"; b_rc=$?
    p_out="$(PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 \
             python3 -m psh -c "$script" 2>&1)"; p_rc=$?
    # Strip each shell's own program-name prefix so the comparison is about the
    # MESSAGE, not about whether the line starts with the shell's name.
    #
    # INSTRUMENT DEFECT FOUND AND FIXED (recorded, not buried): the first
    # version stripped a literal '^bash: ' — but bash prefixes diagnostics with
    # its full argv[0] ('/opt/homebrew/bin/bash: line 1: ...'), so the prefix
    # never matched and cells whose MESSAGE was byte-identical (escape/nounset,
    # ok/no-args) were reported as TEXT-DIFF. Under-stripping inflates the
    # divergence count, which is exactly the direction that would have let a
    # real regression hide inside a wall of false diffs. Both prefixes are now
    # stripped on EVERY line, path and all.
    local b_norm p_norm
    b_norm="$(printf '%s' "$b_out" | sed -E "s#^.*/?bash: (line [0-9]+: )?##")"
    p_norm="$(printf '%s' "$p_out" | sed -E "s#^.*/?psh: (line [0-9]+: )?##")"
    local verdict
    if [ "$b_norm" = "$p_norm" ] && [ "$b_rc" = "$p_rc" ]; then
        verdict="IDENTICAL"
    elif [ "$b_rc" = "$p_rc" ]; then
        verdict="RC-SAME/TEXT-DIFF"
    else
        verdict="DIVERGENT"
    fi
    printf '%-26s %-10s\n' "$label" "$verdict"
    printf '    script: %s\n' "$script"
    printf '    bash rc=%-4s out=%q\n' "$b_rc" "$b_out"
    printf '    psh  rc=%-4s out=%q\n' "$p_rc" "$p_out"
}

echo "=== A. ArithmeticError-leg cells (the LIVE leg) ==="
run_cell "arith/syntax-bare-op"  'let "1+"; echo rc=$?'
run_cell "arith/syntax-junk"     'let "@@@"; echo rc=$?'
run_cell "arith/div-zero"        'let "1/0"; echo rc=$?'
run_cell "arith/mod-zero"        'let "1%0"; echo rc=$?'
run_cell "arith/exp-negative"    'let "2**-1"; echo rc=$?'
run_cell "arith/base-bad"        'let "2#9"; echo rc=$?'
run_cell "arith/octal-bad"       'let "099"; echo rc=$?'
run_cell "arith/bad-subscript"   'let "a[]"; echo rc=$?'
run_cell "arith/unbalanced"      'let "(1+2"; echo rc=$?'

echo
echo "=== B. cells that ESCAPE both legs (PshError propagates past let) ==="
run_cell "escape/nounset"        'set -u; let "nosuchvar+1"; echo rc=$?'
run_cell "escape/nounset-incr"   'set -u; let "nosuchvar++"; echo rc=$?'
run_cell "escape/readonly"       'readonly r=1; let "r=2"; echo rc=$?'
run_cell "escape/readonly-incr"  'readonly r2=1; let "r2++"; echo rc=$?'

echo
echo "=== C. success/exit-status controls (let's own 0/1 contract) ==="
run_cell "ok/nonzero-is-0"       'let "1+1"; echo rc=$?'
run_cell "ok/zero-is-1"          'let "0"; echo rc=$?'
run_cell "ok/assign-zero-is-1"   'let "x=0"; echo rc=$?'
run_cell "ok/multi-last-wins"    'let "1" "0"; echo rc=$?'
run_cell "ok/no-args"            'let; echo rc=$?'

echo
echo "=== D. quote-provenance guard (W2/CV1 B1 — arith_source_quotes=False) ==="
run_cell "quote/assoc-let"       'declare -A m; m[a b]=7; let "v=m[a b]"; echo "v=$v rc=$?"'
run_cell "quote/assoc-arith"     'declare -A m; m[a b]=7; echo $((m[a b]))'
