"""
Conformance tests for `trap` signal-spec normalization.

`trap` accepts a signal as a bare name (`INT`), a `SIG`-prefixed name
(`SIGINT`), or a number (`2`) — all referring to the same signal. Before
v0.487 psh keyed trap handlers by the raw spec, so two everyday idioms broke
(reappraisal #13 HIGH):

  - `trap … SIGINT` was rejected outright ("invalid signal specification");
  - `trap … 2` for a managed signal (INT/TERM/HUP/QUIT) was accepted but
    never fired — the shell died on the default action — because the
    name-keyed signal dispatch never matched the number key.

All three spellings now normalize to one canonical key, so they set, fire,
and query interchangeably. Verified against bash 5.3.15 (Wave 0.2 retune:
the usage line is bash 5.3's `trap [-Plp] [[action] signal_spec ...]`, and
`trap -P` is pinned in TestTrapPrintActionsConformance).
"""

from conformance_framework import ConformanceTest
from shell_oracle import is_comparable, run_bash, run_psh


class TestTrapSignalSpecConformance(ConformanceTest):
    """SIG-prefixed names, bare names, and numbers are interchangeable."""

    def test_sig_prefixed_name_accepted(self):
        self.assert_identical_behavior("trap 'echo x' SIGINT && echo OK")

    def test_sig_prefixed_other_signals(self):
        self.assert_identical_behavior("trap 'echo a' SIGUSR1 && echo OK")
        self.assert_identical_behavior("trap 'echo a' SIGTERM && echo OK")

    def test_invalid_signal_rejected(self):
        # An unknown signal is still rejected (exit 1 from trap) with the same
        # diagnostic — compared by exit code + stderr substring because the
        # bash `line N:` prefix differs from psh's by design.
        cmd = "trap 'echo x' NOTASIGNAL; echo rc=$?"
        psh = run_psh(['-c', cmd])
        assert is_comparable(psh), psh
        bash = run_bash(['-c', cmd])
        assert is_comparable(bash), bash
        assert psh.stdout == bash.stdout == "rc=1\n"
        assert 'invalid signal specification' in psh.stderr
        assert 'invalid signal specification' in bash.stderr


class TestTrapFiresConformance(ConformanceTest):
    """A trap set by name / SIG-name / number all fire on delivery."""

    def test_numbered_managed_signal_fires(self):
        self.assert_identical_behavior(
            "trap 'echo GOT' 2\nkill -2 $$\necho after")

    def test_numbered_term_fires(self):
        self.assert_identical_behavior(
            "trap 'echo T' 15\nkill -15 $$\necho after")

    def test_sig_name_signal_fires(self):
        self.assert_identical_behavior(
            "trap 'echo GOT' SIGINT\nkill -INT $$\necho after")

    def test_bare_name_signal_fires(self):
        self.assert_identical_behavior(
            "trap 'echo GOT' INT\nkill -INT $$\necho after")


class TestTrapQueryConformance(ConformanceTest):
    """`trap -p` finds a trap regardless of how the query names the signal."""

    def test_query_by_sig_prefixed_name(self):
        self.assert_identical_behavior("trap 'echo x' INT; trap -p SIGINT")

    def test_query_by_number(self):
        self.assert_identical_behavior("trap 'echo x' INT; trap -p 2")

    def test_query_by_bare_name(self):
        self.assert_identical_behavior("trap 'echo x' SIGINT; trap -p INT")

    def test_reset_then_query_empty(self):
        self.assert_identical_behavior(
            "trap 'echo x' SIGINT; trap - SIGINT; trap -p SIGINT; echo done")


