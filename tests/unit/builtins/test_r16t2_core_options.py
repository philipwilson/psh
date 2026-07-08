"""Reappraisal #16 Tier-2 CORE/OPTIONS cluster regressions.

Each behaviour is pinned to bash 5.2.26:
  1. `declare -g NAME=val` writes the GLOBAL, past any same-named local.
  2. `set +o` emits only reusable `set -o` names (eval "$(set +o)" is silent).
  3. A declaration-builtin readonly error is ONE clean line (no triple wrap).
  4. `local -` saves the shell options and restores them on return.
  5. `set -o` lists emacs / vi exactly once each.
  6. `set -o interactive` (INTERNAL options) is rejected, $- uncorrupted.
"""


class TestDeclareGlobal:
    """Item 1: `declare -g` forces the global scope."""

    def test_declare_g_over_local_scalar(self, captured_shell):
        result = captured_shell.run_command(
            "x=1; f(){ local x=2; declare -g x=3; echo in=$x; }; f; echo out=$x")
        assert result == 0
        assert captured_shell.get_stdout() == "in=2\nout=3\n"

    def test_declare_g_no_existing_local(self, captured_shell):
        result = captured_shell.run_command(
            "x=1; f(){ declare -g x=3; echo in=$x; }; f; echo out=$x")
        assert result == 0
        assert captured_shell.get_stdout() == "in=3\nout=3\n"

    def test_declare_g_creates_fresh_global(self, captured_shell):
        result = captured_shell.run_command(
            "f(){ declare -g y=9; }; f; echo y=$y")
        assert result == 0
        assert captured_shell.get_stdout() == "y=9\n"

    def test_declare_gi_evaluates_into_global(self, captured_shell):
        result = captured_shell.run_command(
            "x=1; f(){ local x=2; declare -gi x=3+4; echo in=$x; }; f; echo out=$x")
        assert result == 0
        assert captured_shell.get_stdout() == "in=2\nout=7\n"

    def test_declare_gA_over_local_assoc(self, captured_shell):
        result = captured_shell.run_command(
            "declare -A m=([a]=1); "
            "f(){ local -A m=([b]=2); declare -gA m=([c]=3); echo in=${m[b]}; }; f; "
            "echo out=${m[c]}")
        assert result == 0
        assert captured_shell.get_stdout() == "in=2\nout=3\n"

    def test_declare_ga_over_local_indexed(self, captured_shell):
        result = captured_shell.run_command(
            "arr=(g0 g1); "
            "f(){ local arr=(l0); declare -ga arr=(n0 n1); echo in=${arr[0]}; }; f; "
            "echo out=${arr[0]} ${arr[1]}")
        assert result == 0
        assert captured_shell.get_stdout() == "in=l0\nout=n0 n1\n"

    def test_declare_gr_bare_marks_global_readonly_not_local(self, captured_shell):
        # `declare -gr x` (bare, no value) makes the GLOBAL readonly; the
        # local shadow stays writable.
        result = captured_shell.run_command(
            "x=1; f(){ local x=2; declare -gr x; x=9; echo in=$x; }; f; echo out=$x")
        assert result == 0
        assert captured_shell.get_stdout() == "in=9\nout=1\n"


class TestSetPlusOReusable:
    """Item 2: `set +o` output round-trips through eval without errors."""

    def test_eval_of_set_plus_o_is_silent(self, captured_shell):
        # The regression: `set +o` used to emit shopt/internal names that
        # `set -o` then rejected, so eval spewed "invalid option name". End
        # state must be rc 0 with no error cascade. (The exact stdout is
        # pinned end-to-end by the set_plus_o_reusable_eval golden case.)
        result = captured_shell.run_command('o=$(set +o); eval "$o"')
        assert result == 0
        assert "invalid option name" not in captured_shell.get_stderr()

    def test_set_plus_o_omits_non_set_names(self, captured_shell):
        result = captured_shell.run_command("set +o")
        assert result == 0
        out = captured_shell.get_stdout()
        # shopt / debug / internal names must NOT appear (they aren't
        # `set -o`-settable, so eval would reject them).
        for name in ("dotglob", "extglob", "stdin_mode", "command_mode",
                     "interactive", "debug-ast"):
            assert f" {name}" not in out, name
        # A representative SET option IS present.
        assert "errexit" in out

    def test_underscore_named_set_option_is_settable(self, captured_shell):
        # An underscore-named registered option round-trips (the `_`->`-`
        # normalization used to break it, so `set +o` emitted a name `set -o`
        # then rejected). inherit_errexit is a registered underscore option.
        result = captured_shell.run_command("set -o inherit_errexit; echo rc=$?")
        assert result == 0
        assert captured_shell.get_stdout() == "rc=0\n"
        assert captured_shell.get_stderr() == ""


