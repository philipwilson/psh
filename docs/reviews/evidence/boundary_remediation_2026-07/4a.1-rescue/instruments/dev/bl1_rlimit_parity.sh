#!/opt/homebrew/bin/bash
# BL-1 reproduction: does a REAL psh shell keep bash parity for a permanent
# redirect under a low RLIMIT_NOFILE?
#
# Explicit argv everywhere (the zsh unquoted-$var trap). Oracle is PATH bash
# = /opt/homebrew/bin/bash; version recorded below.
#
#   ./bl1_rlimit_parity.sh <tree-under-test>
set -u
TREE="${1:?usage: bl1_rlimit_parity.sh <tree>}"
PY=/Library/Frameworks/Python.framework/Versions/3.14/bin/python
echo "oracle bash: $(/opt/homebrew/bin/bash --version | head -1)"
echo "tree:        $TREE"
echo "tip:         $(git -C "$TREE" rev-parse --short HEAD 2>/dev/null || echo n/a)"
echo

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

printf '%-8s %-28s %-28s %s\n' LIMIT "psh(after,rc)" "bash(after,rc)" PARITY
for LIMIT in 24 40 50 63 64 70 256; do
  # Same script for both shells: a permanent redirect, then observe whether
  # the shell survived it.
  SCRIPT="exec 3> $TMP/out.txt; echo after=\$?"

  P=$( ( ulimit -n "$LIMIT" 2>/dev/null || exit 99
         cd "$TREE" && PYTHONPATH="$TREE" "$PY" -m psh --norc -c "$SCRIPT" ) 2>&1 )
  PRC=$?
  B=$( ( ulimit -n "$LIMIT" 2>/dev/null || exit 99
         /opt/homebrew/bin/bash --norc -c "$SCRIPT" ) 2>&1 )
  BRC=$?

  # Normalise whitespace for the comparison line.
  PN=$(echo "$P" | tr '\n' '|')
  BN=$(echo "$B" | tr '\n' '|')
  if [ "$PN" = "$BN" ] && [ "$PRC" = "$BRC" ]; then VERDICT=MATCH; else VERDICT="**DIVERGE**"; fi
  printf '%-8s %-28s %-28s %s\n' "$LIMIT" "$PN($PRC)" "$BN($BRC)" "$VERDICT"
done
