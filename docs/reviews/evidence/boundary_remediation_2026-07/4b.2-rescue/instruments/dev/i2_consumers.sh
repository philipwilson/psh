#!/opt/homebrew/bin/bash
# i2 — static census of InputCursor construction sites and public-method call
# sites tree-wide, to enumerate which consumers can share a cursor object.
# --include always precedes -e (see i1's note); each grep's exit is printed.
set -u
cd "$(dirname "$0")/../.." || exit 1
echo "== DISCRIMINATOR =="
echo "cwd:  $PWD"
echo "HEAD: $(git rev-parse HEAD)"
echo "tree-dirty(psh/): $(git status --porcelain psh/ | wc -l | tr -d ' ')"
echo

fail=0
section() {  # section <title> <pattern> <path...>
  local title="$1"; shift
  local pat="$1"; shift
  echo "== ${title} =="
  grep -rnE --include='*.py' -e "${pat}" "$@"
  local rc=$?
  echo "-- exit: ${rc} (0=hits, 1=none, 2=ERROR) --"
  [ "${rc}" -gt 1 ] && fail=1
  echo
}

section "InputCursor CONSTRUCTION sites (production)" 'InputCursor\(' psh/
section "registry mediation: cursor_for_fd / make_reader (production)" \
        'cursor_for_fd|make_reader' psh/
section "public-method CALL sites (production, all files incl. input_reader.py)" \
        '\.(read_all|read_limited|read_record|read_record_bytes|poll_readable)\(' psh/
section "read_all NAME sweep (any syntactic form) over psh/ — collision check" \
        'read_all' psh/
section "input_cursors registry references (production)" 'input_cursors' psh/
section "InputCursor NAME sweep over tests/ (which suites touch the cursor)" \
        'InputCursor' tests/

echo "== INSTRUMENT SELF-CHECK: any grep errored? ${fail} (0=no) =="
exit "${fail}"
