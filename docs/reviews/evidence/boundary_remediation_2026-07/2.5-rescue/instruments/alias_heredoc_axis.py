#!/usr/bin/env python3
"""THE ALIAS AXIS (round-8 blockers 1+2, ruling R15-A/R15-B).

Round 8 found the axis nobody had varied in eight rounds: ALIAS EXPANSION.
Aliases substitute tokens AFTER the heredoc-aware lex, so the alias body's
`<<EOF` never goes through heredoc collection -- a LIVE parse path therefore
builds a plain `Redirect` carrying a heredoc operator type and no body, which
is exactly the shape R9-B called "synthetically constructible only" and which
every offender guard in the branch hand-builds.

That refutes a premise I inherited and repeated, so I am re-deriving the whole
picture rather than pinning the verifier's summary:

  * WHICH spellings reach which typed arm;
  * for each, whether base and tip DIFFER (a delta to declare) or agree with
    only the message text changing (record-only);
  * and what BASH does, because "psh moved" and "psh moved toward bash" are
    different claims and this family is not a move toward bash at all.

Usage: python3 alias_heredoc_axis.py <base_tree> <tip_tree> <outfile>
"""
import pathlib
import re
import subprocess
import sys
import tempfile

BASH = "/opt/homebrew/bin/bash"
DISCRIM = ("import psh.io_redirect.file_redirect as f, psh, sys; "
           "sys.stderr.write('I %s %s\\n' % "
           "(psh.__file__, hasattr(f,'NonExecutableRedirectError')))")

# (family, label, script). Every script needs expand_aliases: aliases are off
# in non-interactive shells, and that `shopt` is what makes this axis reachable
# from a script at all.
_PRE = "shopt -s expand_aliases\n"
CASES = [
    ("plain", "alias_plain",
     _PRE + 'alias foo="cat <<EOF"\nfoo\nhello\nEOF\necho AFTER\n'),
    ("digit", "alias_digit",
     _PRE + 'alias foo="cat 0<<EOF"\nfoo\nhello\nEOF\necho AFTER\n'),
    ("var_fd", "alias_var_fd",
     _PRE + 'alias foo="true {v}<<EOF"\nfoo\nhello\nEOF\necho AFTER\n'),
    ("var_fd", "alias_var_fd_strip",
     _PRE + 'alias foo="true {v}<<-EOF"\nfoo\nhello\nEOF\necho AFTER\n'),
    ("builtin_stream", "alias_builtin_read",
     _PRE + 'alias r="read x <<EOF"\nr\nhello\nEOF\necho AFTER\n'),
    # CONTROL: the same heredoc NOT introduced by an alias. The lexer collects
    # the body, so a HeredocRedirect is built and no arm is reached.
    ("control", "direct_heredoc",
     _PRE + 'cat <<EOF\nhello\nEOF\necho AFTER\n'),
    # CONTROL: an alias with no heredoc at all -- isolates "alias" from
    # "alias introducing a heredoc operator".
    ("control", "alias_no_heredoc",
     _PRE + 'alias foo="echo hi"\nfoo\necho AFTER\n'),
]


def env_for(tree):
    return {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp",
            "PYTHONPATH": tree, "PYTHONUNBUFFERED": "1"}


def norm(err, name):
    if name:
        err = err.replace(name, "<S>").replace(name.rsplit("/", 1)[-1], "<S>")
    return re.sub(r"^[^\s:]*(?:psh|bash)[^\s:]*:", "<SH>:", err, flags=re.M)


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
    return (p.returncode, p.stdout.decode(errors="replace"),
            norm(p.stderr.decode(errors="replace"), name))


def run_bash(script, sandbox):
    with tempfile.NamedTemporaryFile("w", suffix=".sh", dir=sandbox,
                                     delete=False) as tf:
        tf.write(script)
    p = subprocess.run([BASH, "--norc", tf.name], capture_output=True,
                       cwd=sandbox, timeout=30)
    return (p.returncode, p.stdout.decode(errors="replace"),
            norm(p.stderr.decode(errors="replace"), tf.name))


def main():
    base_tree, tip_tree, outfile = sys.argv[1], sys.argv[2], sys.argv[3]
    sandbox = tempfile.mkdtemp()
    L = []

    def sha(t):
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=t,
                              capture_output=True, text=True).stdout.strip()

    L.append("# THE ALIAS AXIS -- base vs tip vs bash (R15-A)")
    L.append(f"# base: {base_tree}  SHA: {sha(base_tree)}")
    L.append(f"# tip : {tip_tree}  SHA: {sha(tip_tree)}")
    for tree in (base_tree, tip_tree):
        d = subprocess.run([sys.executable, "-c", DISCRIM], cwd=sandbox,
                           env=env_for(tree), capture_output=True, text=True)
        L.append(f"# discriminator: {d.stderr.strip()}")

    counts = {"delta": 0, "msg_only": 0, "identical": 0}
    for family, label, script in CASES:
        L.append(f"\n### {family} / {label}")
        L.append(f"    script bytes: {script.encode()!r}")
        b_ = run_bash(script, sandbox)
        L.append(f"    bash  rc={b_[0]} out={b_[1]!r} err={b_[2]!r}")
        for channel in ("dash_c", "script", "stdin"):
            for parser in ("rd", "combinator"):
                base = run_psh(base_tree, parser, channel, script, sandbox)
                tip = run_psh(tip_tree, parser, channel, script, sandbox)
                if base == tip:
                    kind = "IDENTICAL"
                    counts["identical"] += 1
                elif (base[0], base[1]) == (tip[0], tip[1]):
                    kind = "MSG-ONLY "   # same rc + stdout, stderr text moved
                    counts["msg_only"] += 1
                else:
                    kind = "DELTA    "
                    counts["delta"] += 1
                L.append(f"  [{kind}] chan={channel:7} parser={parser:11} "
                         f"tip_rc={tip[0]} tip_out={tip[1]!r} "
                         f"bash_match={'YES' if tip == b_ else 'no'}")
                if kind != "IDENTICAL":
                    L.append(f"      base={base!r}")
                    L.append(f"      tip ={tip!r}")

    L.append(f"\n# TOTALS {counts}")
    pathlib.Path(outfile).write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
