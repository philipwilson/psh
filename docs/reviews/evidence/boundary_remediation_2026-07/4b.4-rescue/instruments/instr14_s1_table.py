"""INSTR14 — the D-4B.2-s1 bash table the brief asked for and I never produced.

Brief Phase A item 2: "timeout-partial assignment across -N/-n/plain x
pipe/tty x complete-vs-partial chars x what bash assigns". Round 1 shipped
-N-ONLY evidence, and the user-guide sentence generalises to every `read -t`
form — so the doc currently rests on one eighth of its claim. BL-4.

Axes actually varied here:
  FORM      -N 2 | -n 2 | plain (no count)
  CHANNEL   pipe | tty (PTY)
  INPUT     partial multibyte (lead byte only) | complete char | plain ASCII
  MEASURED  rc, what the variable holds (hex), what the NEXT read gets (hex)

Validity control on every row: rc must be 142 on the timeout arms in BOTH
shells. A row that did not time out is not evidence about timeouts, and
without the control a mis-built script reads as agreement.

The second read is what makes this a table about the CONTRACT rather than
about one variable: psh holds the partial and resumes it, so the pair
(v, w) is where the two shells differ, while the CONCATENATION v+w is where
they must agree (no byte lost either way).

Run:  python tmp/w4b4/instr14_s1_table.py
"""
import os
import pty
import re
import select
import subprocess
import sys
import termios
import time

REPO = "/Users/pwilson/src/psh-r4b-4"
BASH = ["/opt/homebrew/bin/bash"]
PSH = [sys.executable, "-m", "psh"]
TIMEOUT = 1.0
LATE = 2.0

sys.path.insert(0, REPO)
import psh  # noqa: E402
assert psh.__file__ == REPO + "/psh/__init__.py"
print("DISCRIMINATOR:", psh.__file__)
print("ORACLE:", subprocess.run(BASH + ["--version"], capture_output=True,
                                text=True).stdout.splitlines()[0])
print()


