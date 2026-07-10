"""Regression pin: the combinator transfers array_init from token to Word.

Phase C (lexer R2) turned the combinator's `name=(...)` payload from a dynamic
`setattr(token, 'array_init', ...)` into a declared ``Token.array_init`` field.
The consumer that moves it onto the argument ``Word`` lives in
``combinators/commands/simple.py`` (``if group_array_init is not None:``).
Inverting that sentinel guard is a real behavior change — a declaration
builtin's array argument silently initializes to empty — yet exactly ONE test
in the whole suite caught it (verifier mutation arm (d), 2026-07-10).

This adds a DIRECT pin on that consumer (combinator parse of a `declare -a`
array argument) plus an end-to-end check.
"""

import os
import subprocess
import sys

from psh.ast_nodes.commands import SimpleCommand
from psh.lexer import tokenize
from psh.parser import create_parser


def _words_with_array_init(node, out=None):
    """Collect every Word carrying an ArrayInitialization from an AST."""
    if out is None:
        out = []
    if isinstance(node, SimpleCommand):
        out.extend(w for w in node.words if w.array_init is not None)
    for value in (vars(node).values() if hasattr(node, "__dict__") else []):
        if isinstance(value, list):
            for item in value:
                if hasattr(item, "__dict__"):
                    _words_with_array_init(item, out)
        elif hasattr(value, "__dict__"):
            _words_with_array_init(value, out)
    return out


def test_combinator_array_init_flows_to_argument_word():
    prog = create_parser(tokenize("declare -a arr=(one two three)"),
                         active_parser="combinator").parse()
    array_words = _words_with_array_init(prog)
    assert len(array_words) == 1, "array_init lost from the declare argument word"
    ai = array_words[0].array_init
    assert ai.name == "arr"
    assert ai.elements == ["one", "two", "three"]


def test_combinator_array_init_end_to_end():
    # Downstream effect of the consumer: declare must actually build the array.
    env = dict(os.environ)
    for k in ("DISPLAY", "XAUTHORITY", "PSH_STRICT_ERRORS"):
        env.pop(k, None)
    r = subprocess.run(
        [sys.executable, "-m", "psh", "--parser", "combinator", "-c",
         'declare -a arr=(one two three); echo "${arr[1]}:${#arr[@]}"'],
        env=env, capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "two:3\n"
