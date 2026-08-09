#!/usr/bin/env python3
"""A9 — is the masker's handler reachable from USER INPUT?

For the two maskers whose disposition Phase A left open (read_builtin.py:235
and parse_tree.py:135), the question the brief's fence poses is: did anything
NON-DEFECT ever flow through the broad catch? Reading the code answers "no";
this MEASURES it, with line coverage over a user-input corpus.

Method: run each corpus cell in-process under coverage.py and report whether
the handler's own line was EXECUTED. A handler line that never executes across
a deliberately hostile corpus is a defect-only path; one that does execute is
LOAD-BEARING and its narrowing is a fence, not an improvisation.

A SEEDED arm proves the instrument can observe a hit at all (D-3.4 lesson 7:
a prover that cannot fire proves nothing).

ROOT from argv[1].
"""
import io
import os
import sys

ROOT = os.path.abspath(sys.argv[1])
sys.path.insert(0, ROOT)
import coverage  # noqa: E402
import psh  # noqa: E402

assert os.path.dirname(psh.__file__) == os.path.join(ROOT, "psh"), "discriminator"
print(f"discriminator OK: {os.path.dirname(psh.__file__)}")

# INSTRUMENT-KIND CORRECTION (recorded, not buried). The first version keyed
# on the `except ...:` CLAUSE line (read 235 / parse_tree 135). CPython traces
# an except clause when it is TESTED for a match, not only when it matches, so
# an exception that the PRECEDING handler did not take marks the next clause
# executed even though its body never ran. That is a line-level probe answering
# a branch-level question, and it produced a FALSE "load-bearing" reading for
# parse_tree (EXECUTED=True) that a direct subprocess scan for the handler's
# own diagnostic could not reproduce. Key on the handler BODY line instead --
# the substrate that actually answers "did this masker fire?".
READ_HANDLER = (os.path.join(ROOT, "psh/builtins/read_builtin.py"), 236)
PT_HANDLER = (os.path.join(ROOT, "psh/builtins/parse_tree.py"), 136)

# --- corpora -----------------------------------------------------------------
# `read`: hostile INPUT bytes and hostile OPTION combinations. Malformed UTF-8
# is the shape that could plausibly raise a real ValueError (UnicodeDecodeError
# IS a ValueError subclass) if the cursor's decoder were not surrogateescape.
READ_CELLS = [
    ("plain",            b"hello\n",            "read x"),
    ("no-newline",       b"hello",              "read x"),
    ("empty",            b"",                   "read x"),
    ("bad-utf8-lone",    b"\xff\n",             "read x"),
    ("bad-utf8-trunc",   b"\xe2\x82\n",         "read x"),
    ("bad-utf8-mid",     b"a\xffb\n",           "read x"),
    ("bad-utf8-surrog",  b"\xed\xa0\x80\n",     "read x"),
    ("nul-byte",         b"a\x00b\n",           "read x"),
    ("bad-utf8-N",       b"\xff\xfe\xfd",       "read -N 2 x"),
    ("bad-utf8-n",       b"\xff\xfe\xfd\n",     "read -n 2 x"),
    ("bad-utf8-d",       b"\xffX\xfe",          "read -d X x"),
    ("bad-utf8-raw",     b"\xff\\\n\xfe\n",     "read -r x"),
    ("bad-utf8-array",   b"\xff \xfe\n",        "read -a arr"),
    ("bad-utf8-ifs",     b"\xff:\xfe\n",        "IFS=: read x y"),
    ("continuation-eof", b"a \\",               "read x"),
    ("many-vars",        b"a b c\n",            "read x y z w v"),
    ("silent",           b"secret\n",           "read -s x"),
    # `read -d ''` with no terminator BLOCKS and a 100k line crawls under
    # coverage; neither reaches a distinct handler path, so they are dropped
    # rather than left to hang the probe.
    ("long-line",        b"x" * 4096 + b"\n",   "read x"),
    ("crlf",             b"a\r\n",              "read x"),
]

