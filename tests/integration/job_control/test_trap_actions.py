"""
Tests for trap ACTION semantics (reappraisal #17 Tier-2 trap cluster).

Three fix families, each pinned to bash 5.2 via the truth tables in
tmp/probes-r17t2-trap/ (cases_a_ctrlflow / cases_b_bashcmd / cases_c_return):

1. Control flow in trap actions (MED-1): `return`/`break`/`continue` inside
   a trap action act on the enclosing function/loop. execute_trap used to
   swallow them in its blanket `except Exception`, printing a spurious
   "trap: error executing trap" and running the code the control flow
   should have skipped.

2. $BASH_COMMAND (MED-3): never populated. Now recorded (pre-expansion
   text) at the executor dispatch chokepoints and frozen while a trap
   action runs (bash: inside a trap it is the interrupted command).

3. RETURN trap (MED-2): was rejected outright ("invalid signal
   specification"). Now implemented with bash's hiding model: fires at
   each function return and end of `source`; functions hide it for their
   extent unless `set -T` (functrace) or the function's `declare -ft`
   trace attribute; a trap the body sets fires at that function's return
   and persists.

Bonus (LOW-2): with `set -T`, DEBUG additionally fires on function ENTRY.
"""

import subprocess
import sys


def run_psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


class TestControlFlowInTrapActions:
    """return/break/continue in a trap action reach the enclosing
    function/loop (bash); no spurious 'trap: error executing' leak."""

    def test_return_in_signal_trap_returns_from_function(self):
        result = run_psh('f() { trap "echo t; return 9" USR1; kill -USR1 $$; '
                         'echo after; }; f; echo rc=$?')
        assert result.stdout == 't\nrc=9\n'
        assert 'error executing trap' not in result.stderr

    def test_return_noarg_in_trap_uses_pre_trap_status(self):
        # bash: the no-arg return takes $? from before the trap fired
        # (the kill's 0), and `echo after` is skipped.
        result = run_psh('f() { trap "return" USR1; false; kill -USR1 $$; '
                         'echo after; }; f; echo rc=$?')
        assert result.stdout == 'rc=0\n'

    def test_return_in_trap_returns_from_innermost_function(self):
        result = run_psh('g() { kill -USR1 $$; echo g-after; }; '
                         'f() { trap "return 4" USR1; g; echo f-after; }; '
                         'f; echo rc=$?')
        assert result.stdout == 'f-after\nrc=0\n'

    def test_break_in_trap_exits_loop_with_status_0(self):
        result = run_psh('trap "break" USR1; i=0; while true; do i=$((i+1)); '
                         'test $i -eq 2 && kill -USR1 $$; '
                         'test $i -gt 5 && break; done; echo i=$i rc=$?')
        assert result.stdout == 'i=2 rc=0\n'
        assert 'error executing trap' not in result.stderr

    def test_break_in_trap_breaks_inner_loop_only(self):
        result = run_psh('trap "break" USR1; for i in 1 2; do for j in a b; do '
                         'test $j = a && kill -USR1 $$; echo $i$j; done; '
                         'echo outer-$i; done; echo rc=$?')
        assert result.stdout == 'outer-1\nouter-2\nrc=0\n'

    def test_break_2_in_trap_breaks_both_loops(self):
        result = run_psh('trap "break 2" USR1; for i in 1 2; do for j in a b; do '
                         'test $j = a && kill -USR1 $$; echo $i$j; done; '
                         'echo outer-$i; done; echo rc=$?')
        assert result.stdout == 'rc=0\n'

    def test_continue_in_trap_skips_rest_of_iteration(self):
        result = run_psh('trap "continue" USR1; for i in 1 2 3; do '
                         'test $i = 2 && kill -USR1 $$; echo i=$i; done; echo rc=$?')
        assert result.stdout == 'i=1\ni=3\nrc=0\n'

    def test_return_in_trap_stops_sourced_file(self, tmp_path):
        src = tmp_path / 'src.sh'
        src.write_text('trap "return 7" USR1\nkill -USR1 $$\necho in-src-after\n')
        result = run_psh(f'source {src}; echo rc=$?')
        assert result.stdout == 'rc=7\n'

    def test_return_in_trap_at_top_level_is_error_and_continues(self):
        result = run_psh('trap "return 5" USR1; kill -USR1 $$; echo after')
        assert 'after' in result.stdout
        assert "can only `return'" in result.stderr

    def test_return_in_debug_trap_when_inherited(self):
        # set -T inherits DEBUG into the function; its `return 5` returns
        # from the function before any body command runs.
        result = run_psh('set -T; f() { trap "return 5" DEBUG; echo one; '
                         'echo two; }; f; echo rc=$?')
        assert result.stdout == 'rc=5\n'

    def test_failing_trap_command_still_reported_without_wrapper(self):
        # A genuine error inside the action is NOT control flow: the
        # action's own diagnostics appear, execution continues, and no
        # "trap: error executing" wrapper is added (bash).
        result = run_psh('f() { trap "echo t; nosuchcmd_xyz" USR1; '
                         'kill -USR1 $$; echo after; }; f; echo rc=$?')
        assert result.stdout == 't\nafter\nrc=0\n'
        assert 'command not found' in result.stderr
        assert 'error executing trap' not in result.stderr


