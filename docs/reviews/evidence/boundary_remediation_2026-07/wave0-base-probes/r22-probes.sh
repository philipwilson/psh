#!/opt/homebrew/bin/bash
# Reappraisal #22 discriminator reproduction at v0.750.0 (0215279c) vs bash 5.2.26
PSH="python -m psh"
cd /Users/pwilson/src/psh-r22-verify || exit 1

probe() {
  local label="$1" cmd="$2"
  local bo brc po prc
  bo=$(bash -c "$cmd" 2>&1); brc=$?
  po=$($PSH -c "$cmd" 2>&1); prc=$?
  echo "=== $label"
  echo "  cmd : $cmd"
  echo "  bash: rc=$brc out=[$bo]"
  echo "  psh : rc=$prc out=[$po]"
  if [ "$bo" = "$po" ] && [ "$brc" = "$prc" ]; then echo "  MATCH"; else echo "  DIVERGE"; fi
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
probe "HIGH10c7-empty-arith-subscript" 'a=(x y); unset "a[]"; echo rc=$?; echo done'
