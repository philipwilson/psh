"""Conformance: normalize, expand assignments, then resolve ONCE (R3, #20 H10).

The reappraisal-#20 H10 defect: the executor decided a command's scope model,
its ``exec`` special case, and its POSIX prefix-error branch from raw
``function_manager.get_function`` / ``cmd_name in POSIX_SPECIAL_BUILTINS`` reads
taken BEFORE the mode-aware resolution ran. A POSIX-mode special builtin
shadowed by a same-named function therefore took the function temp-env-scope
path and DROPPED a prefix assignment that must persist.

The fix resolves once into a ``ResolvedCommand`` before any scope decision and
drives every downstream branch from it. These rows pin the fixed behavior and
the surrounding resolution/persistence matrix against live bash 5.2. Every row
is stdout-only (error stderr is suppressed or absent) because the conformance
framework compares stderr byte-for-byte and psh's ``psh:`` diagnostic prefix
differs from bash's argv0 by documented convention.
"""

from conformance_framework import ConformanceTest


class TestH10PosixSpecialShadowedByFunction(ConformanceTest):
    """A POSIX-mode special builtin wins over a same-named function, so its
    prefix assignments PERSIST — they are no longer dropped by a function
    temp-env scope selected from the raw function lookup."""

    def test_h10_headline_eval(self):
        # The reappraisal example verbatim.
        self.assert_identical_behavior(
            'eval(){ :; }; set -o posix; unset X; X=kept eval :; '
            'echo "${X-unset}"')

    def test_h10_colon(self):
        self.assert_identical_behavior(
            ':(){ echo fn; }; set -o posix; unset X; X=kept : ; '
            'echo "${X-unset}"')

    def test_h10_export_shadowed(self):
        self.assert_identical_behavior(
            'export(){ echo fn; }; set -o posix; unset Y; '
            '{ Y=kept export Z=1; } 2>/dev/null; echo "${Y-unset}"')

    def test_h10_dot_shadowed(self):
        self.assert_identical_behavior(
            '.(){ echo fn; }; set -o posix; unset X; '
            '{ X=kept . /dev/null; } 2>/dev/null; echo "${X-unset}"')

    def test_default_mode_function_wins_and_prefix_is_temporary(self):
        # Not POSIX: the function shadows the special builtin, and its prefix
        # is temporary (discarded on return) — must stay bash-identical.
        self.assert_identical_behavior(
            'eval(){ :; }; unset X; X=kept eval :; echo "${X-unset}"')

    def test_no_shadow_special_persists_posix(self):
        self.assert_identical_behavior(
            'set -o posix; unset X; X=kept :; echo "${X-unset}"')

    def test_no_shadow_special_temporary_default(self):
        self.assert_identical_behavior(
            'unset X; X=kept :; echo "${X-unset}"')


class TestPersistencePerCommandKind(ConformanceTest):
    """Prefix-assignment persistence by resolved command kind and mode."""

    def test_external_child_only(self):
        self.assert_identical_behavior(
            'V=v printenv V; echo "after=<${V-unset}>"')

    def test_regular_builtin_temporary_default(self):
        self.assert_identical_behavior('V=v true; echo "<${V-unset}>"')

    def test_regular_builtin_temporary_posix(self):
        self.assert_identical_behavior(
            'set -o posix; V=v true; echo "<${V-unset}>"')

    def test_special_builtin_temporary_default(self):
        self.assert_identical_behavior('V=v :; echo "<${V-unset}>"')

    def test_special_builtin_persists_posix(self):
        self.assert_identical_behavior(
            'set -o posix; V=v :; echo "<${V-unset}>"')

    def test_function_prefix_visible_then_restored(self):
        self.assert_identical_behavior(
            'f(){ echo "in=<$V>"; }; V=v f; echo "out=<${V-unset}>"')

    def test_function_body_declare_g_survives(self):
        self.assert_identical_behavior(
            'f(){ declare -g G=survived; }; V=v f; '
            'echo "V=<${V-unset}> G=<${G-unset}>"')

    def test_vanished_expansion_command_word_is_pure_assignment(self):
        self.assert_identical_behavior(
            'unset E; V=v $E; echo "rc=$? V=<${V-unset}>"')


class TestLeftToRightPrefixExpansion(ConformanceTest):
    """Prefix values expand left-to-right; each sees the ones to its left."""

    def test_later_sees_earlier(self):
        self.assert_identical_behavior('A=1 B=$A printenv B')

    def test_self_reference_uses_outer_value(self):
        self.assert_identical_behavior(
            'x=OUT; f(){ echo "<$x>"; }; x=$x f')

    def test_arith_side_effect_order(self):
        self.assert_identical_behavior(
            'n=0; A=$((n+=1)) B=$((n+=1)) printenv A B')

    def test_cmdsub_prefix_values(self):
        self.assert_identical_behavior(
            'A=$(echo one) B=$(echo two) printenv A B')


class TestResolutionPrecedenceAndNormalization(ConformanceTest):
    """Function/builtin/external precedence and command-word normalization,
    all flowing through the one resolution."""

    def test_function_shadows_builtin(self):
        self.assert_identical_behavior('echo(){ command echo FN; }; echo hi')

    def test_command_prefix_skips_function(self):
        self.assert_identical_behavior(
            'echo(){ echo FN; }; command echo real')

    def test_function_beats_special_builtin_default(self):
        self.assert_identical_behavior('exit(){ echo NOEXIT; }; exit')

    def test_backslash_finds_builtin(self):
        self.assert_identical_behavior(r'\echo hi')

    def test_quoted_command_word_finds_builtin(self):
        self.assert_identical_behavior('"echo" hi')

    def test_backslash_finds_function(self):
        self.assert_identical_behavior(r'greet(){ echo hello; }; \greet')

    def test_command_name_from_expansion(self):
        self.assert_identical_behavior('c=echo; $c fromvar')

    def test_backslash_exec_is_exec(self):
        self.assert_identical_behavior(r'\exec echo viaexec')


class TestPrefixInboundCarryEmptyArithSubscript(ConformanceTest):
    """Inbound carry from W2 via R2: ``$(( a[] ))`` (empty arith subscript).

    R2 re-routed this as an ARITHMETIC-evaluation concern; R3 does not touch
    arithmetic subscript evaluation, so it stays a documented divergence.
    Pinned as a BOTH-SIDES snapshot so it cannot vanish silently: psh
    fatal-discards (rc 1), bash warns-twice-continues (rc 0) — a documented
    difference, NOT a claim of parity. See docs/reviews boundary ledger R3.
    """

    def test_empty_arith_subscript_still_diverges(self):
        result = self.check_behavior('a=(1 2); echo $(( a[] )); echo done=$?')
        # bash: warns twice, the arithmetic yields 0, continues rc 0.
        assert result.bash_result.exit_code == 0
        assert 'done=0' in result.bash_result.stdout
        # psh (current, unchanged by R3): fatal-discards the command.
        assert 'done=0' not in result.psh_result.stdout