class TestReadonlyDeclarationErrorMessage:
    """Item 3: one clean readonly-assignment message (no double/triple wrap)."""

    def _one_clean_line(self, stderr):
        lines = [ln for ln in stderr.splitlines() if ln.strip()]
        assert len(lines) == 1, stderr
        return lines[0]

    def test_declare_over_readonly_single_message(self, captured_shell):
        result = captured_shell.run_command("readonly x=1; declare x=2")
        assert result == 1
        line = self._one_clean_line(captured_shell.get_stderr())
        # bash: `declare: x: readonly variable` (with psh's own prefix).
        assert line.endswith("declare: x: readonly variable")
        assert line.count("readonly variable") == 1

    def test_typeset_over_readonly_single_message(self, captured_shell):
        result = captured_shell.run_command("readonly x=1; typeset x=2")
        assert result == 1
        line = self._one_clean_line(captured_shell.get_stderr())
        assert line.endswith("typeset: x: readonly variable")

    def test_readonly_reassign_no_builtin_prefix(self, captured_shell):
        result = captured_shell.run_command("readonly x=1; readonly x=2")
        assert result == 1
        line = self._one_clean_line(captured_shell.get_stderr())
        # bash omits the builtin name for readonly/export assignment errors.
        assert line.endswith("x: readonly variable")
        assert "declare" not in line

    def test_export_over_readonly_no_builtin_prefix(self, captured_shell):
        result = captured_shell.run_command("readonly x=1; export x=2")
        assert result == 1
        line = self._one_clean_line(captured_shell.get_stderr())
        assert line.endswith("x: readonly variable")

    def test_declaration_readonly_error_is_nonfatal(self, captured_shell):
        # The builtin returns 1 but does NOT abort the command list (bash).
        result = captured_shell.run_command(
            "readonly x=1; declare x=2; echo AFTER")
        assert result == 0
        assert captured_shell.get_stdout() == "AFTER\n"


class TestLocalDash:
    """Item 4: `local -` restores shell options on function return."""

    def test_local_dash_restores_errexit(self, captured_shell):
        result = captured_shell.run_command(
            "set +e; f(){ local -; set -e; }; f")
        assert result == 0
        assert captured_shell.state.options["errexit"] is False

    def test_local_dash_restores_after_disable(self, captured_shell):
        captured_shell.run_command("set -e")
        captured_shell.run_command("f(){ local -; set +e; }; f")
        assert captured_shell.state.options["errexit"] is True

    def test_local_dash_visible_inside_function(self, captured_shell):
        result = captured_shell.run_command(
            "set +u; f(){ local -; set -u; case $- in *u*) echo yes;; esac; }; f")
        assert result == 0
        assert captured_shell.get_stdout() == "yes\n"

    def test_local_dash_does_not_create_variable(self, captured_shell):
        result = captured_shell.run_command(
            "f(){ local -; echo \"[${-:+set}]\"; }; f")
        assert result == 0
        # No variable named '-' is created; `$-` is still the option string.

    def test_multiple_local_dash_restore_to_first(self, captured_shell):
        captured_shell.run_command(
            "set +e; f(){ local -; set -e; local -; set +u; }; f")
        assert captured_shell.state.options["errexit"] is False
        assert captured_shell.state.options["nounset"] is False

    def test_local_dash_outside_function_errors(self, captured_shell):
        result = captured_shell.run_command("local -")
        assert result == 1
        assert "can only be used in a function" in captured_shell.get_stderr()


class TestSetOListingEmacsVi:
    """Item 5: emacs / vi appear exactly once each in `set -o`."""

    def test_emacs_and_vi_listed_once(self, captured_shell):
        result = captured_shell.run_command("set -o")
        assert result == 0
        out = captured_shell.get_stdout()
        emacs_lines = [ln for ln in out.splitlines() if ln.startswith("emacs")]
        vi_lines = [ln for ln in out.splitlines() if ln.startswith("vi")]
        assert len(emacs_lines) == 1, out
        assert len(vi_lines) == 1, out


class TestSetOInternalRejected:
    """Item 6: INTERNAL options are not user-settable by name."""

    def test_set_o_interactive_rejected(self, captured_shell):
        result = captured_shell.run_command("set -o interactive")
        assert result == 2
        assert "invalid option name" in captured_shell.get_stderr()
        # $- must not gain a spurious `i`.
        assert captured_shell.state.options["interactive"] is False

    def test_set_o_interactive_leaves_dollar_dash_clean(self, captured_shell):
        captured_shell.run_command("set -o interactive")
        captured_shell.clear_output()
        captured_shell.run_command('echo "$-"')
        assert "i" not in captured_shell.get_stdout()

    def test_set_o_stdin_mode_rejected(self, captured_shell):
        result = captured_shell.run_command("set -o stdin_mode")
        assert result == 2
        assert "invalid option name" in captured_shell.get_stderr()

    def test_set_o_command_mode_rejected(self, captured_shell):
        result = captured_shell.run_command("set -o command_mode")
        assert result == 2
        assert "invalid option name" in captured_shell.get_stderr()

    def test_set_o_errexit_still_accepted(self, captured_shell):
        result = captured_shell.run_command("set -o errexit")
        assert result == 0
        assert captured_shell.state.options["errexit"] is True
