"""C153 PTY leg: realistic-terminal prompt numbers for bash 5.3.15 and psh.

Spawns each shell interactively under a pty with PS1='[\\#]$ ', types a few
commands, and prints the prompts observed. Run from a fresh mktemp -d with
PWD/OLDPWD unset (the caller does that); PYTHONPATH must point at the tree.
"""
import os
import pty
import re
import select
import sys
import time

TREE = os.environ.get("PSH_TREE", "/Users/pwilson/src/psh-w0d")
BASH = "/opt/homebrew/bin/bash"

COMMANDS = ["true", "echo one", "echo two", "echo \"${PS1@P}\"", "exit"]


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
    for cmd in COMMANDS:
        os.write(fd, (cmd + "\n").encode())
        pump(time.time() + 0.8)
    pump(time.time() + 0.5)
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    text = out.decode("utf-8", "replace")
    text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
    prompts = re.findall(r"\[(\d+)\]\$", text)
    print(f"{label}: prompts={prompts}")
    m = re.findall(r"^(\d+) \$", text, re.M)
    for line in text.splitlines():
        if "${PS1@P}" not in line and re.match(r"^\[\d+\]\$ ?$|^\[\d+\]\$ \S", line) is None and re.match(r"^\d+ \$", line):
            pass
    # The `echo "${PS1@P}"` line's OUTPUT is a prompt-looking line not followed by a command.
    lines = [ln for ln in text.splitlines() if re.match(r"^\[\d+\]\$\s*$", ln.strip())]
    print(f"{label}: standalone prompt-shaped lines (the ${{PS1@P}} echo + final prompt) = {[ln.strip() for ln in lines]}")
    return prompts


base_env = {k: v for k, v in os.environ.items() if k not in ("PWD", "OLDPWD")}
base_env["TERM"] = "dumb"
base_env["PS1"] = "[\\#]$ "
base_env["HISTFILE"] = "/dev/null"
bash_env = dict(base_env)
psh_env = dict(base_env, PYTHONPATH=TREE, PSH_STRICT_ERRORS="1")

drive([BASH, "--norc", "--noprofile", "-i"], bash_env, "bash 5.3.15")
drive([sys.executable, "-m", "psh", "--norc", "-i"], psh_env, "psh")