def env():
    return {"HOME": os.environ["HOME"], "PATH": os.environ["PATH"],
            "PYTHONPATH": REPO, "TERM": "dumb",
            "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}


def script(form):
    """A timed read, then a second read, reporting rc and both values in hex."""
    read1 = {"-N": f"read -t {TIMEOUT} -N 2 v",
             "-n": f"read -t {TIMEOUT} -n 2 v",
             "plain": f"read -t {TIMEOUT} v"}[form]
    return (f'{read1}; rc1=$?; read -t {LATE} -N 1 w; rc2=$?; '
            'printf "rc1=%s rc2=%s v=" "$rc1" "$rc2"; '
            "printf '%s' \"$v\" | od -An -tx1 | tr -d ' \\n'; "
            'printf " w="; '
            "printf '%s' \"$w\" | od -An -tx1 | tr -d ' \\n'; printf '\\n'")


def run_pipe(argv, form, phase1, phase2):
    r, w = os.pipe()
    p = subprocess.Popen(argv + ["-c", script(form)], stdin=r,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         cwd=REPO, env=env())
    os.close(r)
    os.write(w, phase1)
    out = b""
    try:
        time.sleep(LATE)
        if phase2:
            try:
                os.write(w, phase2)
            except OSError:
                pass
        out, _ = p.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        return "HUNG"
    finally:
        try:
            os.close(w)
        except OSError:
            pass
    for line in out.decode("utf-8", "backslashreplace").splitlines():
        if line.startswith("rc1="):
            return line
    return f"NO-REPORT {out!r}"


def run_tty(argv, form, phase1, phase2):
    """Same cell on a PTY — the channel the -N/-t interaction is most likely
    to differ on, and the arm round 1 never ran in any form."""
    pid, fd = pty.fork()
    if pid == 0:
        os.execve(argv[0], argv + ["-c", script(form)], env())
        os._exit(127)
    out = b""
    try:
        # DISABLE ECHO. Without this the tty echoes the fed bytes back into
        # the same stream the report is read from, so the report line arrives
        # with input bytes glued to its front and every tty row is garbage
        # that still parses. (Instrument defect, self-caught: the first run of
        # this table reported tty divergences that were pure echo.)
        try:
            attrs = termios.tcgetattr(fd)
            attrs[3] &= ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
        except termios.error:
            pass
        os.write(fd, phase1)
        deadline = time.time() + LATE
        while time.time() < deadline:
            rl, _, _ = select.select([fd], [], [], 0.1)
            if rl:
                try:
                    out += os.read(fd, 4096)
                except OSError:
                    break
        if phase2:
            try:
                os.write(fd, phase2)
            except OSError:
                pass
        end = time.time() + 8
        while time.time() < end:
            rl, _, _ = select.select([fd], [], [], 0.2)
            if not rl:
                continue
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            # Wait for the COMPLETE line, not merely its prefix: breaking on
            # "rc1=" truncated every report mid-field and made v/w read empty.
            if re.search(rb"rc1=.*?\r?\n", out):
                break
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.waitpid(pid, 0)
        except OSError:
            pass
    text = out.decode("utf-8", "backslashreplace")
    # Search ANYWHERE, not at line-start: psh's `read` echoes the characters
    # it consumes even when the tty driver's ECHO is off, so the report is
    # preceded by the fed bytes on the same line. That echo difference is
    # adjacent to successor row D-4B.2-s3 (read's tty echo) and is NOT this
    # slot's subject — it is flagged, not absorbed, and it must not be allowed
    # to masquerade as an s1 finding by making psh's rows unparseable.
    m = re.search(r"rc1=\d+ rc2=\d+ v=[0-9a-f]* w=[0-9a-f]*", text)
    return m.group(0) if m else f"NO-REPORT {out!r}"


CASES = [
    # (label, phase1, phase2, expect_timeout)
    ("partial multibyte (lead only)", b"\xc3", b"\xa9Z\n", True),
    ("complete char, count unmet", "é".encode(), b"Z\n", True),
    ("plain ASCII, count unmet", b"A", b"Z\n", True),
]

ROWS = []
for channel, runner in (("pipe", run_pipe), ("tty", run_tty)):
    for form in ("-N", "-n", "plain"):
        for label, p1, p2, want_to in CASES:
            argvs = {"psh": PSH, "bash": BASH}
            got = {}
            for name, argv in argvs.items():
                got[name] = runner(argv, form, p1, p2)
            ROWS.append((channel, form, label, got["psh"], got["bash"]))
            print(f"[{channel:4}] {form:5} {label}")
            print(f"          psh : {got['psh']}")
            print(f"          bash: {got['bash']}")
            valid = ("rc1=142" in got["psh"] and "rc1=142" in got["bash"])
            print(f"          VALIDITY (both rc1=142): {valid}"
                  f"{'' if valid or not want_to else '   <-- NOT A TIMEOUT ROW'}")
            print()

print("=" * 78)
print("SUMMARY — does psh's (v,w) split differ from bash, and is v+w conserved?")
print("=" * 78)
for channel, form, label, p, b in ROWS:
    def parts(line):
        # Anchored fields. The first version split on "v=" and took the next
        # whitespace token, which for an EMPTY v grabbed "w=..." instead —
        # making every conserved-byte comparison wrong in exactly the rows
        # that matter most. (Instrument defect, self-caught.)
        m = re.search(r"\bv=([0-9a-f]*)\s+w=([0-9a-f]*)\s*$", line)
        return (m.group(1), m.group(2)) if m else ("?", "?")
    pv, pw = parts(p)
    bv, bw = parts(b)
    split_differs = (pv, pw) != (bv, bw)
    conserved = (pv + pw) == (bv + bw)
    print(f"{channel:4} {form:5} {label:32} "
          f"split_differs={str(split_differs):5} conserved={conserved}")
