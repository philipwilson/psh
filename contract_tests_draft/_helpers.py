import os
import sys
import time
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PSH_CMD = [sys.executable, "-m", "psh"]


def run_psh_cmd(cmd: str, env=None, timeout=5):
    env = {**os.environ, **(env or {})}
    result = subprocess.run(
        PSH_CMD + ["-c", cmd],
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=timeout,
    )
    return result


@dataclass
class PtyShell:
    prompt: str = "__PSH__ "

    def __post_init__(self):
        import pytest
        pexpect = pytest.importorskip("pexpect")
        self.prompt_re = r"[$#] "
        self.child = pexpect.spawn(
            sys.executable,
            ["-m", "psh", "-i"],
            cwd=str(REPO_ROOT),
            env=os.environ.copy(),
            encoding="utf-8",
            timeout=5,
        )
        # Wait for default prompt (may include ANSI color codes)
        self.child.expect(self.prompt_re)

    def cmd(self, line: str) -> str:
        # psh line editor expects CR to accept a line; sendline() uses \n.
        self.child.send(line + "\r")
        self.child.expect(self.prompt_re)
        return self.child.before

    def sendline(self, line: str):
        """Send a line without waiting for a prompt."""
        self.child.send(line + "\r")

    def expect_prompt(self):
        """Wait for the prompt."""
        self.child.expect(self.prompt_re)

    def send_ctrl(self, ch: str):
        self.child.sendcontrol(ch)

    def close(self):
        self.child.send("exit\r")
        self.child.expect(".*", timeout=1)
        self.child.close()


def wait_brief():
    time.sleep(0.2)
