"""I-D: design probes feeding rulings (b) SIGNALS lease shape and
(c) quarantine model + GC-handover.  ONE CELL PER PROCESS.

These probe COSTS and FACTS, they do not implement anything.  Output
contract as in coord_matrix.py.
"""
import gc
import os
import sys
import tempfile
import weakref

import psh

print("DISCRIM", os.path.abspath(psh.__file__))

from psh.core.process_lease import (  # noqa: E402
    ComponentKind,
    LeaseError,
    get_coordinator,
)
from psh.shell import Shell  # noqa: E402

CELL = None
COORD = get_coordinator()


def emit(key, value):
    print(f"CELL {CELL} KEY={key} VALUE={value}")


def result(disposition):
    print(f"CELL {CELL} RESULT={disposition}")


# --------------------------------------------------------------------------
# D-01 — WHICH component kinds actually pin the ShellState after the owning
# Shell is dropped?  Ruling (c) option (i) (weakref the STD_FDS baseline) is
# only sufficient if STD_FDS is the ONLY pinning kind.
# --------------------------------------------------------------------------

def gc_pinning(kind):
    d = tempfile.mkdtemp()
    sh = Shell(norc=True)
    if kind == 'STD_FDS':
        # `exec 3>f`, NOT `exec >f`: an `exec >f` here would swallow this
        # probe's own observation rows into the redirect target.  fd 3 is a
        # non-VAR_FD permanent redirect, so it takes the same STD_FDS lease —
        # asserted by the leases_held row below, not assumed.
        sh.run_command('exec 3> %s' % os.path.join(d, 'out.txt'))
    elif kind == 'SIGNALS':
        sh.run_command("trap ':' USR1")
    elif kind == 'LOCALE':
        sh.run_command('true')            # activation glue takes it if pending
    held = sorted(c.kind.name for c in COORD._components if not c.released)
    emit("leases_held", ",".join(held) or "-")
    ref = weakref.ref(sh.state)
    del sh
    gc.collect()
    alive = ref() is not None
    emit("state_alive_after_gc", alive)
    emit("owner_after_gc",
         "ALIVE" if COORD.current_owner() is not None else "COLLECTED")
    # Is the coordinator's own component list the thing keeping it alive?
    if alive:
        chain = []
        for comp in COORD._components:
            if comp.released:
                continue
            restore = comp._restore
            chain.append(f"{comp.kind.name}:{type(restore).__name__}:"
                         f"{getattr(restore, '__qualname__', '?')}")
        emit("restore_callables", ";".join(chain) or "-")
    result(f"PINS:{alive}")


# --------------------------------------------------------------------------
# D-02 — what does the STD_FDS restore genuinely NEED from `state`?
# --------------------------------------------------------------------------

def std_fds_restore_needs():
    src = open(os.path.join(os.path.dirname(os.path.abspath(psh.__file__)),
                            'io_redirect', 'file_redirect.py')).read()
    start = src.index('class _StdStreamBaseline')
    body = src[start:src.index('\ndef _dup2_preserve_target', start)]
    uses = [ln.strip() for ln in body.splitlines() if 'self.state' in ln]
    emit("self_state_uses_in_baseline", len(uses))
    for i, ln in enumerate(uses):
        emit(f"use{i}", ln)
    emit("slots_has_state", "'state'" in body.split('__slots__')[1][:200])
    # Would restoring the FD half alone be coherent for a DEAD owner?
    # state.streams.restore() writes back the shell's own stream overrides —
    # attributes of an object nobody can reach any more.
    emit("state_use_is_only_stream_overrides",
         all('streams.restore' in u for u in uses))
    result(f"USES:{len(uses)}")


# --------------------------------------------------------------------------
# D-03 — does the LOCALE restore closure's captured `service` back-reference
# the ShellState (same GC defeat as _StdStreamBaseline)?
# --------------------------------------------------------------------------

def locale_closure_backref():
    sh = Shell(norc=True)
    sh.run_command('true')
    state = sh.state
    service = state.locale
    attrs = {k: type(v).__name__ for k, v in vars(service).items()}
    emit("service_attrs", ",".join(f"{k}:{v}" for k, v in attrs.items()))
    reaches_state = any(v is state for v in vars(service).values())
    emit("service_directly_references_state", reaches_state)
    lease = COORD.find_component(state, ComponentKind.LOCALE)
    emit("locale_lease_present", lease is not None)
    if lease is not None:
        cells = getattr(lease._restore, '__closure__', None)
        captured = ([type(c.cell_contents).__name__ for c in cells]
                    if cells else [])
        emit("restore_closure_captures", ",".join(captured) or "-")
        emit("restore_defaults",
             ",".join(type(d).__name__
                      for d in (lease._restore.__defaults__ or ())))
        emit("restore_captures_state",
             any(d is state for d in (lease._restore.__defaults__ or ())))
    ref = weakref.ref(state)
    sh.close()
    del sh, state, service, lease
    gc.collect()
    emit("state_alive_after_close_and_gc", ref() is not None)
    result("BACKREF" if reaches_state else "NO_BACKREF")


