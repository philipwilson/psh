import os, sys
sys.path.insert(0, '/Users/pwilson/src/psh-r22-verify')
os.chdir('/Users/pwilson/src/psh-r22-verify')
import psh.version
assert psh.version.__version__ == '0.750.0', psh.version.__version__

from psh.shell import Shell

WORK = '/Users/pwilson/src/psh-r22-verify/tmp/hist_a'
os.makedirs(WORK, exist_ok=True)
HF = os.path.join(WORK, 'histfile')

sh = Shell()
hm = sh.interactive_manager.history_manager
sh.state.history_file = HF

# 1. Write file with A B C
with open(HF, 'w') as f:
    f.write("A\nB\nC\n")

# 2. Load the default file (startup-style read)
hm.load_from_file()
print("after load:        history =", sh.state.history,
      "| _file_read_len =", hm._file_read_len,
      "| _file_synced_len =", hm._file_synced_len)

# 3. history -d 1  (delete in-memory entry 1 == A)
hm.delete_entry(1, 1)
print("after -d 1:         history =", sh.state.history,
      "| _file_read_len =", hm._file_read_len,
      "| _file_synced_len =", hm._file_synced_len)

# 4. Append D to the file externally
with open(HF, 'a') as f:
    f.write("D\n")
print("file on disk now:", open(HF).read().split())

# 5. history -n  (read only lines not already read)
hm.read_new_history()
print("after -n:           history =", sh.state.history,
      "| _file_read_len =", hm._file_read_len)

print()
print("PSH RESULT:", sh.state.history)
print("EXPECTED (bash):    ['B', 'C', 'D']")
print("DUP-C BUG PRESENT:", sh.state.history == ['B', 'C', 'C', 'D'])
