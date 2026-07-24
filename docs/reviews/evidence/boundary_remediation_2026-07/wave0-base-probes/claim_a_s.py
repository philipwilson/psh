import os, sys
sys.path.insert(0, '/Users/pwilson/src/psh-r22-verify')
os.chdir('/Users/pwilson/src/psh-r22-verify')
import psh.version
assert psh.version.__version__ == '0.750.0', psh.version.__version__

from psh.shell import Shell

sh = Shell()
hm = sh.interactive_manager.history_manager

# Cap the in-memory list to 3 entries.
sh.state.max_history_size = 3
print("max_history_size =", sh.state.max_history_size)

# add_to_history applies the cap:
for c in ['a1', 'a2', 'a3', 'a4', 'a5']:
    hm.add_to_history(c)
print("after 5x add_to_history:  history =", sh.state.history,
      "len =", len(sh.state.history))

# reset
sh.state.history.clear()
hm._file_synced_len = 0

# store_entry (history -s) — does it cap?
for c in ['s1', 's2', 's3', 's4', 's5']:
    hm.store_entry(c)
print("after 5x store_entry(-s): history =", sh.state.history,
      "len =", len(sh.state.history))
print("SUB-CLAIM (-s ignores cap):", len(sh.state.history) > sh.state.max_history_size)
