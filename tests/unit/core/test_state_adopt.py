"""Per-field tests for ShellState.clone_for_child() — the subshell inheritance chokepoint.

Reappraisal #15 (E1) found seven __init__ fields silently missing from the
old ``adopt()`` (replaced by ``clone_for_child()`` in v0.656); these tests
pin each copied field's semantics (copied, and independent where mutation
must not leak back). The companion drift-lock is
test_state_adopt_completeness.py. Bash-verified in tmp/e1_truth_table.sh
and tests/behavioral/golden_cases.yaml.

In-process trap tests use MANAGED signals (TERM/HUP) and pseudo-signals
only — setting a trap on an unmanaged signal (USR1) installs a
process-level handler in the test runner. Firing/OS-disposition tests
live in tests/integration/subshells/test_state_inheritance.py
(subprocess-based).
"""

from psh.shell import Shell


class TestAdoptedFields:
    """Fields clone_for_child() copies into a subshell-style child."""

    def test_script_name_is_inherited(self, captured_shell):
        captured_shell.state.script_name = "/path/to/script.sh"
        child = Shell.for_subshell(captured_shell)
        assert child.state.script_name == "/path/to/script.sh"
        assert child.state.get_special_variable('0') == "/path/to/script.sh"

    def test_function_stack_is_inherited_and_independent(self, captured_shell):
        captured_shell.state.function_stack.append("f")
        child = Shell.for_subshell(captured_shell)
        assert child.state.function_stack == ["f"]
        child.state.function_stack.append("g")
        assert captured_shell.state.function_stack == ["f"]

    def test_source_depth_is_inherited(self, captured_shell):
        captured_shell.state.source_depth = 2
        child = Shell.for_subshell(captured_shell)
        assert child.state.source_depth == 2

    def test_getopts_cursor_is_inherited(self, captured_shell):
        captured_shell.run_command("set -- -ab")
        captured_shell.run_command("getopts ab o")
        child = Shell.for_subshell(captured_shell)
        # The clustered-option walk (-ab) continues in the child: bash's
        # $(getopts ab o; echo $o) sees b after the parent consumed a.
        assert (child.state.getopts_state.char_offset
                == captured_shell.state.getopts_state.char_offset)
        child.run_command("getopts ab o")
        assert child.state.get_variable("o") == "b"

    def test_history_is_inherited_and_appends_do_not_leak(self, captured_shell):
        captured_shell.state.history.append("echo parent")
        child = Shell.for_subshell(captured_shell)
        assert "echo parent" in child.state.history
        child.state.history.append("echo child")
        assert "echo child" not in captured_shell.state.history

    def test_directory_stack_is_inherited_and_independent(self, captured_shell):
        from psh.builtins.directory_stack import DirectoryStack
        stack = DirectoryStack()
        stack.update_current("/start")  # seeds an empty stack (r19-T3:
        # initialize() was deleted once _ensure_stack became the only creator)
        stack.push("/pushed")
        captured_shell.state.directory_stack = stack
        child = Shell.for_subshell(captured_shell)
        assert child.state.directory_stack.stack == ["/pushed", "/start"]
        child.state.directory_stack.push("/child")
        assert captured_shell.state.directory_stack.stack == ["/pushed", "/start"]

    def test_absent_directory_stack_stays_absent(self, captured_shell):
        assert not hasattr(captured_shell.state, 'directory_stack')
        child = Shell.for_subshell(captured_shell)
        assert not hasattr(child.state, 'directory_stack')

    def test_seconds_baseline_is_inherited(self, captured_shell):
        captured_shell.run_command("SECONDS=500")
        child = Shell.for_subshell(captured_shell)
        # bash: SECONDS=500; (echo $SECONDS) prints 500.
        assert 500 <= int(child.state.get_variable("SECONDS")) <= 502

    def test_deactivated_specials_stay_deactivated(self, captured_shell):
        captured_shell.run_command("unset RANDOM")
        captured_shell.run_command("unset SECONDS")
        child = Shell.for_subshell(captured_shell)
        # bash: after unset, RANDOM/SECONDS are plain (empty) in children too.
        assert child.state.get_variable("RANDOM") == ""
        assert child.state.get_variable("SECONDS") == ""


