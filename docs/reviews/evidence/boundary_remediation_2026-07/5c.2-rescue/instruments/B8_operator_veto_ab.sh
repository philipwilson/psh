#!/bin/bash
# B8 — A/B byte-identity for the operator-recognizer veto rules, which are the
# only thing the seam touched. Every rule gets cells on BOTH sides of its
# boundary (vetoed and not-vetoed), because a veto tested only where it fires
# proves nothing about where it must not.
set -uo pipefail
BASE=/Users/pwilson/src/psh-r5c-2/tmp/w5c2-scratch/base-3a3e0782
NOW=/Users/pwilson/src/psh-r5c-2
export PYTHONDONTWRITEBYTECODE=1
NBSP=$' '

cases=(
  # --- extglob '!' ABORT rule: '!' before '(' with extglob on/off
  'shopt -s extglob; echo !(a)'
  'shopt -s extglob; case b in !(a)) echo m ;; esac'
  'shopt -u extglob; echo x'
  '! false; echo rc=$?'
  '! true; echo rc=$?'
  # --- standalone '!' SKIP rule: delimiter vs not
  'echo !!'
  'echo !x'
  'echo a!b'
  '!  true; echo rc=$?'
  "echo !${NBSP}false"
  # --- '{}' is a word, not LBRACE+RBRACE
  'echo {}'
  'echo a{}b'
  'find_stub() { echo "$@"; }; find_stub {} \;'
  # --- '}' is RBRACE only at command position
  'echo }'
  'echo a}'
  '{ echo grouped; }'
  '{ echo x; }; echo after'
  # --- '{' opens a brace group only before shell whitespace/operator
  'echo {[ab]}'
  'echo {a,b}'
  '{ echo ws; }'
  "echo {${NBSP}echo"
  '{(echo sub);}'
  '{|'
  # --- neighbours that must be unaffected
  'echo a && echo b'
  'echo a || echo b'
  'echo a; echo b'
  'echo a | cat'
  'echo x > /dev/null; echo rc=$?'
  'echo x 2>&1'
  'true && { echo brace; }'
  '[[ a == a ]] && echo m'
  'i=0; ((i++)); echo $i'
)

fail=0
for c in "${cases[@]}"; do
    a=$(cd "$BASE" && python -m psh -c "$c" 2>&1); arc=$?
    b=$(cd "$NOW"  && python -m psh -c "$c" 2>&1); brc=$?
    if [ "$a" != "$b" ] || [ "$arc" != "$brc" ]; then
        fail=1
        echo "  *** DIVERGED  $c"
        echo "      base: rc=$arc [$a]"
        echo "      now : rc=$brc [$b]"
    fi
done
echo "cases compared: ${#cases[@]}"
if [ "$fail" -eq 0 ]; then
    echo "VERDICT: byte-identical on all ${#cases[@]} cases (stdout+stderr+rc)"
else
    echo "VERDICT: DIVERGENCE — zero-delta claim broken"
fi
exit $fail
