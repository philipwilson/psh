"""Compound assignment reads the LHS BEFORE evaluating the RHS (bash).

`c=1; $((c+=c++))` is 2, not 3: bash binds the left operand of a compound
assignment (`+=`, `-=`, `*=`, ...) ONCE at the start, so an embedded post/pre
increment of the same variable in the RHS does not feed back into that read
(c is read as 1, then c++ yields 1, then 1+1=2). psh used to evaluate the RHS
first (reading c as the already-incremented 2 -> 3). Probe-verified against
bash 5.2 (tmp/probes-r18t2-arith/). See ArithmeticEvaluator._eval_assignment
and _eval_array_assignment.
"""

import pytest


@pytest.mark.parametrize("expr,expected", [
    ("c=1; echo $((c=1, c+=c++))", "2"),
    ("c=5; echo $((c-=c++))", "0"),
    ("c=3; echo $((c*=c++))", "9"),
    ("c=1; echo $((c+=++c))", "3"),
    ("c=5; echo $((c-=c--))", "0"),
    ("c=1; echo $((c|=c++))", "1"),
    ("c=5; echo $((c^=c++))", "0"),
    ("c=1; d=10; echo $((c+=c++ + d))", "12"),
])
def test_scalar_compound_reads_lhs_before_rhs(captured_shell, expr, expected):
    rc = captured_shell.run_command(expr)
    assert rc == 0
    assert captured_shell.get_stdout() == f"{expected}\n"


def test_scalar_final_value_matches_result(captured_shell):
    # Both the expression value and the stored variable are the pre-read
    # result (bash: `c=1; c+=c++` leaves c == 2, and $x == 2).
    rc = captured_shell.run_command("c=1; x=$((c+=c++)); echo $x $c")
    assert rc == 0
    assert captured_shell.get_stdout() == "2 2\n"


def test_plain_assignment_still_last_write_wins(captured_shell):
    # A plain `=` (not compound) evaluates the RHS then overwrites, so the
    # post-increment side effect is clobbered: `c=1; c=c++` is 1 (bash).
    rc = captured_shell.run_command("c=1; echo $((c=c++)); echo $c")
    assert rc == 0
    assert captured_shell.get_stdout() == "1\n1\n"


def test_array_element_compound_reads_lhs_before_rhs(captured_shell):
    # Same ordering for array elements: a=(1 2 3); $((a[1]+=a[1]++)) is 4,
    # not 5 (a[1] read as 2, a[1]++ yields 2, 2+2=4), and a[1] ends at 4.
    rc = captured_shell.run_command(
        "a=(1 2 3); echo $((a[1]+=a[1]++)); echo ${a[1]}")
    assert rc == 0
    assert captured_shell.get_stdout() == "4\n4\n"


def test_let_and_paren_command_agree(captured_shell):
    for cmd in ("c=1; let 'c+=c++'; echo $c",
                "c=1; (( c+=c++ )); echo $c"):
        captured_shell.clear_output()
        rc = captured_shell.run_command(cmd)
        assert rc == 0
        assert captured_shell.get_stdout() == "2\n"
