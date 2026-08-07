#!/opt/homebrew/bin/bash
# i9 — doc-sweep ENUMERATION for slot 4B.2 (pre-registration input).
#
# Rule being honored (4B.1 lesson 2): a doc sweep for a removed/renamed/false
# claim searches the NAME and the CLAIM'S TERMS, not one syntactic form. So this
# sweeps the whole tree for each concept term independently, over docs, CLAUDE.md
# files, user guide and source comments alike — not just the one docstring I
# already know about.
set -u
cd "$(dirname "$0")/../.." || exit 1
echo "== DISCRIMINATOR =="
echo "cwd:  $PWD"
echo "HEAD: $(git rev-parse HEAD)"
echo "tree-dirty: $(git status --porcelain | grep -cv INTEGRATOR-INBOX)"
echo

fail=0
sweep() {  # sweep <title> <extended-regex> [paths...]
  local title="$1"; shift
  local pat="$1"; shift
  echo "== ${title} =="
  echo "   pattern: ${pat}"
  grep -rniE -e "${pat}" "$@" \
      --include='*.py' --include='*.md' --include='*.rst' --include='*.txt' \
      --include='*.yaml' 2>/dev/null
  local rc=$?
  echo "-- exit: ${rc} (0=hits, 1=none, 2=ERROR) --"
  [ "${rc}" -gt 1 ] && fail=1
  echo
}

TREE=(psh docs README.md CHANGELOG.md ARCHITECTURE.md tests)

sweep "T1 the FALSE claim's own words ('multibyte-boundary concern')" \
      'multibyte.boundary|boundary concern' "${TREE[@]}"
sweep "T2 'decoded at once' / 'whole byte run' bulk-drain claims" \
      'decoded at once|whole byte run|reads to EOF' "${TREE[@]}"
sweep "T3 every mention of read_all (NAME, any form)" \
      'read_all' "${TREE[@]}"
sweep "T4 incremental-decoder invariant prose (the thing the fix changes)" \
      'incremental (utf-8 )?decod|one incremental|ONE incremental' "${TREE[@]}"
sweep "T5 surrogateescape policy statements" \
      'surrogateescape' "${TREE[@]}"
sweep "T6 read -N / -t documentation claims (the rider's doc surface)" \
      'read -N|read -t|exact_chars|-N count' docs psh/builtins/CLAUDE.md \
      psh/io_redirect/CLAUDE.md
sweep "T7 subsystem CLAUDE.md pointers into input_reader/read/mapfile" \
      'input_reader|InputCursor|read_builtin|mapfile' psh/builtins/CLAUDE.md \
      psh/io_redirect/CLAUDE.md psh/core/CLAUDE.md psh/interactive/CLAUDE.md \
      ARCHITECTURE.md
sweep "T8 doc drift-lock registries that might pin these lines" \
      'input_reader|read_all|InputCursor' tests/unit/tooling

echo "== INSTRUMENT SELF-CHECK: any grep errored? ${fail} (0=no) =="
exit "${fail}"
