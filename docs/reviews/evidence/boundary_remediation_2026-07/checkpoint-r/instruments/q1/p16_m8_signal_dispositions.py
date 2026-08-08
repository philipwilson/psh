# Q1 probe 16 (MEDIUM-8): signal dispositions must NOT outlive Shell.close().
# Base: 7 script-mode leaked dispositions. Tip claim (v0.768.0):
# restore-exact-prior + unconditional drain in Shell.close().
# Axis: REGRESSION vs recorded base bug.
import os
import signal
import sys

WT = ('/private/tmp/claude-501/-Users-pwilson-src-psh/'
      '05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt')
assert os.getcwd() == WT
sys.path.insert(0, WT)
import psh.version
assert psh.version.__version__ == '0.773.0'
assert psh.version.__file__.startswith(WT)
print("DISCRIMINATOR OK:", psh.version.__version__)

SIGS = [signal.SIGTERM, signal.SIGINT, signal.SIGQUIT, signal.SIGUSR1,
        signal.SIGUSR2, signal.SIGHUP, signal.SIGCHLD, signal.SIGTSTP,
        signal.SIGTTOU, signal.SIGTTIN, signal.SIGPIPE]
before = {s: signal.getsignal(s) for s in SIGS}

from psh.shell import Shell
sh = Shell(norc=True)
sh.run_command("trap 'echo t' TERM USR1 HUP QUIT INT USR2")
sh.run_command(":")
mid_changed = [s.name for s in SIGS if signal.getsignal(s) is not before[s]]
print("dispositions changed while shell live:", mid_changed)
sh.close()
after = {s: signal.getsignal(s) for s in SIGS}
leaked = [s.name for s in SIGS if after[s] is not before[s]]
print("dispositions leaked after close():", leaked)
print("RESULT:", "PASS (restore-exact-prior)" if not leaked else "FAIL: %s" % leaked)

# double-close and re-use-after-close must not corrupt
sh.close()
leaked2 = [s.name for s in SIGS if signal.getsignal(s) is not before[s]]
print("after double-close leaked:", leaked2)
