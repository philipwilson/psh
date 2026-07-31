#!/usr/bin/env python3
"""ROUND-6 BLOCKER 1, reproduced independently (ruling R12-E).

The slot's central latency claim was that `echo \\<<EOF` is observable only at
a terminal, so a `-c` pin would be green-on-base and prove nothing. Round 6
found that FALSE for `--parser combinator`: at base the session's regex opened
a phantom heredoc, so the following physical lines joined ONE buffer and the
combinator stamped every top-level statement with that buffer's start line; at
tip each line is its own buffer, so the line numbers in the diagnostics those
swallowed lines emit become correct (= bash).

I am not taking that on trust. This probe re-derives it from scratch:

  * probe FILES, never `-c` one-liners with shell quoting in the way (the
    brief's rule -- `\\<<` is escape-sensitive and a `-c` smoke probe
    false-alarmed on zsh quoting as recently as v0.760.0); every file is
    od -c dumped in the transcript so the bytes are auditable;
  * all three non-interactive channels x both parsers x both SHAs;
  * bash 5.2.26 at /opt/homebrew/bin/bash (never /bin/bash) as the oracle;
  * an IMPORT DISCRIMINATOR per row: each psh run prints the psh package file
    it actually imported, so a PYTHONPATH that silently resolved to the wrong
    tree cannot masquerade as a behaviour result;
  * the CAUSAL CONTROL: the same probe run against a shape with NO heredoc
    operator at all, to separate "the session stopped merging lines" from
    "the 2.2 combinator line-stamping carry changed". The carry must be
    base-identical.

Usage: python3 escaped_combinator_delta.py <base_tree> <tip_tree> <outfile>
"""
import pathlib
import subprocess
import sys
import tempfile

BASH = "/opt/homebrew/bin/bash"

# label -> exact BYTES. Follow-up lines EMIT DIAGNOSTICS -- that is the axis
# the identity corpus never varied (its escaped_lt case follows up with
# `echo MARK""ER`, which prints and says nothing about which line it was on).
CASES = {
    "escaped_lt_diag":        b"echo \\<<E\nhello\nE\n",
    "escaped_lt_quoted_diag": b"echo \\<<'E'\nhello\nE\n",
    "escaped_lt_strip_diag":  b"echo \\<<-E\nhello\nE\n",
    "escaped_lt_digit_diag":  b"echo 0\\<<E\nhello\nE\n",
    # CONTROLS -----------------------------------------------------------
    # A TRUE heredoc: the body really is swallowed, at both SHAs and in bash.
    "true_heredoc_ctl":       b"cat <<E\nhello\nE\nnosuchcmd\n",
    # No heredoc operator anywhere: isolates the 2.2 combinator top-level
    # line-stamping carry. If THIS moves, the delta is not what I think.
    "no_heredoc_ctl":         b"if true; then\nnosuchcmd\nfi\nnosuchcmd2\n",
}

DISCRIMINATOR = "import psh, sys; sys.stderr.write('IMPORTED ' + psh.__file__ + '\\n')"


def sha(tree):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=tree,
                          capture_output=True, text=True).stdout.strip()


def env_for(tree):
    return {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp",
            "PYTHONPATH": tree, "PYTHONUNBUFFERED": "1"}


def discriminate(tree, sandbox):
    """Prove which psh package this tree's PYTHONPATH actually imports."""
    p = subprocess.run([sys.executable, "-c", DISCRIMINATOR], cwd=sandbox,
                       env=env_for(tree), capture_output=True, text=True)
    got = p.stderr.strip()
    return got, got.startswith(f"IMPORTED {tree}/psh/")


