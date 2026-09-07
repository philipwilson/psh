"""Conformance: a per-command redirect list CAN close then reopen fd 1/2 (C032).

The fd universe applies a redirect list in SOURCE ORDER, so ``1>&- 1>f`` leaves
fd 1 open on ``f`` and the body's output belongs in that file.  psh applied the
STREAM half of the close by an unordered scan of the whole list, installing an
opaque always-EBADF stream for any ``1>&-``/``2>&-`` anywhere in it; the later
reopen was severed and the body's output silently lost in every in-process
compound (brace group, function, ``if``, ``while``, ``until``, ``for``,
``case``), for both fd 1 and fd 2.

Reproducing command:

    { echo hi; } 1>&- 1>f      # bash: rc 0, f == "hi\\n"
                               # psh (before): rc 1, f empty, "write error: Bad
                               #               file descriptor"

The controls pin the other half of the rule: when fd 1 is still closed at the
END of the list the EBADF failure is CORRECT and must survive.

Rows observe the ACTUAL target through ``cat``/``grep`` on stdout rather than
the diagnostic itself, because a shell's error prefix names the shell.  Owner:
``psh/io_redirect/manager.py#_swap_closed_output_streams``.  Verified against
bash 5.3.15.
"""

from conformance_framework import ConformanceTest


class TestCompoundCloseThenReopenFd1(ConformanceTest):
    """The reopen wins: the body's output reaches the file, in every compound."""

    def test_brace_group(self):
        self.assert_identical_behavior('{ echo hi; } 1>&- 1>f; cat f')

    def test_function(self):
        self.assert_identical_behavior('g() { echo hi; }; g 1>&- 1>f; cat f')

    def test_if(self):
        self.assert_identical_behavior('if true; then echo hi; fi 1>&- 1>f; cat f')

    def test_while(self):
        self.assert_identical_behavior(
            'i=0; while [ $i -lt 1 ]; do echo hi; i=1; done 1>&- 1>f; cat f')

    def test_until(self):
        self.assert_identical_behavior(
            'i=0; until [ $i -gt 0 ]; do echo hi; i=1; done 1>&- 1>f; cat f')

    def test_for(self):
        self.assert_identical_behavior('for x in 1; do echo hi; done 1>&- 1>f; cat f')

    def test_case(self):
        self.assert_identical_behavior('case x in x) echo hi;; esac 1>&- 1>f; cat f')

    def test_nested_brace_groups(self):
        self.assert_identical_behavior('{ { echo hi; } 1>&- 1>f; }; cat f')

    def test_append_target(self):
        self.assert_identical_behavior(
            'printf "old\\n" > f; { echo hi; } 1>&- 1>>f; cat f')

    def test_printf_builtin(self):
        self.assert_identical_behavior('{ printf "hi\\n"; } 1>&- 1>f; cat f')

    def test_external_command(self):
        self.assert_identical_behavior('{ /bin/echo hi; } 1>&- 1>f; cat f')

    def test_multiple_writes_keep_order(self):
        self.assert_identical_behavior('{ echo a; echo b; } 1>&- 1>f; cat f')

    def test_builtin_and_external_interleave(self):
        self.assert_identical_behavior(
            '{ echo a; /bin/echo b; echo c; } 1>&- 1>f; cat f')

    def test_command_substitution_in_body(self):
        self.assert_identical_behavior('{ echo "s=$(echo sub)"; } 1>&- 1>f; cat f')

    def test_pipeline_in_body(self):
        self.assert_identical_behavior('{ echo hi | cat; } 1>&- 1>f; cat f')

    def test_eval_in_body(self):
        self.assert_identical_behavior('{ eval "echo hi"; } 1>&- 1>f; cat f')

    def test_body_open_cannot_steal_the_reopened_fd(self):
        # `< src` opens a file while fd 1 is momentarily free; it must not be
        # handed fd 1 out from under the reopen.
        self.assert_identical_behavior(
            'printf "L\\n" > src; { read v < src; echo "got=$v"; } 1>&- 1>f; cat f')


class TestCompoundCloseThenReopenDup(ConformanceTest):
    """The reopen may be a DUP: the stream follows fd 1 to its new target."""

    def test_close_fd1_then_dup_from_fd2(self):
        self.assert_identical_behavior('{ echo hi; } 2>f 1>&- 1>&2; cat f')

    def test_close_fd2_then_dup_from_fd1(self):
        self.assert_identical_behavior('{ echo err >&2; } 1>f 2>&- 2>&1; cat f')


