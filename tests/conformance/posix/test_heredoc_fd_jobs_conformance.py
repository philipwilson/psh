"""Heredoc, fd-duplication and job-control conformance tests.

The user guide claims "Full support" for here documents, here strings,
all redirection forms, and the wait builtin — per the project's
development principles, those claims are proven here against bash.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestHeredocConformance(ConformanceTest):
    def test_plain_heredoc(self):
        self.assert_identical_behavior('cat <<X\nplain $USER text\nX',
                                       env={'USER': 'tester'})

    def test_expansion_in_unquoted_delimiter(self):
        self.assert_identical_behavior(
            'v=42; cat <<X\nexpanded: $v and $(echo sub) and $((1+1))\nX')

    def test_single_quoted_delimiter_is_literal(self):
        self.assert_identical_behavior(
            "v=42; cat <<'X'\nliteral: $v and $(echo sub)\nX")

    def test_double_quoted_delimiter_is_literal(self):
        self.assert_identical_behavior('v=42; cat <<"X"\nliteral2: $v\nX')

    def test_dash_strips_leading_tabs(self):
        self.assert_identical_behavior('cat <<-X\n\tindented\n\t\tdeep\n\tX')

    def test_heredoc_into_pipeline(self):
        self.assert_identical_behavior('cat <<X | tr a-z A-Z\npipe me\nX')

    def test_two_heredocs_in_sequence(self):
        self.assert_identical_behavior('cat <<A; cat <<B\nfirst\nA\nsecond\nB')

    def test_heredoc_with_output_redirect(self):
        # $$ in the target must be the SHELL's pid in both the redirect
        # and the later words (regression: children expanded their own pid)
        self.assert_identical_behavior(
            'cat <<X > /tmp/psh_hd_$$.txt; cat /tmp/psh_hd_$$.txt; rm -f /tmp/psh_hd_$$.txt\ncontent\nX')

    def test_herestring(self):
        self.assert_identical_behavior('cat <<< "here string $((2*3))"')


class TestFdDupConformance(ConformanceTest):
    def test_dup_stdout_to_high_fd_and_back(self):
        self.assert_identical_behavior('exec 3>&1; echo to3 >&3; exec 3>&-')

    def test_exec_open_write_close(self):
        self.assert_identical_behavior(
            'exec 4>/tmp/psh_fd_$$.txt; echo four >&4; exec 4>&-; '
            'cat /tmp/psh_fd_$$.txt; rm -f /tmp/psh_fd_$$.txt')

    def test_exec_open_read_fd(self):
        self.assert_identical_behavior(
            "printf 'l1\\nl2\\n' > /tmp/psh_in_$$.txt; exec 5</tmp/psh_in_$$.txt; "
            'read -r a <&5; read -r b <&5; echo "$a/$b"; exec 5<&-; rm -f /tmp/psh_in_$$.txt')

    def test_swap_order_matters(self):
        self.assert_identical_behavior('echo out 2>&1 1>/dev/null; echo "rc=$?"')

    def test_group_stderr_merge_through_pipe(self):
        self.assert_identical_behavior('{ echo o; echo e >&2; } 2>&1 | sort')

    def test_write_to_unopened_fd_fails(self):
        # brace group so the error (whose text carries the shell's own
        # name) is suppressed in both shells before comparison
        self.assert_identical_behavior('{ echo hi >&9; } 2>/dev/null; echo "rc=$?"')


class TestJobControlConformance(ConformanceTest):
    """Non-interactive job-control basics: no [N] notices, wait statuses."""

    def test_wait_for_specific_pid(self):
        self.assert_identical_behavior('sleep 0.1 & wait $!; echo "rc=$?"')

    def test_wait_all(self):
        self.assert_identical_behavior('sleep 0.1 & sleep 0.12 & wait; echo "all done $?"')

    def test_wait_propagates_failure_status(self):
        self.assert_identical_behavior('false & wait $!; echo "rc=$?"')

    def test_wait_propagates_exit_code(self):
        self.assert_identical_behavior('(sleep 0.05; exit 5) & wait $!; echo "rc=$?"')

    def test_wait_after_kill_reports_signal_status(self):
        self.assert_identical_behavior(
            'sleep 5 & kill %1 && wait %1 2>/dev/null; echo "rc=$?"')

    def test_no_job_notice_in_noninteractive(self):
        # bash prints "[1] PID" only in interactive shells
        self.assert_identical_behavior('true & wait; echo done')

    def test_dollar_dollar_stable_in_subshell_and_cmdsub(self):
        self.assert_identical_behavior(
            'a=$$; b=$(echo $$); (echo "eq:$([ "$a" = "$b" ] && echo yes)") ')

    # disown: a disowned job is dropped from the job table so `jobs` no
    # longer lists it. The background sleeps redirect their own I/O so they
    # do not hold the capture pipe open after the shell exits.
    def test_disown_by_jobspec_removes_job(self):
        self.assert_identical_behavior(
            'sleep 3 >/dev/null 2>&1 & disown %1; jobs; echo done')

    def test_disown_no_arg_removes_current_job(self):
        self.assert_identical_behavior(
            'sleep 3 >/dev/null 2>&1 & disown; jobs; echo done')

    def test_disown_all_removes_every_job(self):
        self.assert_identical_behavior(
            'sleep 3 >/dev/null 2>&1 & disown -a; jobs; echo done')

    def test_disown_h_keeps_job_and_succeeds(self):
        # -h marks the job to skip SIGHUP but leaves it in the table.
        self.assert_identical_behavior(
            'sleep 3 >/dev/null 2>&1 & disown -h %1; echo "rc=$?"')