class TestTrapPosixNumericForms(ConformanceTest):
    """POSIX numeric forms (reappraisal #15 F2): condition 0 is the EXIT
    trap, and operands led by a signal number are a reset request."""

    def test_trap_0_fires_at_exit(self):
        self.assert_identical_behavior('trap "echo bye" 0; echo rc=$?')

    def test_trap_0_keeps_exit_status(self):
        self.assert_identical_behavior('trap "echo bye" 0; exit 3')

    def test_trap_0_lists_as_exit(self):
        self.assert_identical_behavior("trap 'echo bye' 0; trap -p; trap - EXIT")

    def test_query_exit_trap_by_0(self):
        self.assert_identical_behavior("trap 'echo bye' EXIT; trap -p 0; trap - 0")

    def test_trap_number_resets(self):
        self.assert_identical_behavior(
            'trap "echo X" INT; trap 2; trap -p; echo rc=$?')

    def test_trap_leading_number_resets_all_operands(self):
        self.assert_identical_behavior(
            'trap "echo A" INT; trap "echo B" TERM; trap 2 15; trap -p; echo rc=$?')

    def test_trap_0_alone_resets_exit_trap(self):
        self.assert_identical_behavior('trap "echo bye" 0; trap 0; echo rc=$?')

    def test_single_name_operand_resets(self):
        self.assert_identical_behavior(
            "trap 'echo X' INT; trap INT; trap -p; echo rc=$?")

    def test_single_invalid_operand_usage_error(self):
        # Neither shell prefixes its usage message, so full comparison works.
        self.assert_identical_behavior('trap NOTASIGNAL; echo rc=$?')
        self.assert_identical_behavior('trap 999; echo rc=$?')

    def test_leading_non_signal_number_is_action(self):
        self.assert_identical_behavior('trap 999 2; trap -p; trap - INT')


class TestTrapSignalNameCoverage(ConformanceTest):
    """Every platform signal name is a valid trap spec (not just the old
    13-name whitelist); KILL/STOP are accepted like bash even though they
    can never fire."""

    def test_winch_registers_lists_resets(self):
        self.assert_identical_behavior(
            "trap 'echo w' WINCH; echo rc=$?; trap -p; trap - WINCH; trap -p; echo done")

    def test_segv_vtalrm(self):
        self.assert_identical_behavior("trap 'echo s' SIGSEGV; echo rc=$?; trap -p")
        self.assert_identical_behavior("trap 'echo v' VTALRM; echo rc=$?; trap -p")

    def test_kill_stop_accepted(self):
        self.assert_identical_behavior("trap 'echo k' KILL; echo rc=$?; trap -p")
        self.assert_identical_behavior("trap 'echo st' STOP; echo rc=$?; trap -p")

    def test_case_insensitive_names(self):
        self.assert_identical_behavior("trap 'echo w' sigwinch; echo rc=$?; trap -p")


class TestTrapDisplayConformance(ConformanceTest):
    """`trap`/`trap -p` output order matches bash."""

    def test_listing_numeric_order(self):
        # bash: EXIT first, real signals by number, DEBUG/ERR after all.
        self.assert_identical_behavior(
            "trap true CHLD; trap true INT; trap true EXIT; trap true DEBUG; trap")

    def test_query_order_follows_arguments(self):
        self.assert_identical_behavior(
            "trap true INT; trap true USR1; trap -p USR1 INT")

    def test_trap_p_invalid_signal(self):
        # stderr prefixes differ (`bash: line N:`), so compare stdout/exit
        # plus the diagnostic substring.
        cmd = "trap -p NOSUCHSIG; echo rc=$?"
        psh = run_psh(['-c', cmd])
        assert is_comparable(psh), psh
        bash = run_bash(['-c', cmd])
        assert is_comparable(bash), bash
        assert psh.stdout == bash.stdout == "rc=1\n"
        assert 'NOSUCHSIG: invalid signal specification' in psh.stderr
        assert 'NOSUCHSIG: invalid signal specification' in bash.stderr


