#!/opt/homebrew/bin/bash
# Q1 probe 14 (HIGH-5): ParseInputs threaded into the combinator — nested
# extglob @(x|y) inside $() must parse under --parser combinator (base:
# rejected by combinator only). 3-way: bash / psh rd / psh combinator.
# Axis: REGRESSION (base combinator rejection) + DIVERGENCE (vs bash).
set -u
WT='/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt'
BASH=/opt/homebrew/bin/bash
cd "$WT" || exit 1
SCRATCH="$WT/tmp/q1h5"; mkdir -p "$SCRATCH"

CMD='shopt -s extglob
v=$(echo @(x|y))
echo "got:$v"'

echo "=== bash"
bo=$(cd "$SCRATCH" && $BASH -c "$CMD" 2>&1); echo "rc=$? out=[$bo]"
echo "=== psh --parser rd"
po=$(cd "$SCRATCH" && PYTHONPATH="$WT" python -m psh --parser rd -c "$CMD" 2>&1); echo "rc=$? out=[$po]"
echo "=== psh --parser combinator"
co=$(cd "$SCRATCH" && PYTHONPATH="$WT" python -m psh --parser combinator -c "$CMD" 2>&1); echo "rc=$? out=[$co]"
