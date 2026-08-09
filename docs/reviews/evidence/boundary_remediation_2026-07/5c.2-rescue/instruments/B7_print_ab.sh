#!/bin/bash
# B7 — A/B byte-identity for `print` option parsing, concentrating on the two
# arms the seam touched (-u and -f, attached AND separate operand forms) plus
# the clusters, terminators and -R mid-walk rewrite around them.
set -uo pipefail
BASE=/Users/pwilson/src/psh-r5c-2/tmp/w5c2-scratch/base-3a3e0782
NOW=/Users/pwilson/src/psh-r5c-2
export PYTHONDONTWRITEBYTECODE=1

cases=(
  'print hello'
  'print -n hello'
  'print -r "a\tb"'
  'print -e "a\tb"'
  'print -l a b c'
  'print -N a b c'
  # -u: attached and separate, valid and invalid
  'print -u1 hello'
  'print -u 1 hello'
  'print -u2 hello'
  'print -u 2 hello'
  'print -u99 hello'
  'print -u 99 hello'
  'print -ux hello'
  'print -u x hello'
  'print -u'
  'print -nu1 hello'
  'print -u1'
  # -f: attached and separate, valid and invalid
  'print -f"%s\n" hi'
  'print -f "%s\n" hi'
  'print -f"%d" 42'
  'print -f "%d" 42'
  'print -f'
  'print -f "%s" a b c'
  'print -nf "%s" x'
  # clusters mixing an operand-taking flag with others
  'print -rnu1 hello'
  'print -lu2 a b'
  # -R rewrites the option set mid-walk
  'print -R hello'
  'print -R -n hello'
  'print -R -l hello'
  'print -Rn hello'
  # terminators
  'print -- -n'
  'print - -n'
  'print --'
  'print -'
  # unsupported / invalid
  'print -z hi'
  'print -q hi'
  'print -s hi'
  'print'
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
