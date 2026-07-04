"""Loop exit status after break/continue (reappraisal #17 Tier-1 H3).

bash semantics (verified against bash 3.2 AND 5.2 — probe battery in
tmp/probes-r17t1-break/): a successful break/continue is a command that
returns 0, and a loop's exit status is that of the last command executed
in its body — which, when the loop ends via break, is the break itself.

psh used to report the PREVIOUS iteration's status when the signal was
reached via && / || on a non-first iteration:

    for i in 0 1 2 3; do [ $i -ge 2 ] && break; done    # bash 0, psh gave 1

The same table also pins the mirrored while/until CONDITION-position
semantics and the out-of-range `break 0` status crossing fork boundaries.
"""

import subprocess
import sys

import pytest


def run_psh(command, input_text=None, timeout=15):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', command],
        input=input_text, capture_output=True, text=True, timeout=timeout)


class TestBreakResetsStatus:
    """A successful break resets $? to 0 even after a failing command."""

    def test_for_break_via_andand(self, captured_shell):
        # Iterations 0 and 1 leave $?=1 from the failed test; the taken
        # break on iteration 2 must reset the loop status to 0.
        result = captured_shell.run_command(
            "for i in 0 1 2 3; do [ $i -ge 2 ] && break; done")
        assert result == 0

    def test_for_break_via_oror(self, captured_shell):
        result = captured_shell.run_command(
            "for i in 0 1 2 3; do test $i -lt 2 || break; test $i -lt 0; done")
        assert result == 0

    def test_while_break_via_andand(self, captured_shell):
        result = captured_shell.run_command(
            "i=0; while [ $i -lt 4 ]; do i=$((i+1)); [ $i -ge 2 ] && break; done")
        assert result == 0

    def test_until_break_via_andand(self, captured_shell):
        result = captured_shell.run_command(
            "i=0; until [ $i -ge 4 ]; do i=$((i+1)); false; "
            "[ $i -ge 2 ] && break; done")
        assert result == 0

    def test_c_style_for_break_via_andand(self, captured_shell):
        result = captured_shell.run_command(
            "for ((i=0;i<4;i++)); do [ $i -ge 2 ] && break; done")
        assert result == 0

    def test_nested_inner_loop_status_not_stale(self, captured_shell):
        # The inner loop's 0 (from break) is the outer body's last status.
        result = captured_shell.run_command(
            "for i in 1; do for j in 1 2 3; do false; "
            "[ $j -ge 2 ] && break; done; done")
        assert result == 0

    def test_break_2_after_failures_resets_status(self, captured_shell):
        result = captured_shell.run_command(
            "for i in 1 2; do false; for j in 1 2; do false; break 2; done; done")
        assert result == 0

    def test_eval_break_via_andand(self, captured_shell):
        result = captured_shell.run_command(
            "for i in 0 1 2 3; do [ $i -ge 2 ] && eval break; done")
        assert result == 0

    def test_select_break_via_andand(self):
        r = run_psh("select x in a b; do [ 1 -eq 1 ] && break; done; echo rc=$?",
                    input_text="1\n")
        assert r.returncode == 0
        assert r.stdout == "rc=0\n"


class TestContinueResetsStatus:
    """A successful continue also resets $? to 0 (loop ends after it)."""

    def test_for_continue_via_andand(self, captured_shell):
        result = captured_shell.run_command(
            "for i in 0 1 2 3; do [ $i -ge 2 ] && continue; done")
        assert result == 0

    def test_for_continue_via_oror(self, captured_shell):
        result = captured_shell.run_command(
            "for i in 0 1 2 3; do [ $i -lt 2 ] || continue; false; done")
        assert result == 0

    def test_while_continue_via_andand(self, captured_shell):
        result = captured_shell.run_command(
            "i=0; while [ $i -lt 4 ]; do i=$((i+1)); false; "
            "[ $i -ge 2 ] && continue; done")
        assert result == 0

    def test_until_continue_via_andand(self, captured_shell):
        result = captured_shell.run_command(
            "i=0; until [ $i -ge 4 ]; do i=$((i+1)); false; "
            "[ $i -ge 2 ] && continue; done")
        assert result == 0

    def test_c_style_for_continue_via_andand(self, captured_shell):
        result = captured_shell.run_command(
            "for ((i=0;i<4;i++)); do false; [ $i -ge 2 ] && continue; done")
        assert result == 0

    def test_continue_2_resets_outer_status(self, captured_shell):
        result = captured_shell.run_command(
            "for i in 1 2; do false; for j in 1 2; do false; continue 2; done; done")
        assert result == 0