class TestBashCommand:
    """$BASH_COMMAND holds the pre-expansion text of the command being
    (or about to be) executed; frozen at the interrupted command while a
    trap action runs (bash)."""

    def test_debug_trap_sees_upcoming_command(self):
        result = run_psh('trap \'echo "[$BASH_COMMAND]"\' DEBUG; echo hi')
        assert result.stdout == '[echo hi]\nhi\n'

    def test_pre_expansion_text(self):
        result = run_psh('x=5; trap \'echo "[$BASH_COMMAND]"\' DEBUG; echo $x')
        assert result.stdout == '[echo $x]\n5\n'

    def test_quoting_preserved(self):
        result = run_psh("trap 'echo \"[$BASH_COMMAND]\"' DEBUG; "
                         "echo \"a b\" 'c d'")
        assert result.stdout == '[echo "a b" \'c d\']\na b c d\n'

    def test_outside_trap_shows_current_command(self):
        result = run_psh('true; echo "[$BASH_COMMAND]"')
        assert result.stdout == '[echo "[$BASH_COMMAND]"]\n'

    def test_err_trap_sees_failing_command(self):
        result = run_psh('trap \'echo "[$BASH_COMMAND]"\' ERR; false; true')
        assert result.stdout == '[false]\n'

    def test_err_after_function_shows_last_body_command(self):
        # BASH_COMMAND updates inside function bodies even though DEBUG is
        # not inherited there (bash b17).
        result = run_psh('f() { false; }; trap \'echo "[$BASH_COMMAND]"\' ERR; f')
        assert result.stdout == '[false]\n'
        assert result.returncode == 1

    def test_signal_trap_frozen_at_interrupted_command(self):
        result = run_psh('trap \'echo "[$BASH_COMMAND]"\' USR1; '
                         'kill -USR1 $$; echo "post=[$BASH_COMMAND]"')
        assert result.stdout == ('[kill -USR1 $$]\n'
                                 'post=[echo "post=[$BASH_COMMAND]"]\n')

    def test_debug_traps_own_commands_do_not_clobber(self):
        result = run_psh('trap \'true; echo "[$BASH_COMMAND]"\' DEBUG; echo hi')
        assert result.stdout == '[echo hi]\nhi\n'

    def test_for_loop_header_pre_expansion(self):
        result = run_psh('trap \'echo "[$BASH_COMMAND]"\' DEBUG; '
                         'v="a b"; for i in $v; do :; done')
        assert result.stdout == ('[v="a b"]\n[for i in $v]\n[:]\n'
                                 '[for i in $v]\n[:]\n')

    def test_case_header_pre_expansion_with_trailing_space(self):
        result = run_psh('x=foo; trap \'echo "[$BASH_COMMAND]"\' DEBUG; '
                         'case $x in foo) : ;; esac')
        assert result.stdout == '[case $x in ]\n[:]\n'

    def test_c_style_for_reports_each_arith_step(self):
        result = run_psh('trap \'echo "[$BASH_COMMAND]"\' DEBUG; '
                         'for ((i=0;i<1;i++)); do echo b; done')
        assert result.stdout == ('[((i=0))]\n[((i<1))]\n[echo b]\nb\n'
                                 '[((i++))]\n[((i<1))]\n')

    def test_arith_command_fires_debug_with_own_text(self):
        result = run_psh('trap \'echo "[$BASH_COMMAND]"\' DEBUG; ((1+1))')
        assert result.stdout == '[((1+1))]\n'

    def test_cond_expr_fires_debug_with_own_text(self):
        result = run_psh('trap \'echo "[$BASH_COMMAND]"\' DEBUG; [[ a == a ]]')
        assert result.stdout == '[[[ a == a ]]]\n'

    def test_pipeline_members_report_own_text(self):
        result = run_psh('trap \'echo "[$BASH_COMMAND]" >&2\' DEBUG; echo a | cat')
        assert result.stdout == 'a\n'
        assert '[echo a]' in result.stderr
        assert '[cat]' in result.stderr

    def test_exit_trap_frozen_at_exit_command(self):
        result = run_psh('trap \'echo "[$BASH_COMMAND]"\' EXIT; true; exit 0')
        assert result.stdout == '[exit 0]\n'

    def test_exit_trap_at_eof_shows_last_command(self):
        result = run_psh('trap \'echo "[$BASH_COMMAND]"\' EXIT; true')
        assert result.stdout == '[true]\n'


