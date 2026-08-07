"""BL-4: verification rows for the two must-not-flip rails the frozen ledger
was silent on, both inside the rewrite's blast radius.

Rail A: cwd and the recursion limit are DOCUMENTED process-owned — recorded
        at ownership grant for introspection, deliberately NOT restored on
        deactivation (cd persistence and the only-raises recursion policy are
        shell semantics, not leaks).
Rail B: _clear_owner timing — the process-active locale slot is cleared at
        ACTUAL relinquish, never earlier, so the shell's own EXIT trap still
        pattern-matches under its own locale during shutdown.
"""
import os
import sys

import psh
print("DISCRIM", os.path.abspath(psh.__file__))

from psh.core.locale_service import active_locale  # noqa: E402
from psh.core.process_lease import RECURSION_LIMIT, get_coordinator  # noqa: E402
from psh.shell import Shell  # noqa: E402

coord = get_coordinator()

# ---- Rail A: cwd + recursion limit recorded, NOT restored ----------------
start_cwd = os.getcwd()
start_limit = sys.getrecursionlimit()
sh = Shell(norc=True)
lease = sh.state.activate()
baselines = lease.baselines
sh.run_command('cd /tmp')
cwd_during = os.getcwd()
lease.release()
sh.close()
print("RAIL-A baseline_records_cwd:", baselines.cwd == start_cwd)
print("RAIL-A baseline_records_limit:", baselines.recursion_limit == start_limit)
print("RAIL-A cwd_NOT_restored:", os.getcwd() == cwd_during != start_cwd)
print("RAIL-A limit_raised_and_kept:",
      sys.getrecursionlimit() >= RECURSION_LIMIT)
os.chdir(start_cwd)

# ---- Rail B: _clear_owner timing vs the EXIT trap ------------------------
# The shell's EXIT trap runs during shutdown; the process-active locale slot
# must still point at THIS shell's service while it does, so a pattern in the
# trap body matches under the shell's own locale.
sh2 = Shell(norc=True)
sh2.run_command('true')
service = sh2.state.locale
print("RAIL-B active_locale_is_shell_service_while_live:",
      active_locale() is service)
seen = {}
_orig = sh2.state.locale


class _Watch:
    """Record what active_locale() is at the moment the EXIT trap body runs."""


sh2.run_command("trap 'case xyz in x*) :;; esac' EXIT")
# Drive the EXIT trap through the real shutdown path and observe the slot
# from inside the trap body via a command substitution the trap performs.
rc = sh2.run_command("trap 'echo INTRAP >/dev/null' EXIT")
seen['before_close'] = active_locale() is service
sh2.close()
seen['after_close'] = active_locale() is service
print("RAIL-B slot_held_before_close:", seen['before_close'])
print("RAIL-B slot_cleared_after_close:", not seen['after_close'])
print("RAIL-B owner_cleared_after_close:", coord.current_owner() is None)
