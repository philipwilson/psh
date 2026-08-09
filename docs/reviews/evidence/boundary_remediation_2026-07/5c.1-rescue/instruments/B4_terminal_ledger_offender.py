#!/usr/bin/env python3
"""B4 — offender proof for the terminal-handler ledger.

Three arms, each asserting the FAILURE REASON and not merely that something
failed (5B.1 lesson 2):

  O1  a REAL unclassified terminal handler planted in the production tree is
      caught by test_no_unclassified_terminal_handler;
  O2  a stale ledger entry (a classified handler whose site changed) is caught
      by test_ledger_has_no_stale_entries;
  C1  CONTROL — with nothing planted, the suite is green.

The plant is written into the tree and REMOVED in a finally, with the file's
pre-state md5 checked on the way back out (never leave a seeded defect past its
instrument). ROOT from argv[1].
"""
import hashlib
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(sys.argv[1])
TARGET = os.path.join(ROOT, "psh/utils/signal_utils.py")
LEDGER = os.path.join(ROOT, "tests/unit/tooling/test_terminal_except_ledger_5c1.py")
NODE = "tests/unit/tooling/test_terminal_except_ledger_5c1.py"


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def run(node):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-m", "pytest", node, "-q"],
                          cwd=ROOT, capture_output=True, text=True, env=env)


def arm(label, path, anchor, repl, node, expect_pattern):
    src = open(path, encoding="utf-8").read()
    before = md5(path)
    assert src.count(anchor) == 1, f"{label}: anchor not unique ({src.count(anchor)})"
    open(path, "w", encoding="utf-8").write(src.replace(anchor, repl, 1))
    try:
        r = run(node)
        bit = r.returncode != 0
        right = bool(re.search(expect_pattern, r.stdout + r.stderr))
        verdict = ("BITES (own reason)" if bit and right else
                   "BITES (WRONG REASON)" if bit else "DID NOT BITE")
        print(f"{label:52s} {verdict}")
        for ln in r.stdout.splitlines():
            if "AssertionError" in ln or "NEW terminal" in ln or "no live" in ln:
                print(f"     {ln.strip()[:110]}")
                break
    finally:
        open(path, "w", encoding="utf-8").write(src)
        assert md5(path) == before, f"{label}: FAILED TO RESTORE {path}"
    return bit and right


print("=== CONTROL: clean tree ===")
r = run(NODE)
print(f"  clean suite: {'GREEN' if r.returncode == 0 else 'RED'} "
      f"({r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ''})")

print("\n=== OFFENDER ARMS ===")
ok1 = arm("O1 unclassified handler planted in psh/", TARGET,
          # PLANT DEFECT FOUND AND FIXED: the first anchor was
          # "class SignalHandlerRecord", which is preceded by an @dataclass
          # DECORATOR -- inserting a function there bound the decorator to the
          # planted function and broke the module at import, so conftest failed
          # and the guard never ran at all. The arm "bit", but for a collection
          # error rather than its own reason, which is exactly what the
          # reason-assert exists to catch. SignalNotifier is undecorated.
          "class SignalNotifier:",
          "def _zzz_planted_offender():\n"
          "    try:\n"
          "        _zzz_risky()\n"
          "    except Exception:\n"
          "        return 1\n\n\nclass SignalNotifier:",
          f"{NODE}::test_no_unclassified_terminal_handler",
          r"NEW terminal")

ok2 = arm("O2 stale ledger entry (site renamed)", TARGET,
          "    def __del__(self):",
          "    def __del___renamed(self):",
          f"{NODE}::test_ledger_has_no_stale_entries",
          r"no live counterpart")

print("\n=== POST-STATE ===")
r = run(NODE)
print(f"  suite after restore: {'GREEN' if r.returncode == 0 else 'RED'}")
print(f"  arms biting for their own reason: {sum([ok1, ok2])}/2")
sys.exit(0 if (ok1 and ok2 and r.returncode == 0) else 1)
