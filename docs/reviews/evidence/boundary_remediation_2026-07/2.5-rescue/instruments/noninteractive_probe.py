#!/usr/bin/env python3
"""The A5 latency claim, checked rather than assumed: are `-c`, script-file
and stdin GREEN ON BASE for the same bytes that are red under a PTY?

Feeds each input file (the SAME bytes the PTY driver sends) through all three
non-interactive channels to bash and to psh (both parsers) and diffs
stdout/stderr-shape/status. Runs one subprocess per (case, channel, shell)
row -- individual-run protocol.

Usage: python3 noninteractive_probe.py <outfile>
"""
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
PSH_ROOT = str(HERE.parents[1])
ORACLE = "/opt/homebrew/bin/bash"


def run(argv, stdin_bytes=None, cwd=None):
    p = subprocess.run(argv, input=stdin_bytes, capture_output=True,
                       cwd=cwd, timeout=20)
    return (p.returncode, p.stdout.decode(errors="replace"),
            p.stderr.decode(errors="replace"))


def channels(shell, parser, script_path, raw, sandbox):
    base = ([ORACLE, "--norc"] if shell == "bash"
            else [sys.executable, "-m", "psh", "--norc", "--parser", parser])
    return {
        "dash_c": lambda: run(base + ["-c", raw.decode()], cwd=sandbox),
        "script": lambda: run(base + [str(script_path)], cwd=sandbox),
        "stdin": lambda: run(base, stdin_bytes=raw, cwd=sandbox),
    }


def norm(err, shell):
    """Compare the SHAPE of stderr, not its wording: the two shells word the
    same failure differently ('EOF: No such file or directory')."""
    return "ENOENT" if "No such file or directory" in err else (
        "WARN_EOF" if "delimited by end-of-file" in err else
        ("ERR" if err.strip() else ""))


def main():
    out = open(sys.argv[1], "w")
    sandbox = str(HERE / "sandbox")
    pathlib.Path(sandbox).mkdir(exist_ok=True)
    print(f"# SHA: {subprocess.run(['git','rev-parse','HEAD'],cwd=PSH_ROOT,capture_output=True,text=True).stdout.strip()}", file=out)
    rows = agree = differ = 0
    for f in sorted((HERE / "inputs").glob("*.in")):
        raw = f.read_bytes()
        with tempfile.NamedTemporaryFile("wb", suffix=".sh", dir=sandbox,
                                         delete=False) as tf:
            tf.write(raw)
            script = pathlib.Path(tf.name)
        for chan in ("dash_c", "script", "stdin"):
            b = channels("bash", "-", script, raw, sandbox)[chan]()
            bkey = (b[0], b[1], norm(b[2], "bash"))
            for parser in ("rd", "combinator"):
                p = channels("psh", parser, script, raw, sandbox)[chan]()
                pkey = (p[0], p[1], norm(p[2], "psh"))
                same = bkey == pkey
                rows += 1
                agree += same
                differ += (not same)
                print(f"ROW case={f.stem} chan={chan} parser={parser} "
                      f"agree={same} bash={bkey!r} psh={pkey!r}", file=out)
        script.unlink()
    print(f"# TOTALS rows={rows} agree={agree} differ={differ}", file=out)
    out.close()
    print(open(sys.argv[1]).read())


if __name__ == "__main__":
    main()