class TestStatusesThatMustNotReset:
    """Correct pre-fix behaviors that the reset must not disturb."""

    def test_break_on_first_iteration(self, captured_shell):
        assert captured_shell.run_command("for i in 1 2 3; do break; done") == 0

    def test_continue_then_failing_next_iteration(self, captured_shell):
        # The last executed command is iteration 2's false, not the continue.
        result = captured_shell.run_command(
            "for i in 1 2; do [ $i -eq 1 ] && continue; false; done")
        assert result == 1

    def test_untaken_break_keeps_test_failure(self, captured_shell):
        # false && break: break never runs; loop status is the 1 from false.
        result = captured_shell.run_command(
            "for i in 1 2 3; do false && break; done")
        assert result == 1

    def test_break_zero_reports_out_of_range_status_one(self, captured_shell):
        result = captured_shell.run_command("for i in 1 2; do break 0; done")
        assert result == 1
        assert 'loop count out of range' in captured_shell.get_stderr()

    def test_continue_zero_reports_out_of_range_status_one(self, captured_shell):
        result = captured_shell.run_command("for i in 1 2; do continue 0; done")
        assert result == 1
        assert 'loop count out of range' in captured_shell.get_stderr()

    def test_break_level_beyond_depth_is_success(self, captured_shell):
        assert captured_shell.run_command("for i in 1 2; do break 5; done") == 0

    def test_while_normal_end_keeps_last_body_status(self, captured_shell):
        result = captured_shell.run_command(
            "i=0; while [ $i -lt 2 ]; do i=$((i+1)); false; done")
        assert result == 1


class TestConditionPositionSemantics:
    """break/continue in a while/until CONDITION (bash 3.2 + 5.2 verified).

    while: a successful break there resets the loop status to 0; a failed
    `break 0` keeps the last body status. until is mirrored: the signal's 0
    reads as the condition succeeding, ending the loop with the body status
    kept, and `break 0`'s failure status is reported.
    """

    def test_while_break_in_condition_is_zero(self, captured_shell):
        assert captured_shell.run_command("while break; do :; done") == 0

    def test_while_cond_break_resets_after_failing_body(self, captured_shell):
        result = captured_shell.run_command(
            "i=0; while { i=$((i+1)); [ $i -eq 2 ] && break; [ $i -le 5 ]; }; "
            "do false; done")
        assert result == 0

    def test_while_cond_break_zero_keeps_initial_status(self, captured_shell):
        # bash: `while break 0; do :; done` ends with 0 (no body ever ran).
        result = captured_shell.run_command("while break 0; do :; done")
        assert result == 0
        assert 'loop count out of range' in captured_shell.get_stderr()

    def test_while_cond_break_zero_keeps_failing_body_status(self, captured_shell):
        result = captured_shell.run_command(
            "i=0; while { i=$((i+1)); [ $i -eq 2 ] && break 0; [ $i -le 5 ]; }; "
            "do false; done")
        assert result == 1

    def test_while_cond_continue_resets_status(self, captured_shell):
        result = captured_shell.run_command(
            "i=0; while { i=$((i+1)); if [ $i -eq 2 ]; then continue; fi; "
            "[ $i -le 2 ]; }; do false; done")
        assert result == 0

    def test_until_cond_break_keeps_body_status(self, captured_shell):
        result = captured_shell.run_command(
            "i=0; until { i=$((i+1)); [ $i -eq 2 ] && break; [ $i -gt 5 ]; }; "
            "do false; done")
        assert result == 1

    def test_until_cond_break_zero_reports_failure(self, captured_shell):
        result = captured_shell.run_command("until break 0; do :; done")
        assert result == 1
        assert 'loop count out of range' in captured_shell.get_stderr()

    def test_until_cond_continue_terminates_loop(self):
        # psh used to loop FOREVER here; bash ends the until (the continue's
        # 0 reads as the condition succeeding), keeping the last body status.
        r = run_psh(
            "i=0; until { i=$((i+1)); [ $i -eq 2 ] && continue; [ $i -gt 3 ]; }; "
            "do false; done; echo rc=$? i=$i")
        assert r.returncode == 0
        assert r.stdout == "rc=1 i=2\n"

    def test_until_cond_continue_before_any_body_is_zero(self):
        r = run_psh(
            "i=0; until { i=$((i+1)); if [ $i -eq 1 ]; then continue; fi; "
            "[ $i -gt 2 ]; }; do false; done; echo rc=$? i=$i")
        assert r.returncode == 0
        assert r.stdout == "rc=0 i=1\n"

    def test_until_cond_continue_2_still_continues_outer(self):
        # Level>1 must still propagate to the outer loop, not end the until
        # locally: bash prints no body-$i lines.
        r = run_psh(
            "for i in 1 2; do false; until continue 2; do :; done; "
            "echo body-$i; done; echo rc=$?")
        assert r.returncode == 0
        assert r.stdout == "rc=0\n"


class TestSignalStatusAcrossForks:
    """The signal's own status is the child's exit status at fork boundaries."""

    def test_break_zero_status_in_command_substitution(self):
        r = run_psh("for i in 1; do x=$(break 0); echo rc=$?; done")
        assert r.stdout == "rc=1\n"
        assert 'loop count out of range' in r.stderr

    def test_break_zero_status_as_pipeline_member(self):
        r = run_psh("for i in 1; do cat </dev/null | break 0; echo rc=$?; done")
        assert r.stdout == "rc=1\n"
        assert 'loop count out of range' in r.stderr

    @pytest.mark.serial
    def test_break_zero_status_in_background_child(self):
        r = run_psh("for i in 1; do break 0 & wait $!; echo rc=$?; done")
        assert r.stdout == "rc=1\n"
        assert 'loop count out of range' in r.stderr

    def test_successful_break_in_pipeline_member_is_zero(self, captured_shell):
        # The subshell ends silently with 0 and the loop is NOT broken.
        result = captured_shell.run_command(
            "for i in 1; do false; cat </dev/null | break; done")
        assert result == 0
        assert captured_shell.get_stderr() == ""
