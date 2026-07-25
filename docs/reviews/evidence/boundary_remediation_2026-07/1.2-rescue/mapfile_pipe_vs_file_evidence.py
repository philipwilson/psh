"""Evidence probe: mapfile_drains must behave DIFFERENTLY on a pipe vs a
seekable file, through the MIGRATED module's own helpers (not a re-derivation).
"""
import os
import stat
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tests", "harness"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tests", "system"))

from shell_oracle import run_bash, run_psh  # noqa: E402
from test_stdin_script_lazy_read import (  # noqa: E402
    BASH, PSH, STDIN_SHARING_SCRIPTS, _run,
)

SCRIPT = STDIN_SHARING_SCRIPTS["mapfile_drains"]
print("script bytes:", SCRIPT)

for label, argv in (("bash", [BASH]), ("psh", PSH)):
    for seekable in (False, True):
        rc, out = _run(argv, SCRIPT, seekable=seekable)
        kind = "SEEKABLE FILE" if seekable else "PIPE"
        print(f"{label:5s} {kind:14s} rc={rc:<4d} stdout={out!r}")

# Independent proof that the fd KIND really differs (S_ISFIFO vs S_ISREG),
# straight from the runner, not from the shell under test.
PROBE = ("import os,stat,sys; m=os.fstat(0).st_mode; "
         "sys.stdout.write('FIFO' if stat.S_ISFIFO(m) else "
         "('REG' if stat.S_ISREG(m) else 'OTHER'))")
for mode in ("pipe", "file"):
    r = run_bash(["-c", f"{sys.executable} -c \"{PROBE}\""],
                 stdin_data=b"x\n", stdin_mode=mode, timeout=20)
    print(f"fd0 kind under stdin_mode={mode!r}: {r.stdout}")
_ = (run_psh, stat)
