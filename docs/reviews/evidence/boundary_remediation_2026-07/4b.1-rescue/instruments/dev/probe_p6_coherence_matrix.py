#!/usr/bin/env python3
"""P6 — the coherence matrix: the exit criterion's FOUR authorities.

Axis: MUTATION SURFACE x AUTHORITY GUARD (the new axis this slot contributes).

For each authority (readonly / nameref / observer / export) two cells:
  (M) MUTATION-ATTEMPT cell — what plain attribute assignment through the
      lookup result does to the authority's guarantee. At BASE this is the
      defect (assignment succeeds, guarantee broken) => the pin is RED-ON-BASE.
      At TIP the same cell must RAISE.
  (C) COHERENCE cell — the authority's guarantee still holds through the
      LEGITIMATE path (VariableStore by identifier). Must be green at BOTH
      ends: this slot must not weaken the write engine.

Mutation surfaces varied per cell: .status / .value / .binding on the lookup
result, and .value / .attributes on the binding it hands out.

Each cell runs in its OWN subprocess: several of them poison process-global
state (the _MISSING singleton) or leave a shell mid-transaction.
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


def _attempt(fn):
    """Run a mutation attempt; return (succeeded, description)."""
    try:
        fn()
        return True, "SUCCEEDED (no exception)"
    except Exception as exc:                                   # noqa: BLE001
        return False, f"raised {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------- readonly
def readonly_M():
    """Mutation attempt vs the readonly guard."""
    from psh.shell import Shell
    sh = Shell()
    try:
        sh.run_command('readonly RO=original')
        look = sh.state.scope_manager.lookup('RO')
        ok, how = _attempt(lambda: setattr(look.binding, 'value', 'hacked'))
        print(f"    surface .binding.value : {how}")
        print(f"    shell reads RO         : {sh.state.get_variable('RO')!r}")
        print(f"    GUARANTEE HELD         : {sh.state.get_variable('RO') == 'original'}")
    finally:
        sh.close()


def readonly_C():
    """Legitimate path still refuses a readonly write, with the right error."""
    from psh.core.variables import VarAttributes
    from psh.shell import Shell
    sh = Shell()
    try:
        sh.run_command('readonly RO=original')
        rc = sh.run_command('RO=viaShell')
        print(f"    `RO=viaShell` rc       : {rc} (1 == refused)")
        store = sh.state.scope_manager.store
        ok, how = _attempt(lambda: store.assign('RO', 'viaStore'))
        print(f"    store.assign('RO',...) : {how}")
        print(f"    value                  : {sh.state.get_variable('RO')!r}")
        print(f"    GUARANTEE HELD         : "
              f"{sh.state.get_variable('RO') == 'original' and rc == 1}")
        _ = VarAttributes
    finally:
        sh.close()


# ----------------------------------------------------------------- nameref
def nameref_M():
    """Mutation attempt on the DEREF'd binding must not touch the target."""
    from psh.shell import Shell
    sh = Shell()
    try:
        sh.run_command('target=hi')
        sh.run_command('declare -n ref=target')
        look = sh.state.scope_manager.lookup('ref')
        b = look.binding
        print(f"    binding.name           : {b.name!r} (the TARGET, deref'd)")
        ok, how = _attempt(lambda: setattr(b, 'value', 'clobbered'))
        print(f"    surface .binding.value : {how}")
        print(f"    target reads           : {sh.state.get_variable('target')!r}")
        print(f"    GUARANTEE HELD         : "
              f"{sh.state.get_variable('target') == 'hi'}")
    finally:
        sh.close()


def nameref_C():
    """Legitimate nameref write still lands on the target, guards intact."""
    from psh.shell import Shell
    sh = Shell()
    try:
        sh.run_command('target=hi')
        sh.run_command('declare -n ref=target')
        sh.run_command('ref=viaRef')
        print(f"    after `ref=viaRef`: target = "
              f"{sh.state.get_variable('target')!r}")
        print(f"    ...read back via ref       = "
              f"{sh.state.get_variable('ref')!r}")
        sh.run_command('readonly target')
        rc = sh.run_command('ref=blocked')
        print(f"    readonly target; `ref=blocked` rc = {rc} (1 == refused)")
        print(f"    GUARANTEE HELD         : "
              f"{sh.state.get_variable('target') == 'viaRef' and rc == 1}")
    finally:
        sh.close()


# ---------------------------------------------------------------- observer
def observer_M():
    """A binding write must not be able to change a read without notifying."""
    from psh.shell import Shell
    sh = Shell()
    try:
        sh.run_command('export EX=one')
        fired = []
        sm = sh.state.scope_manager
        orig = sm._notify_variable_changed

        def spy(name, *a, **k):
            fired.append(name)
            return orig(name, *a, **k)
        sm._notify_variable_changed = spy       # type: ignore[method-assign]

        look = sm.lookup('EX')
        ok, how = _attempt(lambda: setattr(look.binding, 'value', 'two'))
        print(f"    surface .binding.value : {how}")
        print(f"    observer fired         : {fired!r}")
        print(f"    shell reads / env      : {sh.state.get_variable('EX')!r} / "
              f"{sh.state.env.get('EX')!r}")
        print(f"    GUARANTEE HELD (read change implies observer) : "
              f"{(sh.state.get_variable('EX') == 'one') or bool(fired)}")
    finally:
        sh.close()


