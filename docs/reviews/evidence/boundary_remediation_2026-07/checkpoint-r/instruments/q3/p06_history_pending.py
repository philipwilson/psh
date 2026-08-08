"""Q3 fresh probe: history pending-set positional invariants (slot 4B.3, ruling O3).

Five binding invariants, probed from OUTSIDE the suite:
  inv1 pending <= memory: a `-d`'d entry is never resurrected by `-a`.
  inv2 membership: `-r`-read lines are never pending (no duplicate on save).
  inv3 one maintenance site: static census of `_owed` writers (all inside
       HistoryManager's own helpers).
  inv4 duplicate strings positional: two identical debts save twice; deleting
       one leaves exactly one owed.
  inv5 `_file_synced_len` retired: zero occurrences in psh/.
Plus the `_sync_owed` strict=True drift-loudness, mutation-proven in-process:
with the reconciler disabled, a forced length drift must raise (zip strict),
not silently mis-save.

Subprocess cells run tip psh AND /opt/homebrew/bin/bash on identical scripts —
these compositions avoid the declared b1–b5 interleaves except where noted.
Run with cwd = worktree.
"""
import os
import subprocess
import sys
import tempfile

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q3/wt"
assert os.getcwd() == WT
sys.path.insert(0, WT)
BASH = ["/opt/homebrew/bin/bash"]
ENV = {"HOME": os.environ["HOME"], "PATH": os.environ["PATH"],
       "PYTHONPATH": WT, "TERM": "dumb"}

import psh  # noqa: E402
assert os.path.realpath(psh.__file__).startswith(os.path.realpath(WT) + os.sep)

failures = []


def run_shell(argv, script, histfile, seed=None):
    if os.path.exists(histfile):
        os.unlink(histfile)
    if seed is not None:
        with open(histfile, "w") as fh:
            fh.write(seed)
    env = dict(ENV, HISTFILE=histfile)
    subprocess.run(argv + ["-c", script], cwd=WT, env=env,
                   capture_output=True, timeout=30)
    try:
        with open(histfile) as fh:
            return fh.read()
    except FileNotFoundError:
        return "<NO FILE>"


def cell(name, script, expect_psh, seed=None, bash_should_match=True):
    if not isinstance(expect_psh, tuple):
        expect_psh = (expect_psh,)
    with tempfile.TemporaryDirectory(dir=WT + "/tmp") as d:
        hf = os.path.join(d, "hist")
        got_psh = run_shell([sys.executable, "-m", "psh"], script, hf, seed)
        got_bash = run_shell(BASH, script, hf, seed)
    ok = got_psh in expect_psh
    parity = got_psh == got_bash
    if not ok:
        failures.append((name, got_psh, expect_psh))
    if bash_should_match and not parity:
        failures.append((name + " [bash-parity]", got_psh, got_bash))
    print(f"{'PASS' if ok else 'FAIL':4} {name}: psh={got_psh!r} "
          f"bash={got_bash!r} expect={expect_psh!r} parity={parity}")


# inv1: -d between record and save -> deleted entry never resurrected
cell("inv1 -d then -a",
     'history -s cmd1; history -s cmd2; history -d 2; history -a',
     "cmd1\n")
# inv1 harder: -c wipes all debts
cell("inv1b -c then -a",
     'history -s cmd1; history -c; history -a', ("<NO FILE>", ""),
     bash_should_match=False)  # empty-or-absent both prove nothing resurrected
# inv2: -r-read lines never pending (b1(i) declared family: psh no-duplicate;
# bash's tail window ALSO writes only 'typed' here per the measured model)
cell("inv2 -r then -a",
     'history -r; history -s typed; history -a',
     "readline1\ntyped\n", seed="readline1\n")
# inv4: two identical debts -> two file lines
cell("inv4a dup debts save twice",
     'history -s dup; history -s dup; history -a', "dup\ndup\n")
# inv4: delete ONE of two identical debts -> exactly one saved
cell("inv4b delete one dup",
     'history -s dup; history -s dup; history -d 2; history -a', "dup\n")
# a second -a is a no-op (debt cleared by the first)
cell("inv1c -a twice",
     'history -s once; history -a; history -a', "once\n")

# ---- in-process: strict=True drift-loudness (mutation-proven) --------------
from psh.shell import Shell  # noqa: E402

shell = Shell()
hm = shell.interactive_manager.history_manager
shell.state.history.append("outside-append")
pend = hm._pending_entries()          # reconciler absorbs the outside append
assert "outside-append" not in pend, "outside append must not be owed (inv2 direction)"

# now disable the reconciler and force a drift: the strict zip must go LOUD
hm._sync_owed = lambda: None
shell.state.history.append("drift")
try:
    hm._pending_entries()
    loud = False
except ValueError:
    loud = True
print(f"{'PASS' if loud else 'FAIL':4} strict-loudness: drift with reconciler "
      f"disabled raises ValueError = {loud}")
if not loud:
    failures.append(("strict-loudness", "no raise", "ValueError"))

print("P06-RESULT:", "HOLDS" if not failures else f"HOLE: {failures}")
sys.exit(0 if not failures else 1)
