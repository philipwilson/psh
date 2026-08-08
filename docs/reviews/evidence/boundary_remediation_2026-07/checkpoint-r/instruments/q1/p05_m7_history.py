# Q1 probe 05 (MEDIUM-7): history cursor conflation. Fresh 0.773.0 equivalents
# of the version-pinned wave0-base-probes/claim_a_psh.py / claim_a_s.py.
# Leg A: startup load A,B,C -> history -d 1 -> external append D -> history -n.
#   Base bug: -d decremented the read cursor -> duplicate C (B,C,C,D).
#   Tip claim (v0.772.0, bash parity): ['B','C','D'].
# Leg S: history -s with a 3-entry cap. Base bug: -s bypassed HISTSIZE (5 kept).
#   Tip claim: -s routes through the ONE recording pipeline incl. cap (3 kept).
# Axis: REGRESSION vs the recorded base results (expected values = the row's
# measured-bash values).
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

WORK = os.path.join(WT, 'tmp', 'q1m7')
os.makedirs(WORK, exist_ok=True)
HF = os.path.join(WORK, 'histfile')

print("=== Leg A: -d must not move the read cursor ===")
sh = Shell(norc=True)
hm = sh.interactive_manager.history_manager
sh.state.history_file = HF
with open(HF, 'w') as f:
    f.write("A\nB\nC\n")
hm.load_from_file()
print("after load:  history =", sh.state.history,
      "| _file_read_len =", hm._file_read_len)
rc = sh.run_command("history -d 1")
print("history -d 1 rc =", rc, "| history =", sh.state.history,
      "| _file_read_len =", hm._file_read_len)
with open(HF, 'a') as f:
    f.write("D\n")
rc = sh.run_command("history -n")
print("history -n rc =", rc, "| history =", sh.state.history,
      "| _file_read_len =", hm._file_read_len)
print("EXPECTED (bash):", ['B', 'C', 'D'])
print("LEG-A RESULT:", "PASS" if sh.state.history == ['B', 'C', 'D']
      else "FAIL (dup bug or other): %r" % (sh.state.history,))
sh.close()

print()
print("=== Leg S: history -s honors the HISTSIZE cap ===")
sh2 = Shell(norc=True)
hm2 = sh2.interactive_manager.history_manager
sh2.state.max_history_size = 3
sh2.state.history.clear()
for c in ['s1', 's2', 's3', 's4', 's5']:
    sh2.run_command("history -s %s" % c)
print("after 5x history -s: history =", sh2.state.history,
      "len =", len(sh2.state.history))
print("LEG-S RESULT:", "PASS (cap honored)" if len(sh2.state.history) <= 3
      else "FAIL (-s bypasses cap)")
print("tail is the last 3:", sh2.state.history == ['history -s s3'.replace('history -s ', '') for _ in []] or sh2.state.history)
sh2.close()
