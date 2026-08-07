#!/usr/bin/env python3
"""P1 — MEDIUM-5 reproduction at slot 4B.1's own base.

Re-derives the integrator's brief-time evidence independently (I do not read
their probe file; this is written from the defect description + the source).

Four legs, EACH IN ITS OWN SUBPROCESS (the poisoning leg mutates a module
singleton irreversibly — sharing a process across legs would contaminate them):

  L1 _MISSING poisoning       — mutate a miss result, observe an UNRELATED
                                name read the poison, end-to-end via ${u+w}
  L2 readonly bypass          — lookup('RO').binding.value = ... beats the
                                readonly guard that the normal path enforces
  L3 observer/export desync   — binding write updates the shell read but not
                                state.env (the variable_changed observer that
                                drives _materialize_env_name never fires)
  L4 nameref target mutation  — lookup() derefs to the FINAL cell, so a
                                binding write mutates the TARGET with none of
                                resolve_nameref_name's write guards

Run:  python tmp/4b1-instruments/probe_p1_medium5_repro.py
      (parent spawns itself per leg; prints a verdict table)
"""
from __future__ import annotations

import os
import subprocess
import sys

WORKTREE = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def discriminate() -> str:
    """Prove we imported THIS worktree's psh, not an editable-install MAIN."""
    import psh
    path = os.path.realpath(psh.__file__)
    if not path.startswith(WORKTREE + os.sep):
        raise SystemExit(
            f"DISCRIMINATOR FAIL: imported psh from {path}, expected under {WORKTREE}"
        )
    return path


# --------------------------------------------------------------------------
# Legs
# --------------------------------------------------------------------------

def leg1_missing_poisoning() -> None:
    """The shared _MISSING singleton is mutable and reachable from lookup()."""
    from psh.core.scope import ScopeManager
    from psh.core.variable_lookup import LookupStatus
    from psh.shell import Shell

    mgr = ScopeManager()
    miss = mgr.lookup('unset_a')
    print(f"  lookup('unset_a').status              = {miss.status.name}")
    print(f"  is the shared singleton?              = "
          f"{miss is mgr.lookup('unset_b')}")

    # The attack: plain attribute assignment on the returned object.
    try:
        miss.status = LookupStatus.VALUE
        miss.value = 'POISON'
        mutated = True
    except Exception as exc:                                  # noqa: BLE001
        mutated = False
        print(f"  mutation raised: {type(exc).__name__}: {exc}")
    print(f"  plain attribute assignment SUCCEEDED  = {mutated}")

    # Consequence 1: a DIFFERENT, unrelated unset name now reads the poison.
    other = mgr.lookup('SOME_OTHER_UNSET')
    print(f"  lookup('SOME_OTHER_UNSET').status     = {other.status.name}")
    print(f"  lookup('SOME_OTHER_UNSET').value      = {other.value!r}")
    print(f"  ...is_set (the ${{x+w}} authority)      = {other.is_set}")

    # Consequence 2: end-to-end through a real shell in the same process.
    sh = Shell()
    try:
        rc = sh.run_command('echo "${SOME_UNSET_NAME+FIRED}"')
        print(f"  end-to-end: echo \"${{SOME_UNSET_NAME+FIRED}}\" rc={rc}")
    finally:
        sh.close()

    print(f"  VERDICT L1 poisoning reproduces       = {mutated and other.is_set}")


def leg2_readonly_bypass() -> None:
    """readonly is enforced on the write path and bypassed via .binding."""
    from psh.shell import Shell

    sh = Shell()
    try:
        sh.run_command('readonly RO=original')
        rc = sh.run_command('RO=viaShell')
        print(f"  normal write path `RO=viaShell` rc    = {rc} (1 == refused)")
        print(f"  value after refused write             = "
              f"{sh.state.get_variable('RO')!r}")

        look = sh.state.scope_manager.lookup('RO')
        print(f"  lookup('RO').binding is a live cell   = "
              f"{look.binding is not None}")
        try:
            look.binding.value = 'hacked'
            mutated = True
            raised = None
        except Exception as exc:                              # noqa: BLE001
            mutated, raised = False, f"{type(exc).__name__}: {exc}"
        print(f"  binding.value = 'hacked' SUCCEEDED    = {mutated}"
              + (f"  (raised {raised})" if raised else ""))

        after = sh.state.get_variable('RO')
        print(f"  shell now reads RO                    = {after!r}")
        print(f"  VERDICT L2 readonly bypassed          = "
              f"{mutated and after == 'hacked'}")
    finally:
        sh.close()


