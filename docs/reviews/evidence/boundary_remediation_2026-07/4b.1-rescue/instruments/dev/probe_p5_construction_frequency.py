#!/usr/bin/env python3
"""P5 — MACRO: how often does a real workload actually build a VariableLookup?

P3 measures the cost of ONE construction. That figure only matters multiplied
by the construction COUNT on real work. The module docstring asserts
"lookup() sits on the shell's hottest read path"; scope.py:343 says
get_variable deliberately "skips building a VariableLookup". This instrument
counts both, per workload, so the perf ruling is decided by the PRODUCT, not
by the micro figure alone.

Counts, per workload script:
  - ScopeManager.lookup()      calls  (each builds a VariableLookup, except
                                       MISSING which returns the singleton)
  - ScopeManager.get_variable() calls (the string path — builds NOTHING)
  - _resolve_read()             calls (the shared walk, the real hot path)

Workloads deliberately span the axis that matters: variable-read-heavy work
with NO set-ness operators (where lookup should be absent), set-ness-operator
work (lookup's ONE production caller), and mixed realistic scripting.

Run from the worktree root with PYTHONPATH set to it (the parent does this).
"""
from __future__ import annotations

import os
import subprocess
import sys

WORKTREE = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))

WORKLOADS = {
    "W1 variable-read heavy (no set-ness ops)": r'''
        x=hello; y=world; n=0
        i=0
        while [ $i -lt 2000 ]; do
            s="$x-$y-$i"
            n=$(( n + ${#s} ))
            i=$(( i + 1 ))
        done
        echo "$n"
    ''',
    "W2 set-ness operators ${x+w}/${x-w} heavy": r'''
        set -- a b c
        i=0; hits=0
        while [ $i -lt 2000 ]; do
            v="${UNSET_ONE+one}${UNSET_TWO-two}"
            w="${x+set}"
            i=$(( i + 1 ))
        done
        echo "done"
    ''',
    "W3 arrays + params + functions (mixed realistic)": r'''
        declare -a arr=(a b c d e)
        f() { local acc=""; for e in "${arr[@]}"; do acc="$acc$e"; done; echo "$acc"; }
        i=0
        while [ $i -lt 500 ]; do
            r=$(f)
            case "$r" in abcde) : ;; *) echo BAD ;; esac
            i=$(( i + 1 ))
        done
        echo "$r"
    ''',
    "W4 nameref + export + readonly churn": r'''
        target=t0
        declare -n ref=target
        export EX=e0
        readonly RO=r0
        i=0
        while [ $i -lt 500 ]; do
            target="t$i"
            v="$ref$EX$RO"
            i=$(( i + 1 ))
        done
        echo "$v"
    ''',
}


def run_counted(script: str) -> dict[str, int]:
    """Count the three read entry points during one shell run, in-process."""
    from psh.core.scope import ScopeManager
    from psh.shell import Shell

    counts = {"lookup": 0, "get_variable": 0, "_resolve_read": 0}

    orig_lookup = ScopeManager.lookup
    orig_get = ScopeManager.get_variable
    orig_res = ScopeManager._resolve_read

    def c_lookup(self, name):
        counts["lookup"] += 1
        return orig_lookup(self, name)

    def c_get(self, name, default=None):
        counts["get_variable"] += 1
        return orig_get(self, name, default)

    def c_res(self, name):
        counts["_resolve_read"] += 1
        return orig_res(self, name)

    ScopeManager.lookup = c_lookup                 # type: ignore[method-assign]
    ScopeManager.get_variable = c_get              # type: ignore[method-assign]
    ScopeManager._resolve_read = c_res             # type: ignore[method-assign]
    try:
        sh = Shell()
        # Zero the counters AFTER startup so shell construction noise is
        # measured separately (reported as the W0 row).
        startup = dict(counts)
        for k in counts:
            counts[k] = 0
        try:
            sh.run_command(script)
        finally:
            sh.close()
        counts["_startup_lookup"] = startup["lookup"]
        counts["_startup_get_variable"] = startup["get_variable"]
        return counts
    finally:
        ScopeManager.lookup = orig_lookup          # type: ignore[method-assign]
        ScopeManager.get_variable = orig_get       # type: ignore[method-assign]
        ScopeManager._resolve_read = orig_res      # type: ignore[method-assign]


def child() -> int:
    import psh
    p = os.path.realpath(psh.__file__)
    if not p.startswith(WORKTREE + os.sep):
        raise SystemExit(f"DISCRIMINATOR FAIL: psh from {p}")
    key = sys.argv[2]
    print(f"psh from: {p}")
    c = run_counted(WORKLOADS[key])
    print(f"COUNTS {c!r}")
    return 0


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--child":
        return child()

    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WORKTREE,
                         capture_output=True, text=True).stdout.strip()
    print("P5 construction-frequency (MACRO) — does lookup() sit on the hot path?")
    print(f"SHA: {sha}   python: {sys.version.split()[0]}")
    print("=" * 86)
    env = dict(os.environ, PYTHONPATH=WORKTREE)
    rows = []
    for key in WORKLOADS:
        r = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--child", key],
            cwd=WORKTREE, capture_output=True, text=True, env=env)
        line = [ln for ln in r.stdout.splitlines() if ln.startswith("COUNTS ")]
        if not line:
            print(f"  {key}: FAILED\n    stdout={r.stdout[-800:]}\n"
                  f"    stderr={r.stderr[-800:]}")
            continue
        counts = eval(line[0][len("COUNTS "):])                # noqa: S307
        rows.append((key, counts))

    print(f"{'workload':44s} {'lookup()':>10s} {'get_variable':>13s} "
          f"{'_resolve_read':>14s} {'lookup share':>13s}")
    for key, c in rows:
        total = c["lookup"] + c["get_variable"]
        share = (c["lookup"] / total * 100) if total else 0.0
        print(f"{key:44s} {c['lookup']:10d} {c['get_variable']:13d} "
              f"{c['_resolve_read']:14d} {share:12.3f}%")
    print()
    print("Shell STARTUP (before the workload script runs), same counters:")
    for key, c in rows[:1]:
        print(f"    lookup()={c['_startup_lookup']}   "
              f"get_variable()={c['_startup_get_variable']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
