#!/usr/bin/env python3
"""MEASURES BASE-VS-TIP IDENTITY. It does NOT measure agreement with bash.

That sentence is the whole point of this file's existence, and it is the
round-2 lesson (blocker R7-B, axis-quantification instance #9). Its predecessor
compared psh against BASH at each SHA and I cited a 66/66 result as evidence
that non-interactive behaviour was "unchanged from base". It cannot be: two
shells can agree with bash at both SHAs while psh's own answer changed in ways
bash never sees (stderr wording, warning presence, exit paths), and it can
equally agree at both SHAs on rows where psh moved TOWARD bash. Agreement with
an oracle at two points says nothing about identity between those points.

So this instrument runs the SAME BYTES through BOTH TREES and diffs psh against
itself: exit status, stdout and stderr, exactly. Every non-identical row is a
behaviour delta that must appear in the ledger's DECLARED set.

Universe: every case file in inputs/, every non-interactive channel
(-c / script / stdin), both parsers. One subprocess per row.

Usage: python3 base_tip_identity.py <base_tree> <tip_tree> <outfile>
"""
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent


def run(tree, parser, channel, raw, sandbox):
    base = [sys.executable, "-m", "psh", "--norc", "--parser", parser]
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp",
           "PYTHONPATH": tree, "PYTHONUNBUFFERED": "1"}
    if channel == "dash_c":
        argv, stdin_bytes = base + ["-c", raw.decode()], None
    elif channel == "script":
        with tempfile.NamedTemporaryFile("wb", suffix=".sh", dir=sandbox,
                                         delete=False) as tf:
            tf.write(raw)
        argv, stdin_bytes = base + [tf.name], None
    else:
        argv, stdin_bytes = base, raw
    p = subprocess.run(argv, input=stdin_bytes, capture_output=True,
                       cwd=sandbox, env=env, timeout=30)
    out = p.stdout.decode(errors="replace")
    err = p.stderr.decode(errors="replace")
    # Script paths differ between trees (temp names), so the SCRIPT NAME is
    # normalised out of diagnostics -- otherwise every script-channel row would
    # read as a delta for a reason that is not behaviour.
    if channel == "script":
        err = err.replace(tf.name, "<SCRIPT>")
        for part in (sandbox, tf.name.rsplit("/", 1)[-1]):
            err = err.replace(part, "<SCRIPT>")
    return p.returncode, out, err


def main():
    base_tree, tip_tree, outfile = sys.argv[1], sys.argv[2], sys.argv[3]
    sandbox = tempfile.mkdtemp()
    rows = identical = differ = 0
    def sha(tree):
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=tree,
                              capture_output=True, text=True).stdout.strip()

    lines = ["# MEASURES BASE-VS-TIP IDENTITY (not agreement with bash)",
             f"# base tree: {base_tree}  SHA: {sha(base_tree)}",
             f"# tip  tree: {tip_tree}  SHA: {sha(tip_tree)}"]
    for f in sorted((HERE / "inputs").glob("*.in")):
        raw = f.read_bytes()
        for channel in ("dash_c", "script", "stdin"):
            for parser in ("rd", "combinator"):
                b = run(base_tree, parser, channel, raw, sandbox)
                t = run(tip_tree, parser, channel, raw, sandbox)
                rows += 1
                if b == t:
                    identical += 1
                else:
                    differ += 1
                    lines.append(
                        f"DELTA case={f.stem} chan={channel} parser={parser}")
                    lines.append(f"    base={b!r}")
                    lines.append(f"    tip ={t!r}")
    lines.append(f"# TOTALS rows={rows} identical={identical} differ={differ}")
    pathlib.Path(outfile).write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:3] + lines[-1:]))
    print(f"(full report: {outfile})")


if __name__ == "__main__":
    main()
