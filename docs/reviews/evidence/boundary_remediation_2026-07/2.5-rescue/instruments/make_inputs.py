#!/usr/bin/env python3
"""Write the byte-exact MEDIUM-3 spelling corpus as INPUT FILES.

Every case is a file of exact bytes; the PTY driver and the -c/script/stdin
driver both read these same files, so the two channels are fed IDENTICAL bytes
(the whole point: `echo \\<<EOF` is escape-sensitive and a `-c` one-liner
re-quoted through zsh has already false-alarmed once at v0.760.0).

Line 1 of each file is THE SHAPE. Line 2 is always `echo MARK""ER` — the
discriminator: if the shell considers line 1 COMPLETE, the string MARKER
appears in the shell's OUTPUT; if it swallows line 2 as a phantom heredoc
body, MARKER never appears. The `""` matters: the PTY echoes the typed bytes
back, so a literal `echo MARKER` would put "MARKER" in the transcript even
when nothing ran. Quote-splitting the word makes the typed echo (`MARK""ER`)
and the executed output (`MARKER`) textually distinct.
"""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "inputs"
OUT.mkdir(exist_ok=True)

# (name, shape line, expected-by-bash-grammar: True = line 1 is COMPLETE)
CASES = [
    # THE DEFECT: `\<` is an escaped literal '<'; what remains is `<EOF`, an
    # ordinary input redirection. Line is COMPLETE in bash.
    ("escaped_lt",            r"echo \<<EOF",        True),
    # Escaped SECOND '<': `<` redirect whose target word is `\<EOF` -> `<EOF`.
    ("escaped_second_lt",     r"echo <\<EOF",        True),
    # A literal backslash (\\) followed by a REAL heredoc -> INCOMPLETE.
    ("double_backslash",      "echo \\\\<<EOF",      False),
    # Quoted spellings: text, not an operator. COMPLETE.
    ("single_quoted",         "echo '<<EOF'",        True),
    ("double_quoted",         'echo "<<EOF"',        True),
    # Adjacent operators.
    ("here_string",           "cat <<<EOF",          True),
    ("arith_shift",           "echo $((1<<2))",      True),
    # TRUE heredoc controls: must remain INCOMPLETE-detected.
    ("true_heredoc",          "cat <<EOF",           False),
    ("true_heredoc_strip",    "cat <<-EOF",          False),
    ("true_heredoc_fd",       "cat 0<<EOF",          False),
    ("true_heredoc_quoted",   "cat <<'EOF'",         False),
    # NESTED shape (R1-E). A `<<` inside an UNCLOSED $( ... ): the substitution
    # body's heredoc keeps the line incomplete in both shells. It is in the PTY
    # corpus rather than only the equivalence corpus because the thing under
    # test is the SESSION's continuation decision, which only a terminal
    # exercises.
    ("nested_cmdsub_heredoc", "echo $(cat <<EOF",    False),
    # ... and the DEFECT's spelling one level down, inside a CLOSED $( ).
    ("nested_cmdsub_escaped", "echo $(echo \\<<EOF)", True),
]

# The OPTION axis (R1-E): the same shapes under `set -o posix`. Applied to the
# divergent spelling and to two true-heredoc controls, per the ruling.
OPTION_CASES = [
    ("posix_escaped_lt",      "set -o posix", r"echo \<<EOF",  True),
    ("posix_true_heredoc",    "set -o posix", "cat <<EOF",     False),
    ("posix_true_heredoc_strip", "set -o posix", "cat <<-EOF", False),
]

# THE DIAGNOSTIC AXIS (round-6 blocker 1, ruling R12-E). Every case above
# follows its shape line with `echo MARK""ER`, which prints something and says
# NOTHING about which line it ran on. That left the corpus blind to a class of
# delta it exists to catch: when the session stops merging swallowed lines into
# one buffer, the LINE NUMBERS in any diagnostic those lines emit change. 132
# identity rows reported escaped_lt IDENTICAL while 12 combinator rows had in
# fact moved (to bash's numbering).
#
# These cases follow the shape line with commands that FAIL, and are therefore
# reported as `line N`. The axis carries BOTH ANSWERS by construction: the
# escaped spellings, where the numbers move, and two controls where nothing may
# move -- a TRUE heredoc (whose body really is swallowed, at both SHAs) and a
# shape with no heredoc operator at all, which isolates the 2.2 combinator
# top-level line-stamping carry. If that control ever moves, the delta is not
# what the ledger says it is.
DIAG_CASES = [
    ("diag_escaped_lt",        r"echo \<<E",    "hello\nE"),
    ("diag_escaped_lt_quoted", r"echo \<<'E'",  "hello\nE"),
    ("diag_escaped_lt_strip",  r"echo \<<-E",   "hello\nE"),
    ("diag_escaped_lt_digit",  r"echo 0\<<E",   "hello\nE"),
    ("diag_true_heredoc_ctl",  "cat <<E",       "hello\nE\nnosuchcmd"),
    ("diag_no_heredoc_ctl",    "if true; then", "nosuchcmd\nfi\nnosuchcmd2"),
]

for name, shape, _complete in CASES:
    (OUT / f"{name}.in").write_bytes(
        shape.encode() + b"\n" + b'echo MARK""ER\n')

for name, option, shape, _complete in OPTION_CASES:
    (OUT / f"{name}.in").write_bytes(
        option.encode() + b"\n" + shape.encode() + b"\n" + b'echo MARK""ER\n')

for name, shape, rest in DIAG_CASES:
    (OUT / f"{name}.in").write_bytes(
        shape.encode() + b"\n" + rest.encode() + b"\n")

total = len(CASES) + len(OPTION_CASES) + len(DIAG_CASES)
print(f"wrote {total} input files to {OUT}")
for name, shape, complete in CASES:
    print(f"  {name}: complete_in_bash_grammar={complete}")
for name, option, shape, complete in OPTION_CASES:
    print(f"  {name}: [{option}] complete_in_bash_grammar={complete}")
for name, shape, rest in DIAG_CASES:
    print(f"  {name}: DIAGNOSTIC axis, follow-up = {rest!r}")
