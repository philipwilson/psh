"""
Conformance tests for the ``$LINENO`` special variable.

``$LINENO`` substitutes the line number of the currently-executing command.
The non-trivial requirement (and the source of psh's pre-v0.485 bug, which
set LINENO once per buffered command to the construct's START line) is that
each *statement* reports its own absolute source line:

  - statements inside if/elif/else, for/while/until, case, and brace/subshell
    groups report their own line, not the construct's first line;
  - statements inside a FUNCTION report the line where they were DEFINED
    (identical on every call, regardless of the call site);
  - each pipeline in a multi-line ``&&`` / ``||`` chain reports its own line;
  - ``source``d files and ``eval`` strings count their own lines, and LINENO
    is restored to the caller's line when they return.

Two divergences from bash remain DOCUMENTED (not asserted here): command
substitution does not inherit the enclosing line (``x=$(echo $LINENO)``), and
the physical line counter under-counts after a backslash-newline line
continuation. Both are noted in CHANGELOG v0.485.0.

Verified against bash 5.2.
"""


from conformance_framework import ConformanceTest


class TestLinenoTopLevelConformance(ConformanceTest):
    """LINENO at the top level and across blank/comment lines."""

    def test_consecutive_lines(self):
        self.assert_identical_behavior('echo $LINENO\necho $LINENO\necho $LINENO')

    def test_blank_lines_counted(self):
        self.assert_identical_behavior('echo $LINENO\n\n\necho $LINENO')

    def test_comment_lines_counted(self):
        self.assert_identical_behavior(
            'echo $LINENO\n# a comment\n# another\necho $LINENO')

    def test_arithmetic_reference(self):
        self.assert_identical_behavior('echo $LINENO\necho $((LINENO))')


class TestLinenoCompoundConformance(ConformanceTest):
    """LINENO inside compound constructs reports the inner statement's line."""

    def test_if_then(self):
        self.assert_identical_behavior(
            'if true; then\n  echo $LINENO\nfi\necho $LINENO')

    def test_if_elif_else(self):
        self.assert_identical_behavior(
            'if false; then\n  echo a $LINENO\n'
            'elif true; then\n  echo b $LINENO\n'
            'else\n  echo c $LINENO\nfi')

    def test_for_loop(self):
        self.assert_identical_behavior(
            'for i in 1 2; do\n  echo $LINENO\ndone\necho $LINENO')

    def test_while_loop(self):
        self.assert_identical_behavior(
            'i=0\nwhile [ $i -lt 2 ]; do\n  i=$((i+1))\n  echo $LINENO\ndone')

    def test_until_loop(self):
        self.assert_identical_behavior(
            'until true; do\n  echo nope\ndone\necho $LINENO')

    def test_case(self):
        self.assert_identical_behavior(
            'x=b\ncase $x in\n  a) echo $LINENO ;;\n'
            '  b) echo $LINENO ;;\nesac\necho $LINENO')

    def test_nested_if_in_for(self):
        self.assert_identical_behavior(
            'for i in 1 2; do\n  if true; then\n    echo $LINENO\n  fi\ndone')

    def test_subshell_group(self):
        self.assert_identical_behavior('(\n  echo $LINENO\n  echo $LINENO\n)')

    def test_brace_group(self):
        self.assert_identical_behavior('{\n  echo $LINENO\n  echo $LINENO\n}')


class TestLinenoAndOrChainConformance(ConformanceTest):
    """Each pipeline in a multi-line && / || chain reports its own line."""

    def test_and_chain(self):
        self.assert_identical_behavior('true &&\n  echo $LINENO\necho $LINENO')

    def test_or_chain(self):
        self.assert_identical_behavior('false ||\n  echo $LINENO\necho $LINENO')

    def test_three_chain(self):
        self.assert_identical_behavior(
            'true &&\n  echo a $LINENO &&\n  echo b $LINENO')

    def test_pipeline_in_chain(self):
        self.assert_identical_behavior(
            'echo $LINENO | cat &&\n  echo $LINENO | cat')