class TestReturnTrap:
    """RETURN pseudo-signal: fires at function return and end of source,
    with bash's hiding model for functions (truth table cases_c_return)."""

    def test_accepted_by_trap_builtin(self):
        result = run_psh('trap "echo R" RETURN; echo ok')
        assert result.stdout == 'ok\n'
        assert 'invalid signal' not in result.stderr

    def test_not_fired_for_plain_function_without_functrace(self):
        # bash c1: a top-level RETURN trap is HIDDEN inside a plain
        # function — it does not fire at that function's return.
        result = run_psh('trap "echo R" RETURN; f() { :; }; f; echo done')
        assert result.stdout == 'done\n'

    def test_fires_for_function_with_functrace(self):
        result = run_psh('set -T; trap "echo R" RETURN; f() { :; }; f; echo done')
        assert result.stdout == 'R\ndone\n'

    def test_fires_for_source_without_functrace(self, tmp_path):
        src = tmp_path / 'src.sh'
        src.write_text('echo in-src\n')
        result = run_psh(f'trap "echo R" RETURN; source {src}; echo done')
        assert result.stdout == 'in-src\nR\ndone\n'

    def test_fires_for_source_return_statement(self, tmp_path):
        src = tmp_path / 'src.sh'
        src.write_text('return 5\necho never\n')
        result = run_psh(f"trap 'echo R rc=$?' RETURN; source {src}; echo after=$?")
        assert result.stdout == 'R rc=0\nafter=5\n'

    def test_trap_set_inside_function_fires_at_its_return(self):
        result = run_psh('f() { trap "echo R" RETURN; :; }; f; echo done')
        assert result.stdout == 'R\ndone\n'

    def test_body_set_trap_persists_after_function(self, tmp_path):
        src = tmp_path / 'empty.sh'
        src.write_text('')
        result = run_psh('f() { trap "echo Rin" RETURN; }; f; '
                         f'source {src}; echo done')
        assert result.stdout == 'Rin\nRin\ndone\n'

    def test_body_set_trap_replaces_hidden_outer(self, tmp_path):
        src = tmp_path / 'empty.sh'
        src.write_text('')
        result = run_psh('trap "echo OUTER" RETURN; '
                         'f() { trap "echo INNER" RETURN; }; f; '
                         f'source {src}; echo done')
        assert result.stdout == 'INNER\nINNER\ndone\n'

    def test_hidden_outer_trap_restored_after_function(self, tmp_path):
        src = tmp_path / 'empty.sh'
        src.write_text('')
        result = run_psh('trap "echo R" RETURN; f() { :; }; f; '
                         f'source {src}; echo done')
        assert result.stdout == 'R\ndone\n'

    def test_trap_p_inside_function_lists_nothing(self):
        # The trap is genuinely hidden for the function's extent.
        result = run_psh('trap "echo R" RETURN; f() { trap -p RETURN; '
                         'echo listed=$?; }; f; echo done')
        assert result.stdout == 'listed=0\ndone\n'

    def test_nested_functions_functrace_fires_for_each(self):
        result = run_psh("set -T; g() { :; }; f() { g; }; "
                         "trap 'echo R:${FUNCNAME[0]}' RETURN; f; echo done")
        assert result.stdout == 'R:g\nR:f\ndone\n'

    def test_nested_function_without_functrace_fires_innermost_only(self):
        result = run_psh("g() { :; }; f() { trap 'echo R:${FUNCNAME[0]}' RETURN; "
                         "g; }; f; echo done")
        assert result.stdout == 'R:f\ndone\n'

    def test_funcname_and_locals_visible_during_trap(self):
        result = run_psh('f() { local v=inner; '
                         'trap \'echo "fn=${FUNCNAME[0]} v=$v"\' RETURN; :; }; '
                         'f; echo done')
        assert result.stdout == 'fn=f v=inner\ndone\n'

    def test_dollar_q_is_pre_return_status(self):
        # bash c29: $? inside the trap is the last command's status from
        # BEFORE the `return` executed.
        result = run_psh("f() { trap 'echo rc=$?' RETURN; false; return 7; }; "
                         "f; echo after=$?")
        assert result.stdout == 'rc=1\nafter=7\n'

    def test_trap_commands_do_not_change_return_status(self):
        result = run_psh('f() { trap "false" RETURN; return 0; }; f; echo after=$?')
        assert result.stdout == 'after=0\n'

    def test_trap_p_listing(self):
        result = run_psh('trap "echo R" RETURN; trap -p RETURN')
        assert result.stdout == "trap -- 'echo R' RETURN\n"

    def test_listing_order_pseudo_signals_last(self):
        result = run_psh('trap ":" EXIT; trap ":" DEBUG; trap ":" RETURN; '
                         'trap ":" ERR; trap ":" USR1; trap')
        lines = [ln.split()[-1] for ln in result.stdout.splitlines()]
        assert lines == ['EXIT', 'SIGUSR1', 'DEBUG', 'ERR', 'RETURN']

    def test_removal_with_trap_dash(self, tmp_path):
        src = tmp_path / 'empty.sh'
        src.write_text('')
        result = run_psh('f() { :; }; trap "echo R" RETURN; trap - RETURN; f; '
                         f'source {src}; echo done')
        assert result.stdout == 'done\n'

    def test_ignored_return_trap_does_not_fire(self):
        result = run_psh('f() { trap "" RETURN; :; }; f; echo done')
        assert result.stdout == 'done\n'

    def test_fires_on_each_call(self):
        result = run_psh('f() { trap "echo R" RETURN; :; }; f; f; echo done')
        assert result.stdout == 'R\nR\ndone\n'

    def test_exit_in_function_does_not_fire_return_trap(self):
        result = run_psh('f() { trap "echo R" RETURN; exit 4; }; f; echo never')
        assert result.stdout == ''
        assert result.returncode == 4

    def test_declare_ft_trace_attribute_inherits(self):
        result = run_psh('f() { :; }; declare -ft f; trap "echo R" RETURN; '
                         'f; echo done')
        assert result.stdout == 'R\ndone\n'

    def test_declare_F_shows_trace_flag(self):
        result = run_psh('f() { :; }; declare -ft f; declare -F')
        assert result.stdout == 'declare -ft f\n'

    def test_return_in_return_trap_fires_once_and_overrides(self):
        # bash 5.2 recurses forever here; psh deterministically fires the
        # trap once and adopts the action's return status (documented
        # divergence — see TrapManager.execute_return_trap).
        result = run_psh('f() { trap "return 3" RETURN; return 7; }; '
                         'f; echo after=$?')
        assert result.stdout == 'after=3\n'

    def test_nested_source_fires_for_each(self, tmp_path):
        inner = tmp_path / 'inner.sh'
        inner.write_text('echo inner-src\n')
        outer = tmp_path / 'outer.sh'
        outer.write_text(f'source {inner}\necho outer-src\n')
        result = run_psh(f'trap "echo R" RETURN; source {outer}; echo done')
        assert result.stdout == 'inner-src\nR\nouter-src\nR\ndone\n'


