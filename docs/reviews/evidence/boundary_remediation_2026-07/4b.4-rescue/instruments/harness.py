"""A0 — the marker-anchored two-phase feed harness (shared by the census).

Why this exists (defect ID-1): a two-phase probe that schedules phase 2 off
the PARENT's wall clock is anchored to the wrong timeline. bash starts in
milliseconds; `python -m psh` takes an order of magnitude longer, so the
same delay lands at a different point in each shell's read sequence, and a
cell can diverge for timing reasons that look exactly like semantics.

Fix: the CHILD announces when it is about to enter the read sequence (it
touches a marker file), and every phase is scheduled relative to THAT
instant. The shells are then compared at the same logical position.

Hygiene (brief §Slot-specific test hygiene): deadlines >= 1s; writer is a
threading.Timer with a bounded join; hang detection at >= 4x the expected
runtime; every stimulus reports whether it was VALID.
"""
import os
import subprocess
import sys
import time

REPO = '/Users/pwilson/src/psh-r4b-4'
BASH = ['/opt/homebrew/bin/bash']
PSH = [sys.executable, '-m', 'psh']


def env(extra=None):
    e = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
         'PYTHONPATH': REPO, 'TERM': 'dumb'}
    if extra:
        e.update(extra)
    return e


def discriminate():
    """Assert BOTH the parent's and a child's `psh` resolve to THIS tree.

    Banked strengthening of 4B.2 lesson 4 (R1): the parent's import says
    nothing about what `python -m psh` resolves in a child.
    """
    sys.path.insert(0, REPO)
    import psh
    assert psh.__file__ == REPO + '/psh/__init__.py', psh.__file__
    d = subprocess.run([sys.executable, '-c', 'import psh; print(psh.__file__)'],
                       cwd=REPO, env=env(), capture_output=True, text=True)
    resolved = d.stdout.strip()
    assert resolved == REPO + '/psh/__init__.py', f"CHILD RESOLVED {resolved!r}"
    ver = subprocess.run(BASH + ['--version'], capture_output=True,
                         text=True).stdout.splitlines()[0]
    print(f"DISCRIMINATOR parent+child: {resolved}")
    print(f"ORACLE: {ver}")
    return resolved, ver


def feed(argv, script, phases, marker, extra_env=None, hang=20):
    """Run `argv -c script` feeding `phases` anchored to the CHILD's marker.

    `phases` is a list of (offset_seconds_after_marker, bytes). The script
    MUST touch `marker` immediately before its read sequence.
    `argv` is explicit (never a bare string) — the zsh unquoted-$var 127 trap.
    Returns (stdout_bytes, 'OK'|'HUNG'|'NOMARKER').
    """
    if os.path.exists(marker):
        os.unlink(marker)
    r, w = os.pipe()
    p = subprocess.Popen(argv + ['-c', script], stdin=r,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         cwd=REPO, env=env(extra_env))
    os.close(r)
    status = 'OK'
    try:
        # Wait for the child to announce it is entering the read sequence.
        t_wait = time.monotonic()
        while not os.path.exists(marker):
            if time.monotonic() - t_wait > hang / 2:
                status = 'NOMARKER'
                break
            time.sleep(0.005)
        t0 = time.monotonic()
        for offset, data in phases:
            delay = t0 + offset - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            try:
                os.write(w, data)
            except OSError:
                pass
        out, err = p.communicate(timeout=hang)
        return out, (status if status != 'OK' else ('OK' if p.returncode is not None else 'OK'))
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        return b'', 'HUNG'
    finally:
        try:
            os.close(w)
        except OSError:
            pass


def show(label, out, status):
    print(f"  {label:<26} [{status}] {out!r}")
    return out
