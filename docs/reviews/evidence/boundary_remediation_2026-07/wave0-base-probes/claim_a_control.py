import sys, os, threading, time, subprocess, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import psh.version
assert psh.version.__version__ == '0.750.0', psh.version.__version__

d = tempfile.mkdtemp(dir=os.path.join(ROOT, 'tmp'))
fifo = os.path.join(d, 'f')
os.mkfifo(fifo)

def writer():
    wf = os.open(fifo, os.O_WRONLY)
    os.write(wf, b'\xc3\xa9\n')   # WHOLE character delivered together (no split)
    os.close(wf)

t = threading.Thread(target=writer); t.start()
# No read -t here: mapfile reads the whole thing via read_all in one go.
script = (
    'exec 7< %s\n'
    'mapfile -u 7 arr\n'
    'printf "charcount=%%s\\n" "${#arr[0]}"\n'
    'printf "%%s" "${arr[0]}" | od -An -tx1\n'
) % fifo
p = subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                   cwd=ROOT, capture_output=True, text=True)
t.join()
print("=== CONTROL: C3 A9 delivered together (no seam split) ===")
print(p.stdout)
print("Expect charcount=2 (é + newline) — correct single-char decode, no surrogates.")
