#!/usr/bin/env python3
"""R8-B: the ORDINARY-ERREXIT co-movement hunt, enumerated rather than sampled.

Round 7 declared two co-movement families and pinned seven rows of them. The
ruling asks for the full enumeration as a durable instrument, so the pin's
sample can point at the exhaustive record instead of standing for it.

The space: {suppression source} x {route} x {body shape} x {channel}, each row
an ORDINARY errexit observation with NO substitution syntax error anywhere.
Every row is classified against bash and against the wave base:

  MOVED-TO-BASH   base != bash, tip == bash   (a declared co-movement)
  UNMOVED-MATCH   base == bash == tip         (a control: shapes that do NOT move)
  UNMOVED-DIVERGE base == tip != bash         (pre-existing, outside the families)
  MOVED-AWAY      tip != bash and base == bash (a regression — none expected)

Run with a base worktree path as argv[1] to fill the base column; without it,
the base column reads NA and only tip-vs-bash is classified.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import BASH, _env, discriminator  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-r8b")
BASE_TREE = sys.argv[1] if len(sys.argv) > 1 else None

# The failing-command bodies an ordinary-errexit observation can carry.
BODIES = {
    "eval_text": "eval 'false; echo A'",
    "source_text": ". ./fbody.sh",
    "plain_false": "false; echo A",
    "func_call": "ff",
}
# The routes a body can be reached through.
ROUTES = {
    "member_simple": "{{ true | {body}; }}",
    "member_brace": "{{ true | {{ {body}; }}; }}",
    "member_prefix_cmd": "{{ true | command {body}; }}",
    "member_prefix_assign": "{{ true | X=1 {body}; }}",
    "bg_bare": "{{ {body} & }}",
    "bg_subshell": "{{ ( {body} ) & }}",
    "bg_brace": "{{ {{ {body}; }} & }}",
    "fg_subshell": "( {body} )",
}
# The contexts that suppress errexit.
SOURCES = {
    "orlist": "set -e\n{cmd} || echo GOT rc=$?",
    "ifcond": "set -e\nif {cmd}; then echo T; else echo GOT rc=$?; fi",
    "negate": "set -e\n! {cmd}\necho AFTER rc=$?",
    "whilecond": "set -e\nwhile {cmd}; do break; done\necho AFTER rc=$?",
    "andand": "set -e\n{cmd} && echo T\necho AFTER rc=$?",
    "unsuppressed": "set -e\n{cmd}\necho AFTER rc=$?",
}
PRELUDE = ("printf '%s\\n' 'false' 'echo A' > fbody.sh\n"
           "ff() { false; echo A; }\n")
TAIL = "\necho END\n"


def build():
    rows = {}
    for bname, body in BODIES.items():
        for rname, route in ROUTES.items():
            if bname == "func_call" and rname == "member_prefix_cmd":
                continue          # `command ff` bypasses the function
            cmd = route.format(body=body)
            for sname, src in SOURCES.items():
                script = PRELUDE + src.format(cmd=cmd) + TAIL
                rows[f"{bname}__{rname}__{sname}"] = script.encode()
    return rows


def run_one(argv, path, cwd):
    try:
        r = subprocess.run(argv, capture_output=True, cwd=cwd, env=_env(),
                           timeout=25)
    except subprocess.TimeoutExpired:
        return ("TIMEOUT", "")
    return (r.returncode, r.stdout.decode(errors="replace"))


def main():
    os.makedirs(WORK, exist_ok=True)
    print("discriminator:", discriminator(WORK))
    print("base tree:", BASE_TREE or "NA")
    rows = build()
    counts = {}
    for name, body in sorted(rows.items()):
        path = os.path.join(WORK, name + ".sh")
        with open(path, "wb") as f:
            f.write(body)
        b = run_one([BASH, path], path, WORK)
        t = run_one([sys.executable, "-m", "psh", path], path, WORK)
        if BASE_TREE:
            env = dict(os.environ)
            env["PYTHONPATH"] = BASE_TREE
            r = subprocess.run([sys.executable, "-m", "psh", path],
                               capture_output=True, cwd=WORK, env=env,
                               timeout=25)
            base = (r.returncode, r.stdout.decode(errors="replace"))
        else:
            base = None
        # A BACKGROUND child writes to the same stdout as its parent, so the
        # INTERLEAVING of its output is scheduling, not behaviour: bash's `A`
        # commonly lands after `END` where psh's lands before. Comparison is
        # therefore over the LINE MULTISET; a row whose raw order differed is
        # flagged ORDER-RACY so the domain is visible rather than silently
        # normalised away. (The first version of this instrument compared
        # ordered stdout and mis-sorted 8 such rows.)
        def norm(x):
            return (x[0], tuple(sorted(x[1].splitlines()))) if x else None
        racy = ""
        if base is not None and (norm(b) == norm(t)) and b != t:
            racy = "  [ORDER-RACY]"
        b, t = norm(b), norm(t)
        base = norm(base)
        if base is None:
            verdict = "MATCH" if t == b else "DIVERGE"
        elif base != b and t == b:
            verdict = "MOVED-TO-BASH"
        elif base == b == t:
            verdict = "UNMOVED-MATCH"
        elif base == t != b:
            verdict = "UNMOVED-DIVERGE"
        elif base == b != t:
            verdict = "MOVED-AWAY"
        else:
            verdict = "OTHER"
        counts[verdict] = counts.get(verdict, 0) + 1
        print(f"{verdict:16s} {name:46s}{racy} bash={b[1]!r} base="
              f"{(base[1] if base else 'NA')!r} tip={t[1]!r}")
        sys.stdout.flush()
    print("=" * 72)
    print("ROWS:", len(rows))
    for k in sorted(counts):
        print(f"  {k:16s} {counts[k]}")


if __name__ == "__main__":
    main()