class TestTrapPrintActionsConformance(ConformanceTest):
    """`trap -P` prints the bare action per operand.

    bash 5.3 CHANGES, 5.3-alpha "New Features in Bash" item j: "`trap' has a
    new -P option that prints the trap action associated with each signal
    argument". Wave 0.2 retune, verified against bash 5.3.15; the usage-line
    cells in test_error_prefix_conformance.py and
    test_single_invalid_operand_usage_error above are the gate nodes.
    Diagnostics carry the `<shell>: line N:` prefix, so those rows send
    stderr to /dev/null and compare stdout + `$?`.
    """

    def test_P_prints_bare_action_per_operand(self):
        self.assert_identical_behavior(
            "trap 'echo hi' INT; trap 'echo bye' EXIT; trap -P INT EXIT; echo rc=$?")

    def test_P_unset_reset_and_ignored(self):
        # unset/reset print nothing; the ignored ('') action is an empty line
        self.assert_identical_behavior(
            "trap -P INT; echo rc=$?; trap 'echo hi' INT; trap - INT; trap -P INT; "
            "echo rc=$?; trap '' INT; trap -P INT | od -c")

    def test_P_keeps_the_raw_action_text(self):
        self.assert_identical_behavior(
            "trap \"echo 'x'\" INT; trap -P INT; trap -p INT")

    def test_P_repeats_operands_in_query_order(self):
        self.assert_identical_behavior(
            "trap 'echo hi' INT; trap 'echo z' 0; trap -P 2 SIGINT int EXIT 0")

    def test_P_invalid_spec_rc1_valid_still_printed(self):
        self.assert_identical_behavior(
            "trap 'echo hi' INT; trap -P INT NOSUCH 2>/dev/null; echo rc=$?")

    def test_P_without_operand_rc2(self):
        self.assert_identical_behavior("trap -P 2>/dev/null; echo rc=$?")

    def test_p_and_P_together_rc2(self):
        self.assert_identical_behavior("trap -pP INT 2>/dev/null; echo rc=$?")

    def test_P_usage_errors_exit_posix_shell_suppressibly(self):
        self.assert_identical_behavior(
            "set -o posix; trap -P 2>/dev/null || echo caught; "
            "trap -pP INT 2>/dev/null || echo caught; echo survived")
        self.assert_identical_behavior(
            "set -o posix; trap -P 2>/dev/null; echo not-reached")

    def test_l_dominates_P(self):
        self.assert_identical_behavior(
            "trap 'echo hi' INT; trap -lP INT | grep -c SIGINT")

    def test_l_does_not_rescue_P_usage_errors(self):
        # bash 5.3.15 checks the -P usage errors before honouring -l: no
        # listing, rc 2 (empirical; verifier round 1 of Wave 0.2 pkg E).
        self.assert_identical_behavior(
            "trap -lP 2>/dev/null; echo rc=$?; trap -lpP INT 2>/dev/null; "
            "echo rc=$?; trap -l -p -P INT 2>/dev/null; echo rc=$?; "
            "trap -Pl 2>/dev/null | grep -c SIGINT")

    def test_l_with_P_usage_error_exits_posix_shell(self):
        self.assert_identical_behavior(
            "set -o posix; trap -lpP INT 2>/dev/null; echo not-reached")
        self.assert_identical_behavior(
            "set -o posix; trap -lP 2>/dev/null || echo caught; echo survived")


class TestTrapSubstitutionExitConformance(ConformanceTest):
    """Substitution children run their own EXIT trap (bash)."""

    def test_command_substitution_child(self):
        self.assert_identical_behavior('x=$(trap "echo inner" 0); echo "x=$x"')

    def test_command_substitution_exit_n(self):
        self.assert_identical_behavior(
            'x=$(trap "echo bye" EXIT; exit 5); echo "x=$x rc=$?"')

    def test_process_substitution_child(self):
        self.assert_identical_behavior(
            'cat <(trap "echo bye" EXIT; echo body); echo after')


class TestReturnTrapConformance(ConformanceTest):
    """RETURN pseudo-signal traps (reappraisal #17 Tier-2, v0.617): fire at
    every function return and end of `source`, with bash's hiding model
    (hidden for a function's extent unless `set -T`/`declare -ft`). Flips the
    ch17 "DEBUG/ERR/RETURN traps" row to Full support. (The action's own
    `return N` overriding the status is a documented deliberate divergence:
    bash 5.2 recurses forever there, so it is not asserted here.)"""

    def test_return_trap_fires_at_function_return(self):
        self.assert_identical_behavior(
            "f(){ trap 'echo RET' RETURN; }; f; echo after")

    def test_return_trap_preserves_pre_return_status(self):
        self.assert_identical_behavior(
            "f(){ trap 'echo RET' RETURN; return 5; }; f; echo rc=$?")

    def test_return_trap_hidden_for_function_extent(self):
        self.assert_identical_behavior(
            "f(){ trap 'echo RET' RETURN; }; trap -p RETURN; f; trap -p RETURN")

    def test_return_listed_with_other_pseudo_signals(self):
        self.assert_identical_behavior(
            "trap 'echo t' RETURN EXIT DEBUG ERR; trap -l >/dev/null; echo ok")

    def test_functrace_return_trap_fires_in_untraced_call(self):
        self.assert_identical_behavior(
            "set -T; f(){ echo in; }; trap 'echo R' RETURN; f; echo done")
