#!/usr/bin/env python3
"""atk-c p05: Gap 6 — reconcile tests/harness/oracle_migration_census.md (frozen
at e52957d4/v0.751.0) against the tree at ae871a16.

Checks:
 A. The census table's migration-target module list: count (doc claims 95
    targets = 92 migrated + 3 allowlisted) and per-directory split
    (conformance 36, integration 35, system 12, unit 12).
 B. Existence at tip: every listed module still exists (or its absence noted).
 C. Spot-check 5 MIGRATED modules (one per top dir + 1): each imports
    shell_oracle AND contains zero raw spawns
    (subprocess.run/Popen/call/check_output/check_call, os.system, os.popen,
    pexpect, pty.fork, os.fork) by AST+text scan.
Run from the worktree root.
"""
import ast
import os
import re
import sys

WT = os.getcwd()
CENSUS = os.path.join(WT, "tests/harness/oracle_migration_census.md")

text = open(CENSUS, encoding="utf-8").read()

# A: parse the migration-target table rows: "| tests/... | CLASS | n | kinds |"
rows = re.findall(r"^\| (tests/\S+\.py) \| ([A-Z-]+) \| (\d+) \|", text, re.M)
mods = [r[0] for r in rows]
print(f"A. table rows parsed: {len(rows)}")
from collections import Counter
def topdir(m):
    return m.split("/")[1]
print(f"   per-dir split: {dict(Counter(topdir(m) for m in mods))}")
print(f"   unique modules: {len(set(mods))}")
spawn_total = sum(int(r[2]) for r in rows)
print(f"   spawn-site total in table: {spawn_total} (doc claims 243)")

# The 3 allowlisted targets (named in the doc)
ALLOWLISTED = {
    "tests/integration/job_control/test_exit_trap_paths.py",
    "tests/system/test_script_input_sources.py",
    "tests/system/test_stdin_startup_robustness.py",
}
# resolve allowlisted names by basename against the table
allow_in_table = [m for m in mods if os.path.basename(m) in {os.path.basename(a) for a in ALLOWLISTED}]
print(f"   allowlisted targets found in table: {allow_in_table}")

# B: existence at tip
missing = [m for m in mods if not os.path.isfile(os.path.join(WT, m))]
print(f"B. modules from table missing at ae871a16: {len(missing)}")
for m in missing:
    print(f"   MISSING: {m}")

# C: spot-check 5 migrated modules (deterministic pick: first table row per
# top dir in conformance/integration/system/unit + the ruled special case)
SPOT = []
seen_dirs = set()
allow_basenames = {os.path.basename(a) for a in ALLOWLISTED}
for m in mods:
    d = topdir(m)
    if d not in seen_dirs and os.path.basename(m) not in allow_basenames:
        SPOT.append(m)
        seen_dirs.add(d)
SPOT.append("tests/system/test_read_malformed_bytes_i1.py")  # ruled special case
SPOT = SPOT[:5] if len(SPOT) > 5 else SPOT

RAW_RE = re.compile(
    r"subprocess\.(run|Popen|call|check_output|check_call)|os\.system|os\.popen"
    r"|pexpect|pty\.fork|os\.fork|posix_spawn")

print("C. spot-check (migrated => imports shell_oracle, zero raw spawns):")
for m in SPOT:
    p = os.path.join(WT, m)
    if not os.path.isfile(p):
        print(f"   {m}: MISSING")
        continue
    src = open(p, encoding="utf-8").read()
    tree = ast.parse(src)
    imports_oracle = any(
        (isinstance(n, ast.ImportFrom) and n.module and "shell_oracle" in n.module)
        or (isinstance(n, ast.Import) and any("shell_oracle" in a.name for a in n.names))
        for n in ast.walk(tree))
    raw_hits = []
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.split("#", 1)[0]
        if RAW_RE.search(stripped):
            raw_hits.append((i, line.strip()))
    verdict = "OK" if imports_oracle and not raw_hits else "CHECK"
    print(f"   {m}: imports_shell_oracle={imports_oracle} raw_spawn_hits={len(raw_hits)} -> {verdict}")
    for ln, l in raw_hits:
        print(f"      :{ln}: {l}")