def observer_C():
    """Legitimate write fires the observer and materializes env."""
    from psh.shell import Shell
    sh = Shell()
    try:
        sh.run_command('export EX=one')
        fired = []
        sm = sh.state.scope_manager
        orig = sm._notify_variable_changed

        def spy(name, *a, **k):
            fired.append(name)
            return orig(name, *a, **k)
        sm._notify_variable_changed = spy       # type: ignore[method-assign]

        sh.run_command('EX=two')
        print(f"    after `EX=two` observer fired : {fired!r}")
        print(f"    shell reads / env      : {sh.state.get_variable('EX')!r} / "
              f"{sh.state.env.get('EX')!r}")
        print(f"    GUARANTEE HELD         : "
              f"{sh.state.get_variable('EX') == sh.state.env.get('EX') == 'two' and bool(fired)}")
    finally:
        sh.close()


# ------------------------------------------------------------------ export
def export_M():
    """Mutation attempt must not desync state.env from the shell read."""
    from psh.shell import Shell
    sh = Shell()
    try:
        sh.run_command('export EX=one')
        look = sh.state.scope_manager.lookup('EX')
        ok, how = _attempt(lambda: setattr(look.binding, 'value', 'two'))
        shell_read = sh.state.get_variable('EX')
        env_read = sh.state.env.get('EX')
        print(f"    surface .binding.value : {how}")
        print(f"    shell / env            : {shell_read!r} / {env_read!r}")
        print(f"    GUARANTEE HELD (agree) : {shell_read == env_read}")
    finally:
        sh.close()


def export_C():
    """After any legitimate sequence, shell read and state.env agree, and a
    real child process sees the same value."""
    from psh.shell import Shell
    sh = Shell()
    try:
        for cmd in ('export EX=one', 'EX=two', 'export EX=three',
                    'unset EX', 'export EX=four'):
            sh.run_command(cmd)
            shell_read = sh.state.get_variable('EX')
            env_read = sh.state.env.get('EX')
            print(f"    after {cmd:20s}: shell={shell_read!r:10s} env={env_read!r}")
        agree = sh.state.get_variable('EX') == sh.state.env.get('EX') == 'four'
        print(f"    GUARANTEE HELD         : {agree}")
    finally:
        sh.close()


# --------------------------------------------------------- tri-state (frozen)
def tristate_M():
    """Mutating a lookup must not be able to change the CLASSIFICATION any
    other read sees (the _MISSING poisoning family)."""
    from psh.core.scope import ScopeManager
    from psh.core.variable_lookup import LookupStatus
    mgr = ScopeManager()
    miss = mgr.lookup('unset_a')
    ok, how = _attempt(lambda: (setattr(miss, 'status', LookupStatus.VALUE),
                                setattr(miss, 'value', 'POISON')))
    print(f"    surface .status/.value : {how}")
    other = mgr.lookup('A_DIFFERENT_UNSET_NAME')
    print(f"    unrelated miss reads   : {other.status.name} value={other.value!r}")
    print(f"    GUARANTEE HELD         : {other.status is LookupStatus.MISSING}")


def tristate_M2():
    """Same, across TWO SEQUENTIAL SHELLS in one process (4A.1's multi-shell
    precedent): shell A's poisoning must not reach shell B."""
    from psh.core.scope import ScopeManager
    from psh.core.variable_lookup import LookupStatus
    from psh.shell import Shell
    a = Shell()
    try:
        miss = a.state.scope_manager.lookup('unset_in_a')
        _attempt(lambda: (setattr(miss, 'status', LookupStatus.VALUE),
                          setattr(miss, 'value', 'POISON')))
    finally:
        a.close()
    b = Shell()
    try:
        rc = b.run_command('echo "[${TOTALLY_UNSET_IN_B+FIRED}]"')
        clean = b.state.scope_manager.lookup('ANOTHER_UNSET').status
        print(f"    shell B ${{u+w}} rc      : {rc}")
        print(f"    shell B miss status    : {clean.name}")
        print(f"    GUARANTEE HELD         : {clean is LookupStatus.MISSING}")
    finally:
        b.close()
    _ = ScopeManager


CELLS = {
    'readonly_M': ("readonly  (M) mutation attempt", readonly_M),
    'readonly_C': ("readonly  (C) legitimate path coherence", readonly_C),
    'nameref_M': ("nameref   (M) mutation attempt on deref'd binding", nameref_M),
    'nameref_C': ("nameref   (C) legitimate path coherence", nameref_C),
    'observer_M': ("observer  (M) mutation attempt", observer_M),
    'observer_C': ("observer  (C) legitimate path coherence", observer_C),
    'export_M': ("export    (M) mutation attempt", export_M),
    'export_C': ("export    (C) legitimate path coherence", export_C),
    'tristate_M': ("tri-state (M) _MISSING poisoning, one manager", tristate_M),
    'tristate_M2': ("tri-state (M) poisoning across TWO SHELLS", tristate_M2),
}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in CELLS:
        title, fn = CELLS[sys.argv[1]]
        print(f"  [{sys.argv[1]}] {title}")
        fn()
        return 0

    sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=WORKTREE,
                         capture_output=True, text=True).stdout.strip()
    print("P6 coherence matrix — MUTATION SURFACE x AUTHORITY GUARD")
    print(f"SHA: {sha}   python: {sys.version.split()[0]}")
    print("GUARANTEE HELD=False in an (M) cell == the defect, i.e. RED-ON-BASE")
    print("=" * 78)
    env = dict(os.environ, PYTHONPATH=WORKTREE)
    for key in CELLS:
        r = subprocess.run([sys.executable, os.path.abspath(__file__), key],
                           cwd=WORKTREE, capture_output=True, text=True, env=env)
        print(r.stdout, end='')
        err = r.stderr.strip()
        if err:
            print(f"    [stderr] {err[:600]}")
        print("-" * 78)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
