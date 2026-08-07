"""M8 mutation locks for slot 4A.1: does each load-bearing arm have a pin
that fails for ITS OWN reason?

For every mutation the harness reverts ONE arm of the fix, runs the pin
suites, and records which tests fail. A mutation that kills nothing means
the arm is unpinned; a mutation that kills the SAME tests as another means
the two arms are not independently pinned.

Files are restored from a copy this script takes itself — never with
``git checkout``, which would destroy uncommitted work in the tree.

    python mutation_locks.py            # run every mutation
    python mutation_locks.py <name>     # one mutation
"""
import subprocess
import sys

ROOT = "/Users/pwilson/src/psh-r4a-1"
LEASE = f"{ROOT}/psh/core/process_lease.py"
REDIR = f"{ROOT}/psh/io_redirect/file_redirect.py"
SIGMAN = f"{ROOT}/psh/interactive/signal_manager.py"

PINS = [
    "tests/unit/core/test_activation_transaction_4a1.py",
    "tests/unit/core/test_process_lease.py",
    "tests/integration/redirection/test_failed_exec_lease_4a1.py",
    "tests/unit/interactive/test_managed_signal_lease_4a1.py",
    "tests/unit/core/test_signal_lease_coordination_f2.py",
    "tests/integration/redirection/test_std_fd_lease_f2.py",
]

#: name -> (file, old, new). Each reverts exactly ONE arm.
MUTATIONS = {
    # Arm 1: the checkpoint unwind itself (activate's grant window).
    "unwind-activate": (LEASE,
        """                self._activations.pop()
                lease.released = True
                self._unwind_components_to(checkpoint, exc)""",
        """                self._activations.pop()
                lease.released = True"""),
    # Arm 2: the unwind in acquire_component's grant window.
    "unwind-acquire": (LEASE,
        """            except BaseException as exc:
                self._unwind_components_to(checkpoint, exc)
                self._rollback_owner(rollback)
                raise
            # The grant glue may itself have acquired THIS kind""",
        """            except BaseException as exc:
                self._rollback_owner(rollback)
                raise
            # The grant glue may itself have acquired THIS kind"""),
    # Arm 3: unwind ORDER — components before owner metadata.
    "unwind-order": (LEASE,
        """                self._unwind_components_to(checkpoint, exc)
                self._rollback_owner(rollback)
                raise
        return lease""",
        """                self._rollback_owner(rollback)
                self._unwind_components_to(checkpoint, exc)
                raise
        return lease"""),
    # Arm 4: orphan discrimination in _ensure_owner (count only own leases).
    "ensure-owner-discrimination": (LEASE,
        """        own = self._components_of(current)
        if current is not None and (self._activations or own):""",
        """        own = self._components_of(current)
        if current is not None and (self._activations or self._live_components()):"""),
    # Arm 5: the deterministic orphan sweep in _ensure_owner.
    "ensure-owner-sweep": (LEASE,
        """        orphans = self._orphan_components(current)
        if orphans:
            self._release_components(orphans)""",
        """        orphans = self._orphan_components(current)"""),
    # Arm 6: find_component's per-lease owner filter.
    "find-component-filter": (LEASE,
        """            if (lease.kind is kind and not lease.released
                    and lease.owner_ref() is owner):""",
        """            if lease.kind is kind and not lease.released:"""),
    # Arm 7: release_owner sweeping a non-owner caller's own leases.
    "release-owner-sweep": (LEASE,
        """        if self._owner_ref is None or self._owner_ref() is not owner:
            self._release_components(self._components_of(owner))
            return""",
        """        if self._owner_ref is None or self._owner_ref() is not owner:
            return"""),
    # Arm 8: aggregate surfacing (vs the old swallow).
    "aggregate-surfacing": (LEASE,
        """        if failures:
            kinds = ", ".join(sorted(lease.kind.name for lease, _ in failures))
            raise LeaseRestoreError(""",
        """        if False:
            kinds = ", ".join(sorted(lease.kind.name for lease, _ in failures))
            raise LeaseRestoreError("""),
    # Arm 9: attempting EVERY restore (vs stopping at the first failure).
    "attempt-every-restore": (LEASE,
        """            except Exception as exc:                     # noqa: BLE001
                failures.append((lease, exc))
                self._quarantined.append(lease)""",
        """            except Exception as exc:                     # noqa: BLE001
                failures.append((lease, exc))
                self._quarantined.append(lease)
                break"""),
    # Arm 10: quarantine blocking the next ownership grant.
    "quarantine-blocks": (LEASE,
        '        if self._quarantined:\n            raise LeaseError(\n',
        '        if False:\n            raise LeaseError(\n'),
    # Arm 11: newly-acquired-only release on a failed exec.
    "failed-exec-release": (REDIR,
        """            if lease_acquired_here:""",
        """            if False:"""),
    # Arm 12: the newly-acquired DISCRIMINATION (release even an older lease).
    "failed-exec-discrimination": (REDIR,
        """            if lease_acquired_here:""",
        """            if True:"""),
    # Arm 13: the errno split in the baseline-dup arm.
    "errno-split": (REDIR,
        """                    if exc.errno != errno.EBADF:
                        raise""",
        """                    if False:
                        raise"""),
    # Arm 14: the weak state reference in the STD_FDS baseline.
    "weak-baseline-ref": (REDIR,
        """        self._state_ref: 'weakref.ref[ShellState]' = weakref.ref(state)""",
        """        self._state_ref = (lambda s=state: s)  # strong again"""),
    # Arm 15: MANAGED_SIGNALS as its own kind (vs folding into SIGNALS).
    "managed-signals-kind": (SIGMAN,
        """            self.state, ComponentKind.MANAGED_SIGNALS,""",
        """            self.state, ComponentKind.SIGNALS,"""),
    # Arm 16: taking the managed lease at all.
    "managed-lease-acquired": (SIGMAN,
        """        if not self._original_handlers:
            self._register_managed_signal_lease()""",
        """        if False:
            self._register_managed_signal_lease()"""),
}