# --------------------------------------------------------------------------
# D-04 — SIGNALS folding: if managed dispositions used the SAME
# ComponentKind.SIGNALS as trap-installed unmanaged ones, the FIRST
# acquirer's restore is the only one that ever runs (acquire_component is
# idempotent per (owner, kind)).  Demonstrated on the coordinator directly.
# --------------------------------------------------------------------------

def signals_folding_loses_a_family(order):
    class Owner:
        locale = None
        name = 'A'

    a = Owner()
    COORD.activate(a).release()
    ran = []
    first, second = ('managed', 'trap') if order == 'managed-first' \
        else ('trap', 'managed')
    l1 = COORD.acquire_component(a, ComponentKind.SIGNALS,
                                 restore=lambda: ran.append(first),
                                 description=f"probe-{first}")
    l2 = COORD.acquire_component(a, ComponentKind.SIGNALS,
                                 restore=lambda: ran.append(second),
                                 description=f"probe-{second}")
    emit("second_acquire_folded", l2 is l1)
    emit("lease_description", l1.description)
    COORD.release_owner(a)
    emit("restores_that_ran", ",".join(ran) or "-")
    emit("families_restored", len(ran))
    result(f"RAN:{','.join(ran) or '-'}")


# --------------------------------------------------------------------------
# D-05 — aggregate error shape: what stays in the LOUD (internal-defect)
# family and what the four existing suites' pytest.raises(LeaseError) accept.
# --------------------------------------------------------------------------

def aggregate_error_shape():
    from psh.core.exceptions import PshError

    class AggregateLeaseError(LeaseError):
        pass

    candidates = {
        'LeaseError': LeaseError("x"),
        'LeaseError_subclass': AggregateLeaseError("x"),
        'ExceptionGroup': ExceptionGroup("x", [RuntimeError("a")]),
    }
    for name, exc in candidates.items():
        emit(f"{name}.is_LeaseError", isinstance(exc, LeaseError))
        emit(f"{name}.is_RuntimeError", isinstance(exc, RuntimeError))
        emit(f"{name}.is_PshError", isinstance(exc, PshError))
        emit(f"{name}.is_OSError", isinstance(exc, OSError))
        # report_internal_defect's EXPECTED set is PshError/OSError/
        # SyntaxError/RecursionError; everything else is an INTERNAL DEFECT
        # (loud under strict-errors).
        expected = isinstance(exc, (PshError, OSError, SyntaxError,
                                    RecursionError))
        emit(f"{name}.classifies_internal", not expected)
        emit(f"{name}.caught_by_pytest_raises_LeaseError",
             isinstance(exc, LeaseError))
    # __notes__ availability for carrying per-failure detail on one exception.
    e = LeaseError("x")
    e.add_note("detail")
    emit("add_note_supported", getattr(e, '__notes__', None) == ["detail"])
    emit("python_version", "%d.%d" % sys.version_info[:2])
    result("RECORDED")


# --------------------------------------------------------------------------
# D-06 — is there ANY public way today to observe an orphan / prove the
# process clean?  (Quarantine observability baseline for ruling (c).)
# --------------------------------------------------------------------------

def observability_baseline():
    public = [n for n in dir(COORD) if not n.startswith('_')]
    emit("public_surface", ",".join(sorted(public)))
    emit("has_clean_predicate",
         any('clean' in n or 'quiesc' in n or 'quarant' in n for n in public))
    emit("find_component_needs_owner", 'owner' in
         COORD.find_component.__doc__.lower())
    result("|".join(sorted(public)))


CELLS = {
    'D-01-locale': lambda: gc_pinning('LOCALE'),
    'D-01-signals': lambda: gc_pinning('SIGNALS'),
    'D-01-stdfds': lambda: gc_pinning('STD_FDS'),
    'D-02': std_fds_restore_needs,
    'D-03': locale_closure_backref,
    'D-04-managed-first': lambda: signals_folding_loses_a_family('managed-first'),
    'D-04-trap-first': lambda: signals_folding_loses_a_family('trap-first'),
    'D-05': aggregate_error_shape,
    'D-06': observability_baseline,
}


if __name__ == '__main__':
    CELL = sys.argv[1]
    if CELL == '--list':
        for name in CELLS:
            print(name)
        raise SystemExit(0)
    CELLS[CELL]()