class TestCompoundCloseThenReopenFd2(ConformanceTest):
    """fd 2: a builtin's own diagnostic must reach the reopened target."""

    def test_cd_diagnostic_reaches_reopened_fd2(self):
        self.assert_identical_behavior(
            '{ cd /nonexistent_zz; } 2>&- 2>f; grep -c nonexistent_zz f')

    def test_function_cd_diagnostic_reaches_reopened_fd2(self):
        self.assert_identical_behavior(
            'g() { cd /nonexistent_zz; }; g 2>&- 2>f; grep -c nonexistent_zz f')

    def test_cd_diagnostic_follows_fd2_dup_to_stdout(self):
        self.assert_identical_behavior(
            '{ cd /nonexistent_zz; } 2>&- 2>&1 | grep -c nonexistent_zz')

    def test_both_fds_closed_and_reopened(self):
        self.assert_identical_behavior(
            '{ echo out; echo err >&2; } 1>&- 2>&- 1>o 2>e; cat o; cat e')


class TestCloseWithoutReopenStillFails(ConformanceTest):
    """Control: fd still closed at the END of the list -- EBADF is correct.

    Losing these would mean the fix had merely disabled the close.
    """

    def test_reverse_order_reopen_then_close(self):
        self.assert_identical_behavior(
            '{ echo hi; } 1>f 1>&- 2>/dev/null; rc=$?; '
            'if [ -s f ]; then echo "rc=$rc nonempty"; else echo "rc=$rc empty"; fi')

    def test_close_only(self):
        self.assert_identical_behavior('{ echo hi; } 1>&- 2>/dev/null; echo "rc=$?"')

    def test_close_reopen_close(self):
        self.assert_identical_behavior(
            '{ echo hi; } 1>&- 1>f 1>&- 2>/dev/null; rc=$?; '
            'if [ -s f ]; then echo "rc=$rc nonempty"; else echo "rc=$rc empty"; fi')

    def test_function_close_only(self):
        self.assert_identical_behavior(
            'g() { echo hi; }; g 1>&- 2>/dev/null; echo "rc=$?"')


class TestNestedRegionsRestoreLifo(ConformanceTest):
    """Nested close-then-reopen regions: the inner install is undone first.

    Each region installs its own fd-following stream and the restore is LIFO,
    so an inner region's state can never outlive it -- nor mask the outer's.
    """

    def test_inner_reopen_inside_outer_close(self):
        # Outer closes fd 1 for good; the INNER list reopens it onto `f`.
        self.assert_identical_behavior(
            '{ { echo hi; } 1>&- 1>f; } 1>&-; echo "rc=$?"; cat f')

    def test_inner_close_inside_outer_reopen(self):
        # Outer reopens fd 1 onto `f`; the INNER list closes it again, so the
        # write must still fail EBADF and `f` stay empty.
        self.assert_identical_behavior(
            '{ { echo hi; } 1>&-; } 1>&- 1>f 2>/dev/null; '
            'if [ -s f ]; then echo nonempty; else echo empty; fi')

    def test_function_nests_its_own_reopen(self):
        self.assert_identical_behavior(
            'g() { { echo hi; } 1>&- 1>inner; }; g 1>&- 1>outer; '
            'echo "inner=[$(cat inner)] outer=[$(cat outer)]"')

    def test_reopen_region_then_close_only_region(self):
        self.assert_identical_behavior(
            '{ echo a; } 1>&- 1>f; { echo b; } 1>&- 2>/dev/null; '
            'echo "rc=$?"; cat f')


class TestStreamIsRestoredAfterTheCompound(ConformanceTest):
    """The displaced stream comes back: later commands reach the real stdout."""

    def test_echo_after_reopen(self):
        self.assert_identical_behavior('{ echo hi; } 1>&- 1>f; echo after; cat f')

    def test_echo_after_ebadf(self):
        self.assert_identical_behavior('{ echo hi; } 1>&- 2>/dev/null; echo back')

    def test_two_compounds_in_a_row(self):
        self.assert_identical_behavior(
            '{ echo one; } 1>&- 1>f1; { echo two; } 1>&- 1>f2; '
            'echo three; cat f1 f2')

    def test_function_reusable_afterwards(self):
        self.assert_identical_behavior('g() { echo in; }; g 1>&- 1>f; g; cat f')