def leg3_observer_export_desync() -> None:
    """A binding write updates the shell read but never fires the observer,
    so state.env (what children inherit) goes stale."""
    from psh.shell import Shell

    sh = Shell()
    try:
        sh.run_command('export EX=one')
        print(f"  after `export EX=one`: shell reads    = "
              f"{sh.state.get_variable('EX')!r}")
        print(f"  ...state.env['EX']                    = "
              f"{sh.state.env.get('EX')!r}")

        look = sh.state.scope_manager.lookup('EX')
        try:
            look.binding.value = 'two'
            mutated = True
        except Exception as exc:                              # noqa: BLE001
            mutated = False
            print(f"  mutation raised: {type(exc).__name__}: {exc}")

        shell_read = sh.state.get_variable('EX')
        env_read = sh.state.env.get('EX')
        print(f"  after binding write: shell reads      = {shell_read!r}")
        print(f"  ...state.env['EX'] (children see this)= {env_read!r}")
        print(f"  VERDICT L3 export desync              = "
              f"{mutated and shell_read != env_read}")
    finally:
        sh.close()


def leg4_nameref_target_mutation() -> None:
    """lookup() derefs to the FINAL cell: a binding write hits the TARGET
    with none of the nameref write path's guards."""
    from psh.shell import Shell

    sh = Shell()
    try:
        sh.run_command('target=hi')
        sh.run_command('declare -n ref=target')
        look = sh.state.scope_manager.lookup('ref')
        binding_name = look.binding.name if look.binding is not None else None
        print(f"  lookup('ref').value                   = {look.value!r}")
        print(f"  lookup('ref').binding.name            = {binding_name!r}"
              f"   (deref'd to the TARGET, not the ref)")
        try:
            look.binding.value = 'clobbered'
            mutated = True
        except Exception as exc:                              # noqa: BLE001
            mutated = False
            print(f"  mutation raised: {type(exc).__name__}: {exc}")
        tgt = sh.state.get_variable('target')
        via_ref = sh.state.get_variable('ref')
        print(f"  target now reads                      = {tgt!r}")
        print(f"  ref now reads                         = {via_ref!r}")
        print(f"  VERDICT L4 nameref target mutated     = "
              f"{mutated and tgt == 'clobbered'}")
    finally:
        sh.close()


LEGS = {
    'L1': ('_MISSING poisoning', leg1_missing_poisoning),
    'L2': ('readonly bypass', leg2_readonly_bypass),
    'L3': ('observer/export desync', leg3_observer_export_desync),
    'L4': ('nameref target mutation', leg4_nameref_target_mutation),
}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in LEGS:
        key = sys.argv[1]
        title, fn = LEGS[key]
        print(f"psh imported from: {discriminate()}")
        print(f"--- {key}: {title} ---")
        fn()
        return 0

    # Parent: run each leg in a FRESH subprocess.
    sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=WORKTREE,
                         capture_output=True, text=True).stdout.strip()
    print(f"P1 MEDIUM-5 reproduction — worktree {WORKTREE}")
    print(f"SHA: {sha}")
    print(f"python: {sys.version.split()[0]}")
    print("=" * 74)
    # The editable install resolves `import psh` to the MAIN checkout; sys.path[0]
    # is this script's dir, not the worktree root. PYTHONPATH puts THIS tree
    # first — the discriminator in each child proves it took.
    env = dict(os.environ, PYTHONPATH=WORKTREE)
    for key in LEGS:
        r = subprocess.run([sys.executable, os.path.abspath(__file__), key],
                           cwd=WORKTREE, capture_output=True, text=True, env=env)
        print(r.stdout, end='')
        if r.stderr.strip():
            print("  [stderr]", r.stderr.strip()[:2000])
        print("-" * 74)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
