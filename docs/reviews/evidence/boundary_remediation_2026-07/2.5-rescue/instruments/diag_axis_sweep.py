#!/usr/bin/env python3
"""THE DIAG AXIS, SWEPT ACROSS EVERY SPELLING FAMILY (ruling R14-A + its tail).

Round 6 found that the escaped `\\<<` spelling moves the combinator's
diagnostic LINE NUMBERS base->tip. I added a diagnostic axis -- follow-up lines
that FAIL, and therefore get reported with a line number -- but I added it only
to the escaped spellings. Round 7 then found the identical delta on valid
arithmetic-shift SUBSCRIPTS (`a[1<<2]=1`), which no pin covered. That is the
same unvaried-axis failure twice: I closed the axis for the shapes I had just
been bounced on, not for the SPACE the declaration's own prose quantifies over.

So this sweep does not ask "do the four subscript shapes move?". It asks the
question whose answer closes the axis:

    FOR EVERY SPELLING FAMILY THE CORPUS KNOWS, does a diagnostic-emitting
    follow-up line report a different line number at base than at tip?

The predicted membership is mechanical, and stating it up front makes this a
test of a hypothesis rather than a fishing trip: base's TEXT scanner reported a
phantom pending heredoc for any `<<WORD` it saw outside quotes/arithmetic, and
the session then merged the following physical lines into ONE buffer, which the
combinator stamps with the buffer's start line. So a family MOVES iff base's
regex mis-detected it AND the real lexer says the line is complete. Every
family where the two agreed -- quoted, arithmetic, true heredocs -- must be
IDENTICAL, and those rows are the controls that keep this instrument honest.

Usage: python3 diag_axis_sweep.py <base_tree> <tip_tree> <outfile>
"""
import pathlib
import re
import subprocess
import sys
import tempfile

BASH = "/opt/homebrew/bin/bash"
LINE_RE = re.compile(r"line (\d+):")

# (family, label, script). Every script's follow-up lines FAIL, so every one
# of them is reported with a line number -- that is the axis.
CASES = [
    # --- PREDICTED TO MOVE: base's regex saw a phantom heredoc -------------
    ("escaped", "escaped_lt", "echo \\<<E\nhello\nE\n"),
    ("escaped", "escaped_lt_quoted", "echo \\<<'E'\nhello\nE\n"),
    ("escaped", "escaped_lt_strip", "echo \\<<-E\nhello\nE\n"),
    ("escaped", "escaped_lt_digit", "echo 0\\<<E\nhello\nE\n"),
    ("escaped2", "escaped_second_lt", "echo <\\<E\nnosuchcmd_a\n"),
    ("subscript", "subscript_shift_valid",
     "a[1<<2]=1; echo ${a[4]}\nnosuchcmd_b\n"),
    ("subscript", "subscript_shift_spaces",
     "a[ 1 << 2 ]=1; echo ${a[4]}\nnosuchcmd_c\n"),
    ("subscript", "subscript_shift_expand",
     "n=2; a[1<<$n]=1; echo ${a[4]}\nnosuchcmd_d\n"),
    ("subscript", "declare_subscript_shift",
     "declare -a b; b[3<<1]=z; echo ${b[6]}\nnosuchcmd_e\n"),
    ("subscript", "subscript_degenerate", "a[<<]=1\nnosuchcmd_f\n"),

    # --- CONTROLS: base's regex and the lexer AGREED, so nothing may move ---
    ("quoted", "single_quoted", "echo '<<E'\nnosuchcmd_g\n"),
    ("quoted", "double_quoted", 'echo "<<E"\nnosuchcmd_h\n'),
    ("arith", "arith_dollar", "echo $((1<<2))\nnosuchcmd_i\n"),
    ("arith", "arith_dbl_paren", "((1<<2))\nnosuchcmd_j\n"),
    ("arith", "let_shift", "let 'x = 1 << 2'\nnosuchcmd_k\n"),
    ("herestring", "here_string", "cat <<<word\nnosuchcmd_l\n"),
    ("fd_dup", "fd_dup_in", "echo x <&0\nnosuchcmd_m\n"),
    ("true_heredoc", "true_heredoc", "cat <<E\nhello\nE\nnosuchcmd_n\n"),
    ("true_heredoc", "true_heredoc_strip", "cat <<-E\nhello\nE\nnosuchcmd_o\n"),
    ("true_heredoc", "true_heredoc_quoted",
     "cat <<'E'\nhello\nE\nnosuchcmd_p\n"),
    ("true_heredoc", "true_heredoc_fd", "cat 0<<E\nhello\nE\nnosuchcmd_q\n"),
    ("no_heredoc", "no_heredoc_ctl",
     "if true; then\nnosuchcmd_r\nfi\nnosuchcmd_s\n"),
    ("option", "posix_escaped_lt", "set -o posix\necho \\<<E\nhello\nE\n"),
]

