#!/opt/homebrew/bin/bash
# i1 — static census of every read/write site of the three cursor-lifetime
# states (_decoder, _decoded, _pushback) over psh/ and tests/.
# Substrate: the TREE (static), so the instrument is grep over the tree.
# NOTE: --include must precede -e; a `--` end-of-options marker would make
# grep treat --include as a FILE operand (exit 2). Every grep's own exit
# status is printed and checked.
set -u
cd "$(dirname "$0")/../.." || exit 1
echo "== DISCRIMINATOR =="
echo "cwd:  $PWD"
echo "HEAD: $(git rev-parse HEAD)"
echo "tree-dirty(psh/): $(git status --porcelain psh/ | wc -l | tr -d ' ')"
echo "bash: $(/opt/homebrew/bin/bash --version | head -1)"
echo

fail=0
for name in _pushback _decoder _decoded; do
  echo "== ${name} — ALL sites (psh/ and tests/, *.py only) =="
  grep -rn --include='*.py' -e "${name}" psh/ tests/
  rc=$?
  echo "-- grep exit: ${rc} (0=hits, 1=none, 2=ERROR) --"
  [ "${rc}" -gt 1 ] && fail=1
  echo "== ${name} — WRITE sites only (assignment / mutating method) =="
  grep -rnE --include='*.py' \
      -e "${name}[[:space:]]*(=[^=]|\.(clear|append|extend|popleft|pop)\()" \
      psh/ tests/
  rc=$?
  echo "-- write-site grep exit: ${rc} (0=hits, 1=none, 2=ERROR) --"
  [ "${rc}" -gt 1 ] && fail=1
  echo
done
echo "== INSTRUMENT SELF-CHECK: any grep errored? ${fail} (0=no) =="
exit "${fail}"
