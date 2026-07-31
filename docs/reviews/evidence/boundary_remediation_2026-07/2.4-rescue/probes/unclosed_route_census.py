#!/usr/bin/env python3
"""R4-C: CENSUS the unclosed-cmdsub-classified route class.

The cmdsub scanner classifies some incomplete bodies as an UNCLOSED
substitution rather than handing the body to the nested parser. Those surface
as a PLAIN ParseError (substitution_origin False), so neither the producer
typing nor the 2.4 consumers fire.

This enumerates the CLASS — every compound-opening keyword and brace/paren
form, not just the `case` witness the verifier found — and reports, per body,
whether the error is typed. Domain is stated in the output.
"""
import sys

sys.path.insert(0, "/Users/pwilson/src/psh-r2-4")

from psh.parser import ParseError, is_substitution_origin  # noqa: E402

# The compound/word forms that can leave a body "incomplete" in the scanner's
# eyes. Generated over the space of shell compound openers plus the grouping
# forms, rather than the one witness.
BODIES = [
    "case x in a) :;",        # the verifier's witness
    "case x in",
    "for i in 1 2",
    "for i in 1 2; do :",
    "while true",
    "while true; do :",
    "until false",
    "until false; do :",
    "if true",
    "if true; then :",
    "if true; then :; elif",
    "{ :",
    "( :",
    "select x in a",
    "select x in a; do :",
    "f() {",
    "[[ 1 -eq 1",
    "$(( 1 +",
    "'unterminated",
    '"unterminated',
    # CONTROLS: bodies known to be typed (both 2.4 kinds)
    "if",
    "fi",
    ";",
]


def classify(src):
    from psh.lexer import tokenize
    from psh.parser import parse
    try:
        parse(tokenize(src))
    except ParseError as e:
        return type(e).__name__, is_substitution_origin(e)
    except Exception as e:            # noqa: BLE001 - census reports the type
        return type(e).__name__, None
    return "NO-ERROR", None


def main():
    print("DOMAIN: every compound opener + grouping/quote form that can leave a")
    print("cmdsub body incomplete, wrapped in $(...) and in <(...).\n")
    typed = untyped = other = 0
    for body in BODIES:
        row = []
        for wrapper in ("echo $(%s)", "cat <(%s)"):
            src = wrapper % body
            name, origin = classify(src)
            row.append("%s/%s" % (name, origin))
            if origin is True:
                typed += 1
            elif origin is False:
                untyped += 1
            else:
                other += 1
        print("  %-26r cmdsub=%-34s procsub=%s" % (body, row[0], row[1]))
    print("\ntyped(sub_origin=True)=%d  UNTYPED(False)=%d  other=%d"
          % (typed, untyped, other))


if __name__ == "__main__":
    main()