def run_psh(tree, parser, channel, raw, sandbox):
    argv = [sys.executable, "-m", "psh", "--norc", "--parser", parser]
    stdin_bytes = None
    scriptname = None
    if channel == "dash_c":
        argv += ["-c", raw.decode()]
    elif channel == "script":
        with tempfile.NamedTemporaryFile("wb", suffix=".sh", dir=sandbox,
                                         delete=False) as tf:
            tf.write(raw)
        scriptname = tf.name
        argv += [scriptname]
    else:
        stdin_bytes = raw
    p = subprocess.run(argv, input=stdin_bytes, capture_output=True,
                       cwd=sandbox, env=env_for(tree), timeout=30)
    err = p.stderr.decode(errors="replace")
    if scriptname:
        err = err.replace(scriptname, "<SCRIPT>")
        err = err.replace(scriptname.rsplit("/", 1)[-1], "<SCRIPT>")
    return p.returncode, p.stdout.decode(errors="replace"), err


def run_bash(raw, sandbox):
    with tempfile.NamedTemporaryFile("wb", suffix=".sh", dir=sandbox,
                                     delete=False) as tf:
        tf.write(raw)
    p = subprocess.run([BASH, tf.name], capture_output=True, cwd=sandbox,
                       timeout=30)
    err = p.stderr.decode(errors="replace")
    err = err.replace(tf.name, "<SCRIPT>")
    err = err.replace(tf.name.rsplit("/", 1)[-1], "<SCRIPT>")
    return p.returncode, p.stdout.decode(errors="replace"), err


def main():
    base_tree, tip_tree, outfile = sys.argv[1], sys.argv[2], sys.argv[3]
    sandbox = tempfile.mkdtemp()
    L = []

    bashver = subprocess.run([BASH, "--version"], capture_output=True,
                             text=True).stdout.splitlines()[0]
    L.append("# ROUND-6 BLOCKER 1 reproduced independently (R12-E)")
    L.append(f"# base tree: {base_tree}  SHA: {sha(base_tree)}")
    L.append(f"# tip  tree: {tip_tree}  SHA: {sha(tip_tree)}")
    L.append(f"# oracle: {bashver}  ({BASH})")

    L.append("\n## IMPORT DISCRIMINATOR")
    ok_all = True
    for tree in (base_tree, tip_tree):
        got, ok = discriminate(tree, sandbox)
        ok_all &= ok
        L.append(f"  {'OK ' if ok else 'BAD'} {tree} -> {got}")
    if not ok_all:
        L.append("  FATAL: a tree did not import its own psh -- results void.")
        pathlib.Path(outfile).write_text("\n".join(L) + "\n")
        print("\n".join(L))
        return 2

    L.append("\n## PROBE BYTES (od -c)")
    for label, raw in CASES.items():
        f = pathlib.Path(sandbox) / f"{label}.in"
        f.write_bytes(raw)
        od = subprocess.run(["od", "-c", str(f)], capture_output=True,
                            text=True).stdout.strip()
        L.append(f"  {label}:")
        for ln in od.splitlines():
            L.append(f"    {ln}")

    deltas = identical = 0
    L.append("\n## ROWS  (base vs tip, and each against bash)")
    for label, raw in CASES.items():
        L.append(f"\n### {label}")
        b_rc, b_out, b_err = run_bash(raw, sandbox)
        L.append(f"  bash   rc={b_rc} out={b_out!r} err={b_err!r}")
        for channel in ("dash_c", "script", "stdin"):
            for parser in ("rd", "combinator"):
                base = run_psh(base_tree, parser, channel, raw, sandbox)
                tip = run_psh(tip_tree, parser, channel, raw, sandbox)
                same = base == tip
                identical += same
                deltas += not same
                tag = "IDENTICAL" if same else "DELTA    "
                L.append(f"  [{tag}] chan={channel:7} parser={parser}")
                if not same:
                    L.append(f"      base={base!r}")
                    L.append(f"      tip ={tip!r}")
                    L.append(f"      bash={(b_rc, b_out, b_err)!r}")
                    L.append(f"      tip==bash? "
                             f"{tip == (b_rc, b_out, b_err)}")

    L.append(f"\n## TOTALS rows={identical+deltas} identical={identical} "
             f"deltas={deltas}")
    pathlib.Path(outfile).write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
