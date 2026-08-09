#!/usr/bin/env python3
"""B2 — AXIS 2 (RECLASSIFICATION) for the narrowed maskers.

Axis 1 proved the non-defect paths are byte-identical. This proves the OTHER
half of the two-axis pin: a defect that the broad net used to swallow as a user
diagnostic now surfaces per the strict-errors taxonomy.

Each cell seeds a ValueError INSIDE the former try body (never in the
documented int() conversion) and records what the user sees. At BASE the defect
is masked as a bland user error; at TIP it must surface. The seed is a
monkeypatch applied and reverted in-process — nothing is left in the tree.

ROOT from argv[1]; discriminator asserted before measuring.
"""
import os
import sys

ROOT = os.path.abspath(sys.argv[1])
sys.path.insert(0, ROOT)
import psh  # noqa: E402

assert os.path.dirname(psh.__file__) == os.path.join(ROOT, "psh"), \
    f"DISCRIMINATOR FAILED: {os.path.dirname(psh.__file__)}"
print(f"# tree={ROOT}")

from psh.shell import Shell  # noqa: E402


def run(label, seed, script):
    """Apply *seed* (a callable returning an undo), run *script*, report."""
    undo = seed()
    sh = Shell(norc=True)
    try:
        rc = sh.run_command(script)
        print(f"{label:34s} rc={rc}")
    except BaseException as e:                    # noqa: BLE001 - measuring
        print(f"{label:34s} SURFACED {type(e).__name__}: {str(e)[:60]}")
    finally:
        sh.close()
        undo()


# --- seeds: a ValueError from a call that USED to sit inside the net --------
def seed_popd_pop():
    """INSTRUMENT DEFECT FOUND AND FIXED (recorded, not buried).

    The first version seeded ``_chdir_or_error``. That call is shared with
    ``pushd`` -- so the seeded ValueError fired during the cell's own
    ``pushd /usr`` SETUP, outside popd's try entirely, and surfaced at BASE as
    well as at TIP. A cell that shows the same result on both sides proves
    nothing about the narrowing; it was measuring the setup line.

    ``DirectoryStack.pop`` is reached ONLY by popd, and only from inside the
    former try body, so it is the discriminating seed: masked at base,
    surfaced at tip.
    """
    from psh.builtins.directory_stack import DirectoryStack
    orig = DirectoryStack.pop

    def boom(self, *a, **k):
        raise ValueError("seeded defect in DirectoryStack.pop")
    DirectoryStack.pop = boom
    return lambda: setattr(DirectoryStack, "pop", orig)


def seed_dirs_size():
    from psh.builtins.directory_stack import DirectoryStack
    orig = DirectoryStack.size

    def boom(self):
        raise ValueError("seeded defect in DirectoryStack.size")
    DirectoryStack.size = boom
    return lambda: setattr(DirectoryStack, "size", orig)


def seed_disown_lookup():
    from psh.executor.job_control import JobManager
    orig = JobManager.get_job_by_pid

    def boom(self, pid):
        raise ValueError("seeded defect in get_job_by_pid")
    JobManager.get_job_by_pid = boom
    return lambda: setattr(JobManager, "get_job_by_pid", orig)


print("=== AXIS 2: forced defect inside the FORMER try body ===")
run("popd +0 / DirectoryStack.pop", seed_popd_pop,
    "cd /tmp; pushd /usr >/dev/null; popd +0")
run("dirs +0 / DirectoryStack.size", seed_dirs_size, "dirs +0")
run("disown 123 / get_job_by_pid", seed_disown_lookup, "disown 123")

print("\n=== CONTROL: same cells with NO seed (must be ordinary user errors) ===")
noop = (lambda: (lambda: None))
run("popd +0 unseeded", noop, "cd /tmp; pushd /usr >/dev/null; popd +0")
run("dirs +0 unseeded", noop, "dirs +0")
run("disown 123 unseeded", noop, "disown 123")