class TestLinenoFunctionConformance(ConformanceTest):
    """LINENO inside a function reports its DEFINITION line on every call."""

    def test_def_site_lines(self):
        self.assert_identical_behavior(
            'echo top $LINENO\n'
            'myfunc() {\n  echo a $LINENO\n  echo b $LINENO\n}\n'
            'echo before $LINENO\nmyfunc\necho after $LINENO\nmyfunc')

    def test_single_line_func_multiple_calls(self):
        self.assert_identical_behavior(
            'f() { echo $LINENO; }\nf\nf\nf')

    def test_function_called_before_following_lines(self):
        self.assert_identical_behavior('f() {\n  echo $LINENO\n}\necho $LINENO\nf')

    def test_function_calls_function(self):
        self.assert_identical_behavior(
            'a() {\n  echo a $LINENO\n  b\n}\n'
            'b() {\n  echo b $LINENO\n}\na')

    def test_nested_function_definitions(self):
        self.assert_identical_behavior(
            'outer() {\n  echo o $LINENO\n'
            '  inner() { echo i $LINENO; }\n  inner\n}\nouter\nouter')


class TestLinenoEvalSourceConformance(ConformanceTest):
    """eval and source count their own lines and restore on return."""

    def test_eval_at_line_1(self):
        # eval on line 1: its string's line 1 anchors at 1, line 2 at 2.
        self.assert_identical_behavior("eval $'echo $LINENO\\necho $LINENO'")

    def test_eval_anchors_at_invoking_line(self):
        # eval is NOT a fresh context: bash anchors the eval string's line 1 at
        # the line eval was invoked on (here line 3), not 1. This is the case
        # the original single-line-1 test missed (it passed at offset 0).
        self.assert_identical_behavior(
            "echo a\necho b\neval 'echo p=$LINENO; echo q=$LINENO'")

    def test_eval_multiline_string_increments(self):
        self.assert_identical_behavior(
            "echo a\necho b\neval $'echo x=$LINENO\\necho y=$LINENO'")

    def test_eval_inside_function_uses_def_line(self):
        self.assert_identical_behavior(
            "f() {\n  eval 'echo $LINENO'\n}\necho x\nf")

    def test_source_resets_and_restores(self):
        # Build the sourced file in the (isolated, temp) cwd, then source it.
        self.assert_identical_behavior(
            "printf 'echo src $LINENO\\necho src $LINENO\\n' > f.sh\n"
            "echo pre $LINENO\nsource ./f.sh\necho post $LINENO")


class TestLinenoTrapConformance(ConformanceTest):
    """Trap action $LINENO: ERR/DEBUG see the current command line; EXIT and
    signal traps fire asynchronously and count from the action's own line 1."""

    def test_err_trap_reports_failing_command_line(self):
        self.assert_identical_behavior(
            "trap 'echo ERR at $LINENO' ERR\necho a\nfalse")

    def test_debug_trap_reports_command_line(self):
        self.assert_identical_behavior(
            "trap 'echo DEBUG at $LINENO' DEBUG\necho a\necho b")

    def test_exit_trap_counts_from_action_line_1(self):
        # bash runs the EXIT trap with $LINENO counting from the action's own
        # line, regardless of where the trap was defined or the last line run.
        self.assert_identical_behavior(
            "trap 'echo E$LINENO' EXIT\necho a\necho b")

    def test_exit_trap_multiline_action(self):
        self.assert_identical_behavior(
            "trap $'echo E$LINENO\\necho E$LINENO' EXIT\necho a")


class TestLinenoAssignmentConformance(ConformanceTest):
    """Assigning LINENO=N is honored and tracking continues from there."""

    def test_reassignment(self):
        self.assert_identical_behavior(
            'echo $LINENO\nLINENO=100\necho $LINENO\necho $LINENO')