# `parse-tree`: valid, invalid, and pathological command text, across FORMATS
# (the format axis is what selects the formatter the net wraps).
PT_FORMATS = ["pretty", "tree", "compact", "dot"]
PT_INPUTS = [
    "echo hi", "", "if", "for i in a b; do echo $i; done",
    "a | b | c", "((1+2))", "[[ -f x ]]", "case x in y) ;; esac",
    "echo $(date)", "echo `date`", "echo ${x:-y}", "echo $((1/0))",
    "func() { echo; }", "echo 'unclosed", 'echo "unclosed',
    "echo <(cat)", "declare -A m; m[a b]=1", "echo $'\\x41'",
    "while :; do break; done", "a=1 b=2 env", "echo *", "echo {1..3}",
    # `coproc`/`select` spawn or block under parse-tree; dropped.
    "!", "&&", ";;",
    "echo \\", "$(((((", "${!x}", "${x@Q}", "echo >&-", "time echo",
]


def run_covered(fn, targets):
    cov = coverage.Coverage(data_file=None, branch=False,
                            include=[t[0] for t in targets])
    cov.start()
    try:
        fn()
    finally:
        cov.stop()
    data = cov.get_data()
    hits = {}
    for path, line in targets:
        executed = set(data.lines(path) or ())
        hits[(os.path.relpath(path, ROOT), line)] = line in executed
    return hits


def drive_read():
    # ONE shell for the whole corpus: campaign F2 forbids two simultaneously
    # active shells anyway, and building 20 of them dominated the runtime.
    from psh.shell import Shell
    sh = Shell(norc=True)
    try:
        for label, data, cmd in READ_CELLS:
            r, w = os.pipe()
            os.write(w, data)
            os.close(w)
            saved = os.dup(0)
            os.dup2(r, 0)
            os.close(r)
            try:
                sh.run_command(cmd)
            except BaseException as e:      # noqa: BLE001 - measuring
                print(f"    read/{label}: escaped {type(e).__name__}: {e}")
            finally:
                os.dup2(saved, 0)
                os.close(saved)
    finally:
        sh.close()


def drive_parse_tree():
    from psh.shell import Shell
    sh = Shell(norc=True)
    try:
        for fmt in PT_FORMATS:
            for txt in PT_INPUTS:
                try:
                    sh.run_command(f"parse-tree -f {fmt} {txt!r}")
                except BaseException as e:  # noqa: BLE001 - measuring
                    print(f"    pt/{fmt}/{txt[:14]!r}: escaped "
                          f"{type(e).__name__}")
    finally:
        sh.close()


def main():
    print(f"\n=== read_builtin.py:235 — {len(READ_CELLS)} user-input cells ===")
    buf = io.StringIO()
    so, se = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = buf
    try:
        h1 = run_covered(drive_read, [READ_HANDLER])
    finally:
        sys.stdout, sys.stderr = so, se
    for k, v in h1.items():
        print(f"  handler {k[0]}:{k[1]} EXECUTED={v}")

    print(f"\n=== parse_tree.py:135 — "
          f"{len(PT_FORMATS) * len(PT_INPUTS)} format x input cells ===")
    buf2 = io.StringIO()
    sys.stdout = sys.stderr = buf2
    try:
        h2 = run_covered(drive_parse_tree, [PT_HANDLER])
    finally:
        sys.stdout, sys.stderr = so, se
    for k, v in h2.items():
        print(f"  handler {k[0]}:{k[1]} EXECUTED={v}")

    # --- SEEDED arm: the instrument must be able to SEE a hit ---------------
    print("\n=== SEEDED CONTROL: force the read VE leg with an injected defect ===")
    from psh.shell import Shell
    import psh.builtins.read_builtin as rb

    orig = rb.ReadBuiltin._read_normal

    def boom(self, *a, **k):
        raise ValueError("seeded defect inside the read record engine")

    rb.ReadBuiltin._read_normal = boom
    try:
        def drive_seeded():
            r, w = os.pipe()
            os.write(w, b"hi\n")
            os.close(w)
            saved = os.dup(0)
            os.dup2(r, 0)
            os.close(r)
            sh = Shell(norc=True)
            try:
                sh.run_command("read x")
            finally:
                sh.close()
                os.dup2(saved, 0)
                os.close(saved)
        buf3 = io.StringIO()
        sys.stdout = sys.stderr = buf3
        try:
            h3 = run_covered(drive_seeded, [READ_HANDLER])
        finally:
            sys.stdout, sys.stderr = so, se
        for k, v in h3.items():
            print(f"  handler {k[0]}:{k[1]} EXECUTED={v}   <- must be True")
        print(f"  (seeded run's shell output: {buf3.getvalue().strip()[:90]!r})")
    finally:
        rb.ReadBuiltin._read_normal = orig
        print("  seeded defect REMOVED from the tree (monkeypatch reverted)")


main()
