#!/usr/bin/env python3
"""P7/P8/P9 — the three design facts the binding policy turns on.

P7  lookup() x dynamic-special registry: is .binding a LIVE store cell for a
    computed special, or a freshly built throwaway? (The brief's composition
    cell "frozen-lookup x computed-special read — check how lookup() composes
    with the special registry BEFORE assuming".)

P8  Scope boundary: which ScopeManager/VariableStore returns hand out LIVE
    Variable cells (the write engine's own sanctioned surface, NOT this slot)
    vs the public read contract being frozen. Derived by RUNTIME IDENTITY
    (`is` against the cell in the scope dict), not by reading docstrings.

P9  Array aliasing: if ruling (b) picks an immutable SNAPSHOT, does copying
    the scalar fields actually snapshot anything? Arrays are mutable objects;
    a snapshot that aliases the live IndexedArray is not a snapshot.

Each section runs in its own subprocess.
"""
from __future__ import annotations

import os
import subprocess
import sys

WORKTREE = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def disc() -> str:
    import psh
    p = os.path.realpath(psh.__file__)
    if not p.startswith(WORKTREE + os.sep):
        raise SystemExit(f"DISCRIMINATOR FAIL: psh from {p}")
    return p


# ------------------------------------------------------------------- P7
def p7_specials() -> None:
    from psh.core.scope import ScopeManager
    from psh.shell import Shell

    sh = Shell()
    try:
        sm = sh.state.scope_manager
        print("  Is each name a computed special?")
        for name in ('RANDOM', 'SECONDS', 'LINENO', 'PLAINVAR'):
            print(f"    {name:10s} is_computed={sm._special.is_computed(name)}")

        sh.run_command('PLAINVAR=p')
        print("\n  Does lookup() reach the special registry, and is .binding live?")
        for name in ('RANDOM', 'SECONDS', 'PLAINVAR'):
            r1 = sm.lookup(name)
            r2 = sm.lookup(name)
            b1, b2 = r1.binding, r2.binding
            same = (b1 is b2) if (b1 is not None and b2 is not None) else None
            print(f"    {name:10s} status={r1.status.name:13s} "
                  f"binding={'None' if b1 is None else type(b1).__name__:8s} "
                  f"two reads share the cell? {same}")

        print("\n  Mutating a SPECIAL's binding — does anything observe it?")
        r = sm.lookup('SECONDS')
        before = sm.get_variable('SECONDS')
        try:
            r.binding.value = '999999'
            note = "SUCCEEDED"
        except Exception as exc:                               # noqa: BLE001
            note = f"raised {type(exc).__name__}"
        after = sm.get_variable('SECONDS')
        print(f"    attempt: {note};  SECONDS before={before!r} after={after!r}")
        print(f"    -> the special's binding is a THROWAWAY: "
              f"{note == 'SUCCEEDED' and after != '999999'}")

        print("\n  Local shadowing a special (bash: the local wins):")
        sh.run_command('f() { local RANDOM=5; echo "$RANDOM"; }; f')
        _ = ScopeManager
    finally:
        sh.close()


# ------------------------------------------------------------------- P8
def p8_boundary() -> None:
    from psh.shell import Shell

    sh = Shell()
    try:
        sm = sh.state.scope_manager
        sh.run_command('X=v')
        # The authoritative cell: the one actually stored in the scope dict.
        stored = None
        for scope in reversed(sm.scope_stack):
            if 'X' in scope.variables:
                stored = scope.variables['X']
                break
        print(f"  stored cell in scope dict: {stored!r}")
        print("\n  Which returns hand out THAT LIVE cell (identity test)?")
        checks = [
            ("ScopeManager.get_variable_object('X')",
             sm.get_variable_object('X')),
            ("ScopeManager.get_declared_variable_object('X')",
             sm.get_declared_variable_object('X')),
            ("ScopeManager.lookup('X').binding",
             sm.lookup('X').binding),
            ("VariableStore.get_variable_object('X')",
             sm.store.get_variable_object('X')),
        ]
        allvars = sm.all_variables_with_attributes()
        x_in_all = next((v for v in allvars if getattr(v, 'name', None) == 'X'),
                        None)
        checks.append(("ScopeManager.all_variables_with_attributes() -> X",
                       x_in_all))
        for label, got in checks:
            print(f"    {label:48s} is the live cell? {got is stored}")

        print("\n  And the string projection returns no cell at all:")
        print(f"    ScopeManager.get_variable('X') -> {sm.get_variable('X')!r} "
              f"({type(sm.get_variable('X')).__name__})")
    finally:
        sh.close()


# ------------------------------------------------------------------- P9
def p9_array_aliasing() -> None:
    from psh.core.variables import AssociativeArray, IndexedArray
    from psh.shell import Shell

    sh = Shell()
    try:
        sm = sh.state.scope_manager
        sh.run_command('declare -a arr=(a b c)')
        sh.run_command('declare -A m=([k]=v)')
        for name in ('arr', 'm'):
            r = sm.lookup(name)
            b = r.binding
            val = b.value if b is not None else None
            print(f"  {name}: binding.value is {type(val).__name__} "
                  f"(mutable object: "
                  f"{isinstance(val, (IndexedArray, AssociativeArray))})")

        print("\n  A 'snapshot' that copies only the SCALAR fields still aliases:")
        r = sm.lookup('arr')
        live_array = r.binding.value
        # simulate a naive snapshot: copy name/value/attributes references
        class NaiveSnapshot:
            def __init__(self, var):
                self.name = var.name
                self.value = var.value          # <-- SAME IndexedArray object
                self.attributes = var.attributes
        snap = NaiveSnapshot(r.binding)
        print(f"    snapshot.value is the live array object? "
              f"{snap.value is live_array}")
        snap.value.set(0, 'MUTATED_THROUGH_SNAPSHOT')
        print(f"    after snapshot.value.set(0, ...): shell reads "
              f"${{arr[0]}} = {sh.state.get_variable('arr')!r}")
        sh.run_command('echo "arr[0]=${arr[0]}"')

        print("\n  Variable.copy() DEEP-copies arrays (the honest snapshot):")
        sh.run_command('declare -a arr2=(x y z)')
        r2 = sm.lookup('arr2')
        deep = r2.binding.copy()
        print(f"    deep.value is live? {deep.value is r2.binding.value}")
        deep.value.set(0, 'ONLY_IN_COPY')
        sh.run_command('echo "arr2[0]=${arr2[0]}"')
    finally:
        sh.close()


SECTIONS = {
    'p7': ("P7 lookup() x dynamic-special registry", p7_specials),
    'p8': ("P8 scope boundary — which returns are LIVE cells", p8_boundary),
    'p9': ("P9 array aliasing under a snapshot policy", p9_array_aliasing),
}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in SECTIONS:
        title, fn = SECTIONS[sys.argv[1]]
        print(f"--- {title} ---")
        print(f"psh from: {disc()}")
        fn()
        return 0

    sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=WORKTREE,
                         capture_output=True, text=True).stdout.strip()
    print("P7/P8/P9 design facts")
    print(f"SHA: {sha}   python: {sys.version.split()[0]}")
    print("=" * 78)
    env = dict(os.environ, PYTHONPATH=WORKTREE)
    for key in SECTIONS:
        r = subprocess.run([sys.executable, os.path.abspath(__file__), key],
                           cwd=WORKTREE, capture_output=True, text=True, env=env)
        print(r.stdout, end='')
        err = r.stderr.strip()
        if err:
            print(f"  [stderr] {err[:800]}")
        print("-" * 78)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
