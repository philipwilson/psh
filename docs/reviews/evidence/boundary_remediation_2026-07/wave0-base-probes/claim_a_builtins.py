import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psh.version
assert psh.version.__version__ == '0.750.0', psh.version.__version__
from psh.shell import Shell

def log(*a):
    print(*a); sys.stdout.flush()

log("=== Claim A via REAL builtins: read -t (buffers C3) then mapfile (read_all) ===")
sh = Shell()
log("step1: shell built")

r, w = os.pipe()
FD = 7
os.dup2(r, FD)          # expose the pipe read-end as fd 7 for the shell
os.close(r)
log("step2: pipe read-end on fd", FD)

os.write(w, b'\xc3')    # only the lead byte available
log("step3: wrote C3")

rc = sh.run_command(f"read -t 0.2 -n 5 -u {FD} x; echo read-rc=$?")
log("step4: read returned, rc(run_command)=", rc)

os.write(w, b'\xa9rest\n')  # continuation + rest arrive
os.close(w)
log("step5: wrote A9rest and closed write end")

sh.run_command(f"mapfile -u {FD} arr")
log("step6: mapfile returned")

val = sh.state.get_variable('arr')
elem = val[0] if val else None
log("mapfile stored arr[0] =", repr(elem))
log("  code points:", [hex(ord(c)) for c in elem] if elem else None)
log("  == correct 'érest\\n':", elem == 'érest\n')
log("  starts with two surrogates \\udcc3\\udca9:", bool(elem) and elem.startswith('\udcc3\udca9'))
log("  byte round-trip to c3 a9 ...:",
    bool(elem) and elem.encode('utf-8', 'surrogateescape') == b'\xc3\xa9rest\n')
