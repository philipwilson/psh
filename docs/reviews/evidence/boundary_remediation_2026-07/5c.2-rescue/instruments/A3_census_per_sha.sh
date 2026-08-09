#!/bin/bash
# A3 — per-SHA attribution of the CR-tip -> base census drift.
# Materialises each Wave-5 release SHA with `git archive` into a scratch dir
# (no worktree locks, no checkout over anyone's tree) and runs the READ-ONLY
# q4_09 copy at each. Explicit argv throughout; project tmp/ only.
set -euo pipefail
REPO=/Users/pwilson/src/psh-r5c-2
INST="$REPO/tmp/w5c2-instruments"
SCRATCH="$REPO/tmp/w5c2-scratch"
export PYTHONDONTWRITEBYTECODE=1

rm -rf "$SCRATCH"
mkdir -p "$SCRATCH"

# label:sha  — CR tip, then each Wave-5 release tag commit, then base
for pair in \
  "CRtip-ae871a16:ae871a16" \
  "v0774-2cf9493b:2cf9493b" \
  "v0775-1cddebb5:1cddebb5" \
  "v0776-d8166242:d8166242" \
  "v0777-67261b29:67261b29" \
  "base-3a3e0782:3a3e0782" ; do
    label="${pair%%:*}"
    sha="${pair##*:}"
    d="$SCRATCH/$label"
    mkdir -p "$d"
    git -C "$REPO" archive "$sha" | tar -x -C "$d"
    # discriminator: the materialised tree really is that SHA's psh/version.py
    ver=$(grep -E '^__version__' "$d/psh/version.py")
    echo "### $label ($sha) $ver"
    python "$INST/A1_fn_length_census_COPY.py" "$d" "$label" \
        --json "$INST/A3_census_$label.json" | head -1
done

echo
echo "=== drift of the four changed >=100 rows + the two publish fns, per SHA ==="
python - "$INST" <<'PY'
import json, sys, pathlib
inst = pathlib.Path(sys.argv[1])
labels = ["CRtip-ae871a16","v0774-2cf9493b","v0775-1cddebb5",
          "v0776-d8166242","v0777-67261b29","base-3a3e0782"]
docs = {l: json.loads((inst/f"A3_census_{l}.json").read_text()) for l in labels}
watch = [
 ("psh/builtins/read_builtin.py","ReadBuiltin.execute"),
 ("psh/builtins/parse_tree.py","ParseTreeBuiltin.execute"),
 ("psh/parser/combinators/commands/simple.py","SimpleCommandMixin._build_simple_command_parser"),
 ("psh/executor/job_control.py","JobManager.publish_foreground_pgid"),
]
for l in labels:
    idx = {(r["file"], r["fn"]): r["len"] for r in docs[l]["all"]}
    cells = "  ".join(f"{q.split('.')[-1]}={idx.get(k,'-')}" for k in watch for q in [k[1]])
    print(f"{l:22s} total={docs[l]['total_functions']:5d} ge100={docs[l]['ge100_count']:3d}  {cells}")
PY
