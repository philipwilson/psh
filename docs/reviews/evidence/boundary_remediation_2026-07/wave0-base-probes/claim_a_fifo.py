import sys, os, threading, time, subprocess, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import psh.version
assert psh.version.__version__ == '0.750.0', psh.version.__version__

d = tempfile.mkdtemp(dir=os.path.join(ROOT, 'tmp'))
fifo = os.path.join(d, 'f')
os.mkfifo(fifo)

def writer():
    # Blocks until psh opens the read side (exec 7< fifo).
    wf = os.open(fifo, os.O_WRONLY)
    os.write(wf, b'\xc3')      # lead byte only -> psh read -t times out here
    time.sleep(1.0)            # ... after the 0.2s read deadline has passed
    os.write(wf, b'\xa9\n')    # continuation + newline arrive for mapfile
    os.close(wf)

t = threading.Thread(target=writer)
t.start()

# read -t times out mid-multibyte (C3 buffered in the shared fd-7 cursor);
# mapfile (no -n) then drains the same cursor via read_all.
# Report the CHARACTER count and code points of arr[0]. Byte round-trip hides
# the bug on stdout, so we inspect character content, not bytes.
script = (
    'exec 7< %s\n'
    'read -t 0.2 -n 5 -u 7 x; echo "read-rc=$?"\n'
    'mapfile -u 7 arr\n'
    'printf "charcount=%%s\\n" "${#arr[0]}"\n'
    'printf "%%s" "${arr[0]}" | od -An -tx1\n'
) % fifo

p = subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                   cwd=ROOT, capture_output=True, text=True)
t.join()
print("=== Claim A end-to-end: real psh subprocess, read -t then mapfile, FIFO ===")
print("psh stdout:\n" + p.stdout)
print("psh stderr:\n" + p.stderr)
print("Correct decode of C3 A9 0A = 'é\\n' -> 2 characters (é, newline).")
print("Buggy seam decode = '\\udcc3\\udca9\\n' -> 3 characters (two surrogates + newline).")
print("od shows bytes c3 a9 0a either way (byte round-trip survives).")
