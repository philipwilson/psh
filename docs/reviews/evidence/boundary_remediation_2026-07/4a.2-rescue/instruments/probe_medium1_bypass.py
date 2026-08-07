"""Brief-time evidence probe for slot 4A.2 (MEDIUM-1), at base d1e4f1ae.

Run as a subprocess from the repo root. Two legs:
  1. Exit-status precedence psh-vs-bash (-c observable) — run via the
     shell loop in the dispatch transcript (four cells: 7/3/7/7 MATCH).
  2. Structural bypass instrumentation (this file): trap-exit ->
     which shutdown steps ran?
"""
import psh
print("DISCRIMINATOR:", psh.__file__)
from psh.shell import Shell  # noqa: E402

calls = []
sh = Shell(norc=True)
sh._dispose_jobs_at_exit = lambda **k: calls.append('dispose_jobs')
hm = sh.interactive_manager.history_manager
hm.save_to_file = lambda *a, **k: calls.append('history_save')
try:
    rc = sh.run_command("trap 'exit 7' EXIT; exit 3")
    print("returned rc", rc)
except SystemExit as e:
    print("SystemExit", e.code)
print("shutdown steps that ran:", calls or "NONE")
print("shutdown_reason:", getattr(sh, '_shutdown_reason', None))
# Control: no trap — the same route runs the steps.
calls2 = []
sh2 = Shell(norc=True)
sh2._dispose_jobs_at_exit = lambda **k: calls2.append('dispose_jobs')
sh2.interactive_manager.history_manager.save_to_file = (
    lambda *a, **k: calls2.append('history_save'))
try:
    sh2.run_command("exit 3")
except SystemExit as e:
    print("control SystemExit", e.code)
print("control steps:", calls2 or "NONE")
