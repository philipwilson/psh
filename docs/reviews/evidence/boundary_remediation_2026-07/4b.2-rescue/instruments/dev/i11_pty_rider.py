#!/usr/bin/env python3
"""i11 — the TTY arm of the A5 rider, probed at a REAL pseudo-terminal.

BL-3: D1 committed to probing the TTY leg or declaring it NOT-PROBED with a
reason, and neither happened — while the rider fix DID change the tty arm
(`_read_exact`'s `os.isatty` raw-mode branch now receives the deadline). This
instrument supplies the missing evidence with MY OWN numbers: it drives psh and
the bash oracle through a pty and records rc, the assigned value and elapsed
time for the two cells the pin family will carry.

`read -N` takes the tty branch whenever stdin is a terminal, so `-c` under a pty
exercises it — no REPL driving needed, which keeps the cell deterministic.

Run with a tree argument to probe a specific checkout:
    python i11_pty_rider.py [<repo-root>]
"""
import os
import re
import subprocess
import sys
import time

import pexpect

BASH = '/opt/homebrew/bin/bash'
DEADLINE = 1.0
KILL_AFTER = 8.0          # 8x the deadline

REPORT = r"""rc=$?; printf 'RC=%s VAL=[%s]\n' "$rc" "$x" """
SCRIPT = f"read -t {DEADLINE} -N 3 x; {REPORT}"


def assert_tree_under_test(root, env):
    """FAIL LOUDLY unless the child really imports the tree we mean to measure.

    `python -m psh` prepends the child's CWD to sys.path, which OUTRANKS
    PYTHONPATH. A pty probe that sets PYTHONPATH but inherits the harness's cwd
    therefore measures the HARNESS's tree while claiming to measure the argument
    — silently, and in a direction that makes a base run look already-fixed.
    This probe hit exactly that: an earlier revision reported the base as
    bash-matching because it was importing the fixed worktree. Hence: cwd is
    pinned to the tree under test AND the resolved module path is verified here
    before any cell runs.
    """
    child = pexpect.spawn(
        sys.executable, ['-u', '-c',
                         'import psh.builtins.read_builtin as rb;'
                         ' print("RB=" + rb.__file__)'],
        timeout=30, encoding='utf-8', env=env, cwd=root)
    child.expect(r'RB=(\S+)')
    resolved = child.match.group(1)
    child.close(force=True)
    want = os.path.join(root, 'psh', 'builtins', 'read_builtin.py')
    if os.path.realpath(resolved) != os.path.realpath(want):
        raise SystemExit(
            f"DISCRIMINATOR FAILED: the child imports {resolved!r} but this run "
            f"claims to measure {want!r}. Refusing to report numbers for the "
            f"wrong tree.")
    return resolved


def probe(label, argv, env, root, send=None):
    """Spawn under a pty, optionally type SEND, and collect the report line."""
    t0 = time.monotonic()
    # cwd MUST be the tree under test — see assert_tree_under_test.
    child = pexpect.spawn(argv[0], argv[1:], timeout=KILL_AFTER,
                          encoding='utf-8', env=env, cwd=root)
    typed = None
    try:
        if send:
            time.sleep(0.15)      # let the read arm its deadline first
            child.send(send)
            typed = send
        child.expect(r'RC=(\d+) VAL=\[([^\]]*)\]')
        rc, val = child.match.group(1), child.match.group(2)
        outcome = f"rc={rc} val=[{val}]"
    except pexpect.TIMEOUT:
        outcome = f"HUNG(>{KILL_AFTER:.0f}s — deadline ignored at the tty)"
    except pexpect.EOF:
        outcome = f"EOF-before-report: {child.before!r}"
    finally:
        dt = time.monotonic() - t0
        try:
            child.close(force=True)
        except Exception:
            pass
    return {'label': label, 'outcome': outcome, 'dt': dt, 'typed': typed}


def main() -> int:
    root = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root,
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain', 'psh/'], cwd=root,
                           capture_output=True, text=True).stdout
    bash_ver = subprocess.run([BASH, '--version'], capture_output=True,
                              text=True).stdout.splitlines()[0]
    print("== DISCRIMINATOR ==")
    print(f"tree under test: {root}")
    print(f"HEAD:            {head}")
    print(f"psh/ dirty:      {len(dirty.splitlines())} lines")
    print(f"bash oracle:     {BASH} -> {bash_ver}")
    print(f"pexpect:         {pexpect.__version__}")
    print(f"deadline {DEADLINE}s, kill bound {KILL_AFTER}s, stdin IS a tty")
    print()

    env = {
        'PATH': '/opt/homebrew/bin:/usr/bin:/bin',
        'HOME': os.environ.get('HOME', '/tmp'),
        'TERM': 'xterm',
        'LC_ALL': 'en_US.UTF-8', 'LANG': 'en_US.UTF-8',
        'PYTHONUNBUFFERED': '1',
        'PYTHONPATH': root,
    }
    resolved = assert_tree_under_test(root, env)
    print(f"resolved psh module: {resolved}")
    print()

    psh_argv = [sys.executable, '-u', '-m', 'psh', '--norc', '-c', SCRIPT]
    bash_argv = [BASH, '--norc', '-c', SCRIPT]

    cells = [
        ("no-input", None),
        ("partial-ab-at-deadline", "ab"),
        ("full-abc-before-deadline", "abc"),
    ]
    print(f"{'CELL':<26} {'PSH':<44} {'dt':<6} {'BASH':<26} {'dt':<6} MATCH")
    print("-" * 118)
    for name, send in cells:
        p = probe(f"psh/{name}", psh_argv, env, root, send)
        b = probe(f"bash/{name}", bash_argv, env, root, send)
        match = 'SAME' if p['outcome'] == b['outcome'] else 'DIFFER'
        print(f"{name:<26} {p['outcome']:<44} {p['dt']:<6.2f} "
              f"{b['outcome']:<26} {b['dt']:<6.2f} {match}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
