"""C153 PTY leg with nested reads (bounce B2), independent construction.

Interactive bash 5.3.15 and psh under a pty with PS1='#\\## '; the typed lines
include eval, source, a command substitution and a function call, each echoing
${PS1@P} from inside the nested read.  Prints the prompt numbers seen and every
"tag:#N#" line the nested commands printed.
"""
import os
import pty
import re
import select
import sys
import time

TREE = os.environ.get("PSH_TREE", "/Users/pwilson/src/psh-w0d")
BASH = "/opt/homebrew/bin/bash"
LINES = [
    'echo "top:${PS1@P}"',
    'eval \'echo "ev:${PS1@P}"; true; true\'',
    'source ./inc.sh',
    'x=$(echo "cs:${PS1@P}"; true); echo "$x"',
    'f() { echo "fn:${PS1@P}"; true; }; f',
    'echo "end:${PS1@P}"',
    'exit',
]


def drive(argv, env, label):
    pid, fd = pty.fork()
    if pid == 0:
        os.execve(argv[0], argv, env)
    out = b""

    def pump(deadline):
        nonlocal out
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    return
                if not chunk:
                    return
                out += chunk

    pump(time.time() + 1.5)
    for line in LINES:
        os.write(fd, (line + "\n").encode())
        pump(time.time() + 0.8)
    pump(time.time() + 0.5)
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", out.decode("utf-8", "replace"))
    text = re.sub(r"\x1b\][^\x07]*\x07", "", text)   # OSC title writes (psh)
    text = text.replace("\r", "")
    prompts = re.findall(r"^#(\d+)# ", text, re.M)
    tags = re.findall(r"(\w+):#(\d+)#", text)
    print(f"{label}: prompts={prompts}")
    print(f"{label}: nested={[f'{t}:{n}' for t, n in tags]}")
    if os.environ.get("RAW"):
        print(f"{label}: RAW={text!r}")


with open("inc.sh", "w") as f:
    f.write('echo "src:${PS1@P}"\n')
base = {k: v for k, v in os.environ.items() if k not in ("PWD", "OLDPWD")}
base.update(TERM="xterm", PS1="#\\## ", HISTFILE="/dev/null")
drive([BASH, "--norc", "--noprofile", "-i"], dict(base), "bash 5.3.15")
drive([sys.executable, "-m", "psh", "--norc", "-i"], dict(base, PYTHONPATH=TREE, PSH_STRICT_ERRORS="1"), "psh")
