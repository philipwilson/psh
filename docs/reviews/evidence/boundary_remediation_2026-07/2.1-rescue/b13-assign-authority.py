"""Does the command-args reader contribute anything UNIQUE for assignment words?

Condition-1 follow-up: my proposed fix makes the ASSIGNMENT authority the sole
reader of assignment values (the command-args reader would skip
assignment-shaped words). Risk to disprove: a finding that ONLY the
command-args path produces for an assignment word would be dropped.

Method: for each assignment shape, run the enhanced validator normally, then
again with `_check_undefined_variables_in_command` neutered, and finally with
`_process_variable_assignments`' value-check neutered — so each path's
contribution is attributable. Prints the message multiset per configuration.
"""
import os
import sys

sys.path.insert(0, os.getcwd())

from psh.lexer import tokenize  # noqa: E402
from psh.parser import parse  # noqa: E402
from psh.visitor.enhanced_validator_visitor import EnhancedValidatorVisitor  # noqa: E402

SHAPES = [
    ('bare plain', 'FOO=$y'),
    ('export plain', 'export FOO=$y'),
    ('local plain', 'fn() { local FOO=$y; }; fn'),
    ('readonly plain', 'readonly FOO=$y'),
    ('declare plain', 'declare FOO=$y'),
    ('export backtick', 'export FOO=`echo $y`'),
    ('export arith', 'export FOO=$(($y + 1))'),
    ('export modern', 'export FOO=$(echo $y)'),
    ('export at-unquoted', 'export FOO=$@'),
    ('export at-quoted', 'export FOO="$@"'),
    ('bare at-unquoted', 'FOO=$@'),
    ('export dquoted', 'export FOO="$y"'),
    ('export concat', 'export FOO=a$yb'),
    ('export two-refs', 'export FOO=$y$z'),
    ('export subscript', 'export FOO=${arr[$y]}'),
]


def msgs(src, *, skip_cmdargs=False, skip_assign=False):
    cls = EnhancedValidatorVisitor
    orig_cmdargs = cls._check_undefined_variables_in_command
    orig_word = cls._check_word_for_undefined_vars
    try:
        if skip_cmdargs:
            cls._check_undefined_variables_in_command = lambda self, node: None
        if skip_assign:
            cls._check_word_for_undefined_vars = lambda self, w, n: None
        v = cls()
        v.visit(parse(tokenize(src)))
        return sorted(i.message for i in v.issues)
    finally:
        cls._check_undefined_variables_in_command = orig_cmdargs
        cls._check_word_for_undefined_vars = orig_word


for label, src in SHAPES:
    both = msgs(src)
    assign_only = msgs(src, skip_cmdargs=True)
    cmdargs_only = msgs(src, skip_assign=True)
    unique_to_cmdargs = [m for m in cmdargs_only if m not in assign_only]
    print(f"{label:20s} both={len(both)} assign-only={len(assign_only)} "
          f"cmdargs-only={len(cmdargs_only)}")
    if unique_to_cmdargs:
        print(f"    UNIQUE-TO-CMDARGS: {unique_to_cmdargs}")