def run_pins():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *PINS, "-q", "-p", "no:randomly",
         "--no-header", "-x" if False else "--tb=no"],
        cwd=ROOT, capture_output=True, text=True, timeout=600)
    failed = sorted({ln.split("::")[-1].split()[0]
                     for ln in proc.stdout.splitlines()
                     if ln.startswith("FAILED")})
    errors = sum(1 for ln in proc.stdout.splitlines() if ln.startswith("ERROR"))
    return failed, errors, proc.stdout.strip().splitlines()[-1] if proc.stdout else ""


def apply_mutation(name):
    path, old, new = MUTATIONS[name]
    original = open(path).read()
    if old not in original:
        return None, original, path
    open(path, "w").write(original.replace(old, new, 1))
    return True, original, path


def main():
    wanted = sys.argv[1:] or list(MUTATIONS)
    print(f"# baseline (unmutated)")
    base_failed, base_errors, base_line = run_pins()
    print(f"  {base_line}")
    if base_failed or base_errors:
        print(f"  ABORT: pins are not green before mutating: {base_failed}")
        return 1
    results = {}
    for name in wanted:
        ok, original, path = apply_mutation(name)
        try:
            if ok is None:
                print(f"\n## {name}: PATTERN NOT FOUND (stale mutation)")
                results[name] = None
                continue
            failed, errors, line = run_pins()
            results[name] = failed
            print(f"\n## {name}  ({path.split('/')[-1]})")
            print(f"   {line}")
            print(f"   killed {len(failed)} test(s): " +
                  (", ".join(failed[:6]) + (" ..." if len(failed) > 6 else "")
                   if failed else "NONE  <-- UNPINNED ARM"))
        finally:
            open(path, "w").write(original)
    print("\n=== DERIVED ===")
    unpinned = [n for n, f in results.items() if f == []]
    stale = [n for n, f in results.items() if f is None]
    print(f"mutations run       = {len([f for f in results.values() if f is not None])}")
    print(f"arms with a lock    = {len([f for f in results.values() if f])}")
    print(f"UNPINNED arms       = {len(unpinned)} {unpinned}")
    print(f"stale patterns      = {len(stale)} {stale}")
    # Independence: two arms killing the identical test set are not
    # independently pinned.
    seen = {}
    for name, failed in results.items():
        if not failed:
            continue
        key = tuple(failed)
        seen.setdefault(key, []).append(name)
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    print(f"arms sharing an IDENTICAL kill set = {len(dupes)}")
    for key, names in dupes.items():
        print(f"   {names} -> {list(key)[:4]}")
    return 1 if unpinned or stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