class TestFunctraceDebugEntry:
    """LOW-2: with set -T, DEBUG fires on function ENTRY too (bash d1/d2)."""

    def test_entry_fire_with_functrace(self):
        result = run_psh('set -T; trap "echo D" DEBUG; f() { :; }; f')
        # call-site fire + entry fire + body `:` fire
        assert result.stdout == 'D\nD\nD\n'

    def test_no_entry_fire_without_functrace(self):
        result = run_psh('trap "echo D" DEBUG; f() { :; }; f')
        # only the call-site fire (DEBUG not inherited into the body)
        assert result.stdout == 'D\n'

    def test_entry_fire_reports_call_text(self):
        result = run_psh('set -T; trap \'echo "[D:$BASH_COMMAND]"\' DEBUG; '
                         'f() { echo inf; }; f; echo top')
        assert result.stdout == ('[D:f]\n[D:f]\n[D:echo inf]\ninf\n'
                                 '[D:echo top]\ntop\n')

    def test_return_in_entry_fire_returns_from_function(self):
        # The entry fire's action can `return` — it returns from the
        # function being entered, not an internal-defect leak (bash rc=5).
        result = run_psh('set -T; f() { echo body; }; '
                         'trap "if [ \\${#FUNCNAME[@]} -gt 0 ]; then return 5; fi"'
                         ' DEBUG; f; echo rc=$?')
        assert result.stdout == 'rc=5\n'