class TestAdoptedTraps:
    """Trap inheritance: listable-but-never-firing (POSIX saved=$(trap))."""

    def test_parent_trap_is_listed_in_child(self, captured_shell):
        captured_shell.run_command("trap 'echo hi' TERM")
        child = Shell.for_subshell(captured_shell)
        assert "trap -- 'echo hi' SIGTERM" in child.trap_manager.show_traps()[0]

    def test_parent_trap_never_fires_in_child(self, captured_shell):
        captured_shell.run_command("trap 'child_fired=1' TERM")
        child = Shell.for_subshell(captured_shell)
        assert child.trap_manager.get_handler('TERM') is None
        child.trap_manager.execute_trap('TERM')
        assert child.state.get_variable('child_fired') == ""

    def test_first_modification_drops_all_inherited(self, captured_shell):
        # bash probe: `trap A ...; (trap - HUP; trap)` lists nothing — ANY
        # trap modification in the child drops every inherited entry.
        captured_shell.run_command("trap 'echo hi' TERM")
        child = Shell.for_subshell(captured_shell)
        child.run_command("trap - HUP")
        assert child.trap_manager.show_traps()[0] == ""
        # The parent's trap is untouched.
        assert "SIGTERM" in captured_shell.trap_manager.show_traps()[0]

    def test_ignored_trap_stays_in_effect_in_child(self, captured_shell):
        captured_shell.run_command("trap '' TERM")
        child = Shell.for_subshell(captured_shell)
        # '' is genuinely in effect (not merely listable) ...
        assert child.trap_manager.get_handler('TERM') == ''
        # ... and survives the child's first trap modification (bash).
        child.run_command("trap 'echo x' HUP")
        assert "trap -- '' SIGTERM" in child.trap_manager.show_traps()[0]

    def test_child_own_trap_replaces_inherited(self, captured_shell):
        captured_shell.run_command("trap 'echo parent' TERM")
        child = Shell.for_subshell(captured_shell)
        child.run_command("trap 'echo child' TERM")
        assert child.trap_manager.get_handler('TERM') == 'echo child'
        assert captured_shell.trap_manager.get_handler('TERM') == 'echo parent'

    def test_inherited_exit_trap_does_not_fire_at_child_exit(self, captured_shell):
        captured_shell.run_command("trap 'pfired=yes' EXIT")
        child = Shell.for_subshell(captured_shell)
        child.trap_manager.execute_exit_trap()
        assert child.state.get_variable('pfired') == ""
        # The parent's own EXIT trap still fires (in the parent).
        captured_shell.trap_manager.execute_exit_trap()
        assert captured_shell.state.get_variable('pfired') == "yes"

    def test_child_own_exit_trap_fires(self, captured_shell):
        child = Shell.for_subshell(captured_shell)
        child.run_command("trap 'cfired=yes' EXIT")
        child.trap_manager.execute_exit_trap()
        assert child.state.get_variable('cfired') == "yes"

    def test_errtrace_keeps_err_trap_live_in_child(self, captured_shell):
        # set -E: the ERR trap is inherited by subshell environments (bash).
        captured_shell.run_command("set -E; trap 'echo E' ERR")
        child = Shell.for_subshell(captured_shell)
        assert child.trap_manager.get_handler('ERR') == 'echo E'

    def test_functrace_keeps_debug_trap_live_in_child(self, captured_shell):
        # set -T: the DEBUG trap is inherited by subshell environments (bash).
        captured_shell.run_command("set -T; trap 'echo D' DEBUG")
        child = Shell.for_subshell(captured_shell)
        assert child.trap_manager.get_handler('DEBUG') == 'echo D'

    def test_debug_trap_inert_in_child_without_functrace(self, captured_shell):
        captured_shell.run_command("trap 'echo D' DEBUG")
        child = Shell.for_subshell(captured_shell)
        assert child.trap_manager.get_handler('DEBUG') is None
        assert "DEBUG" in child.trap_manager.show_traps()[0]

    def test_listing_order_matches_bash(self, captured_shell):
        # bash: EXIT (signal 0) first, real signals by number, then DEBUG/ERR.
        captured_shell.run_command(
            "trap : EXIT; trap : DEBUG; trap : ERR; trap : TERM; trap : HUP")
        lines = captured_shell.trap_manager.show_traps()[0].splitlines()
        names = [line.rsplit(' ', 1)[1] for line in lines]
        assert names == ['EXIT', 'SIGHUP', 'SIGTERM', 'DEBUG', 'ERR']
