#!/opt/homebrew/bin/bash
# Wave 0 baseline legs — Boundary Remediation Campaign
# Runs SEQUENTIALLY at the launch base in this neutral detached worktree.
# Declared shuffle seeds: 101, 202, 303 (identical phase censuses required).
set -u
cd /Users/pwilson/src/psh-wave0-legs || exit 1
OUT=tmp/wave0-legs
mkdir -p "$OUT"

{
  echo "campaign: boundary_remediation_2026-07 wave0 baseline"
  echo "sha: $(git rev-parse HEAD)"
  echo "date: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "host: $(uname -a)"
  python --version 2>&1
  bash --version | head -1
  echo "PATH bash: $(which bash)"
  ruff --version 2>&1
  python -m mypy --version 2>&1
  echo "seeds: 101 202 303"
  echo "note: shared interactive host; light doc-authoring ran concurrently (benchmarks leg context)"
} > "$OUT/context.txt"

run_leg() {
  local name=$1; shift
  echo "=== $name START $(date '+%H:%M:%S')"
  "$@" > "$OUT/$name.txt" 2>&1
  local rc=$?
  echo "leg-rc=$rc" >> "$OUT/$name.txt"
  echo "=== $name DONE rc=$rc $(date '+%H:%M:%S')"
}

run_leg ruff ruff check psh tests tools
run_leg mypy python -m mypy
run_leg gate-seed101 python -u run_tests.py --parallel --shuffle-seed 101 < /dev/null
run_leg gate-seed202 python -u run_tests.py --parallel --shuffle-seed 202 < /dev/null
run_leg gate-seed303 python -u run_tests.py --parallel --shuffle-seed 303 < /dev/null
run_leg conformance python -m pytest tests/conformance -q
run_leg compare-bash python -m pytest tests/behavioral --compare-bash -n auto -q
run_leg benchmarks python -u run_tests.py --benchmarks < /dev/null

python - > "$OUT/complexity.txt" 2>&1 <<'EOF'
import ast, pathlib
n100 = 0; total = 0; incomplete = 0; files = 0; loc = 0
biggest = []
for f in pathlib.Path('psh').rglob('*.py'):
    files += 1
    text = f.read_text()
    loc += text.count('\n')
    t = ast.parse(text)
    for node in ast.walk(t):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total += 1
            span = (node.end_lineno or node.lineno) - node.lineno + 1
            if span >= 100:
                n100 += 1
                biggest.append((span, f.as_posix(), node.name))
            a = node.args
            allargs = a.posonlyargs + a.args + a.kwonlyargs
            unann = any(x.annotation is None and x.arg not in ('self','cls') for x in allargs)
            if unann or (node.returns is None and node.name != '__init__'):
                incomplete += 1
print(f"files={files} loc={loc}")
print(f"functions_total={total}")
print(f"functions_ge_100_lines={n100}")
print(f"incomplete_annotation_functions(methodology: any unannotated param excl self/cls, or missing return excl __init__)={incomplete}")
for span, path, name in sorted(biggest, reverse=True)[:10]:
    print(f"  {span:4d}  {path}#{name}")
EOF
echo "=== complexity DONE"

echo "ALL-LEGS-DONE $(date '+%H:%M:%S')"
