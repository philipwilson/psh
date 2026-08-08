#!/opt/homebrew/bin/bash
# Q1 probe 01: fresh re-execution of the r22 discriminator battery at
# ae871a16 (v0.773.0). Fresh equivalent of the committed
# wave0-base-probes/r22-probes.sh (which is 0.750.0-era and used bare `bash`).
# Axis: DIVERGENCE (tip vs bash 5.2.26). Oracle: /opt/homebrew/bin/bash.
set -u
WT='/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt'
BASH=/opt/homebrew/bin/bash
cd "$WT" || exit 1
PSH="python -m psh"

echo "bash oracle: $($BASH --version | head -1)"
python -c "import psh,psh.version;print('psh:',psh.__file__,psh.version.__version__);assert psh.__file__.startswith('$WT');assert psh.version.__version__=='0.773.0'" || exit 1

probe() {
  local label="$1" cmd="$2"
  local bo brc po prc
  bo=$($BASH -c "$cmd" 2>&1); brc=$?
  po=$($PSH -c "$cmd" 2>&1); prc=$?
  echo "=== $label"
  echo "  cmd : $cmd"
  echo "  bash: rc=$brc out=[$bo]"
  echo "  psh : rc=$prc out=[$po]"
  if [ "$bo" = "$po" ] && [ "$brc" = "$prc" ]; then
    echo "  MATCH"
  else
    # prefix-normalized second look (diagnostic-prefix classes only)
    local bn pn
    bn=$(printf '%s' "$bo" | sed -E 's/^(bash|psh)(: line [0-9]+)?: //; s/^[^:]*: line [0-9]+: //')
    pn=$(printf '%s' "$po" | sed -E 's/^(bash|psh)(: line [0-9]+)?: //; s/^[^:]*: line [0-9]+: //')
    if [ "$bn" = "$pn" ] && [ "$brc" = "$prc" ]; then
      echo "  MATCH-PREFIX-NORMALIZED"
    else
      echo "  DIVERGE"
    fi
  fi
}

probe "H3a-arith-prefix-posix" 'eval(){ echo FN; }; unset POSIXLY_CORRECT; A=$((POSIXLY_CORRECT=1)) eval "echo BUILTIN"'
probe "H3b-param-prefix-posix" 'eval(){ echo FN; }; unset POSIXLY_CORRECT; A=${POSIXLY_CORRECT:=1} eval "echo BUILTIN"'
probe "H4a-procsub-assoc-key" 'declare -A a; a[<(printf x)]=v; declare -p a'
probe "H4b-procsub-invalid-timing" 'declare -A a; echo before; a[<(if)]=x; echo after'
probe "H6-at-flatten-operand" 'unset x; set -- a b; printf "<%s>" "${x:-"$@"}"'
probe "H7a-nullable-extglob" 'shopt -s extglob; [[ "" == *@(a|*) ]]; echo rc=$?'
probe "H7b-neg-extglob-star" 'shopt -s extglob; [[ a == *!(a) ]]; echo rc=$?'
probe "H7c-neg-extglob-empty" 'shopt -s extglob; [[ "" == *!(*) ]]; echo rc=$?'
probe "H9a-substsyn-toplevel" 'echo $(if)'
probe "H9b-substsyn-eval-frame" 'eval "echo \$(if)"; echo AFTER'
probe "M4-bracket-extent" 'declare -A a; a["]"]=ok; echo "${a[$(printf "]")]}"'
probe "M4b-bracket-mixed" 'declare -A a; a["a]b"]=v2; echo "${a[a]b]:-MISS}"; echo "${a[$(printf "a]b")]}"'
echo "--- next row is carry B#3: DECLARED deviation (must-NOT-flip); DIVERGE here is AS-DECLARED ---"
probe "HIGH10c7-empty-arith-subscript-DECLARED" 'a=(x y); unset "a[]"; echo rc=$?; echo done'