DISCRIM = "import psh, sys; sys.stderr.write('I '+psh.__file__+'\\n')"


def env_for(tree):
    return {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp",
            "PYTHONPATH": tree, "PYTHONUNBUFFERED": "1"}


def run_psh(tree, parser, channel, script, sandbox):
    argv = [sys.executable, "-m", "psh", "--norc", "--parser", parser]
    stdin_b, name = None, None
    if channel == "dash_c":
        argv += ["-c", script]
    elif channel == "script":
        with tempfile.NamedTemporaryFile("w", suffix=".sh", dir=sandbox,
                                         delete=False) as tf:
            tf.write(script)
        name = tf.name
        argv += [name]
    else:
        stdin_b = script.encode()
    p = subprocess.run(argv, input=stdin_b, capture_output=True, cwd=sandbox,
                       env=env_for(tree), timeout=30)
    err = p.stderr.decode(errors="replace")
    if name:
        err = err.replace(name, "<S>").replace(name.rsplit("/", 1)[-1], "<S>")
    return p.returncode, p.stdout.decode(errors="replace"), \
        [int(n) for n in LINE_RE.findall(err)]


def run_bash(script, sandbox):
    with tempfile.NamedTemporaryFile("w", suffix=".sh", dir=sandbox,
                                     delete=False) as tf:
        tf.write(script)
    p = subprocess.run([BASH, tf.name], capture_output=True, cwd=sandbox,
                       timeout=30)
    err = p.stderr.decode(errors="replace")
    return p.returncode, p.stdout.decode(errors="replace"), \
        [int(n) for n in LINE_RE.findall(err)]


def main():
    base_tree, tip_tree, outfile = sys.argv[1], sys.argv[2], sys.argv[3]
    sandbox = tempfile.mkdtemp()
    L = []

    def sha(t):
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=t,
                              capture_output=True, text=True).stdout.strip()

    L.append("# DIAG AXIS SWEPT ACROSS EVERY SPELLING FAMILY (R14-A + tail)")
    L.append(f"# base: {base_tree}  SHA: {sha(base_tree)}")
    L.append(f"# tip : {tip_tree}  SHA: {sha(tip_tree)}")
    L.append(f"# oracle: {subprocess.run([BASH, '--version'], capture_output=True, text=True).stdout.splitlines()[0]}")
    for tree in (base_tree, tip_tree):
        d = subprocess.run([sys.executable, "-c", DISCRIM], cwd=sandbox,
                           env=env_for(tree), capture_output=True, text=True)
        ok = d.stderr.strip().startswith(f"I {tree}/psh/")
        L.append(f"# discriminator {'OK ' if ok else 'BAD'}: {d.stderr.strip()}")
        if not ok:
            L.append("# FATAL: wrong tree imported — results void.")
            pathlib.Path(outfile).write_text("\n".join(L) + "\n")
            print("\n".join(L))
            return 2

    moved, identical = [], []
    L.append("\n# family        label                      chan     parser      "
             "base_lines -> tip_lines   bash_lines   verdict")
    for family, label, script in CASES:
        for channel in ("dash_c", "script", "stdin"):
            for parser in ("rd", "combinator"):
                b = run_psh(base_tree, parser, channel, script, sandbox)
                t = run_psh(tip_tree, parser, channel, script, sandbox)
                bash = run_bash(script, sandbox)
                same = b == t
                key = (family, label, channel, parser)
                (identical if same else moved).append(key)
                agrees = "tip==bash_lines" if t[2] == bash[2] else "LINES DIFFER"
                L.append(f"  {family:12} {label:26} {channel:8} {parser:11} "
                         f"{str(b[2]):10} -> {str(t[2]):10} {str(bash[2]):12} "
                         f"{'MOVED  ' if not same else 'ident  '} {agrees}")

    L.append(f"\n# TOTALS rows={len(moved)+len(identical)} moved={len(moved)} "
             f"identical={len(identical)}")
    fam_moved = sorted({m[0] for m in moved})
    fam_ident = sorted({i[0] for i in identical} - set(fam_moved))
    L.append(f"# FAMILIES THAT MOVE:     {fam_moved}")
    L.append(f"# FAMILIES THAT DO NOT:   {fam_ident}")
    L.append("# MOVED rows, by (family,label,chan,parser):")
    for m in moved:
        L.append(f"#     {m}")
    pathlib.Path(outfile).write_text("\n".join(L) + "\n")
    print("\n".join(L[-40:]))
    print(f"(full report: {outfile})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
