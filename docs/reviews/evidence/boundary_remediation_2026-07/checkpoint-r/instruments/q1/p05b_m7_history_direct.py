# Q1 probe 05b (MEDIUM-7 leg A, v2): same shape as the committed
# claim_a_psh.py but 0.773.0-pinned and driving the manager API directly
# (avoids the shell recording the probe's own `history` commands, which
# p05's run_command route mixed into the list).
import os
import sys

WT = ('/private/tmp/claude-501/-Users-pwilson-src-psh/'
      '05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt')
assert os.getcwd() == WT
sys.path.insert(0, WT)
import psh.version
assert psh.version.__version__ == '0.773.0'
assert psh.version.__file__.startswith(WT)
print("DISCRIMINATOR OK:", psh.version.__version__)

from psh.shell import Shell

WORK = os.path.join(WT, 'tmp', 'q1m7b')
os.makedirs(WORK, exist_ok=True)
HF = os.path.join(WORK, 'histfile')

sh = Shell(norc=True)
hm = sh.interactive_manager.history_manager
sh.state.history_file = HF
with open(HF, 'w') as f:
    f.write("A\nB\nC\n")
hm.load_from_file()
print("after load:  history =", sh.state.history,
      "| _file_read_len =", hm._file_read_len)
hm.delete_entry(1, 1)
print("after -d 1:  history =", sh.state.history,
      "| _file_read_len =", hm._file_read_len)
with open(HF, 'a') as f:
    f.write("D\n")
hm.read_new_history()
print("after -n:    history =", sh.state.history,
      "| _file_read_len =", hm._file_read_len)
print("EXPECTED (bash): ['B', 'C', 'D']")
print("RESULT:", "PASS" if sh.state.history == ['B', 'C', 'D']
      else "FAIL: %r" % (sh.state.history,))
print("DUP-C BUG PRESENT:", sh.state.history == ['B', 'C', 'C', 'D'])
sh.close()
