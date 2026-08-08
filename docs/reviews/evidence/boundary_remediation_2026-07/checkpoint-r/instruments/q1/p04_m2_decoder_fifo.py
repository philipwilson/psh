# Q1 probe 04 (MEDIUM-2): UTF-8 decoder seam, end-to-end psh subprocess.
# Fresh 0.773.0-pinned equivalent of wave0-base-probes/claim_a_fifo.py
# (committed probe is 0.750.0-pinned and must not be edited).
# Base: read -t times out holding C3; mapfile read_all decoded the tail with a
# FRESH decoder -> arr[0] = two surrogates + rest (charcount 3 for 'é\n' case).
# Tip claim (v0.771.0): ONE incremental decoder across the seam -> charcount 2.
# Axis: REGRESSION (recorded base bug) + the correctness value equals bash's.
import os
import subprocess
import sys
import threading
import time

WT = ('/private/tmp/claude-501/-Users-pwilson-src-psh/'
      '05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt')
assert os.getcwd() == WT
sys.path.insert(0, WT)
import psh.version
assert psh.version.__version__ == '0.773.0', psh.version.__version__
assert psh.version.__file__.startswith(WT)
print("DISCRIMINATOR OK:", psh.version.__version__)

d = os.path.join(WT, 'tmp', 'q1m2')
os.makedirs(d, exist_ok=True)


def run_case(name, split):
    fifo = os.path.join(d, 'f_' + name)
    if os.path.exists(fifo):
        os.unlink(fifo)
    os.mkfifo(fifo)

    def writer():
        wf = os.open(fifo, os.O_WRONLY)
        if split:
            os.write(wf, b'\xc3')      # lead byte only; read -t 0.2 times out
            time.sleep(1.0)
            os.write(wf, b'\xa9\n')    # continuation arrives for mapfile
        else:
            os.write(wf, b'\xc3\xa9\n')  # control: whole char together
        os.close(wf)

    t = threading.Thread(target=writer)
    t.start()
    # Control mirrors the committed claim_a_control.py: NO read -t (v2 fix —
    # the first composition left read -t in the control, which consumed the
    # whole char before mapfile; that was an instrument artifact, not a defect).
    if split:
        script = (
            'exec 7< %s\n'
            'read -t 0.2 -n 5 -u 7 x; echo "read-rc=$?"\n'
            'mapfile -u 7 arr\n'
            'printf "charcount=%%s\\n" "${#arr[0]}"\n'
            'printf "%%s" "${arr[0]}" | od -An -tx1\n'
        ) % fifo
    else:
        script = (
            'exec 7< %s\n'
            'mapfile -u 7 arr\n'
            'printf "charcount=%%s\\n" "${#arr[0]}"\n'
            'printf "%%s" "${arr[0]}" | od -An -tx1\n'
        ) % fifo
    p = subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                       cwd=WT, capture_output=True, text=True, timeout=30)
    t.join()
    print("=== case:", name, "(split seam)" if split else "(control, no split)")
    print("stdout:\n" + p.stdout)
    if p.stderr:
        print("stderr:\n" + p.stderr)
    ok = 'charcount=2' in p.stdout and 'c3 a9 0a' in p.stdout.replace('  ', ' ')
    print("charcount=2 and bytes c3 a9 0a:", ok)
    return ok


split_ok = run_case('split', True)
ctrl_ok = run_case('control', False)
print("SPLIT-SEAM DECODE CORRECT:", split_ok)
print("CONTROL DECODE CORRECT:", ctrl_ok)
