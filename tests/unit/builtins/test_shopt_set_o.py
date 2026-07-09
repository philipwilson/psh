"""shopt -o mode and the bash-faithful shopt flag grammar (task #10).

Every behaviour here was probe-pinned against /opt/homebrew/bin/bash 5.2.26
(tmp/optreflect probe batteries, 2026-07-09):

- `shopt -o NAME` queries the SET-O option table (`set -o` names), printing
  `name<pad>\ton/off` with exit status reflecting the state (0 on / 1 off).
- `shopt -so/-uo NAME` is exactly `set -o/+o NAME` (couplings included);
  the -o toggle path returns 0 even for an unknown name (bash quirk), while
  the shopt-table toggle path returns 1 for one.
- `shopt -po` prints reusable `set -o NAME` lines; `shopt -po` == `set +o`
  and `shopt -o` == `set -o` line for line.
- Flags cluster in any order (-so, -os, -sq, -pso); parsing stops at the
  first operand (`shopt extglob -s` treats -s as an OPERAND); -s with -u is
  an error; a bad flag prints a usage line and returns 2.
"""


class TestShoptSetOQuery:
    def test_query_off_prints_state_rc1(self, captured_shell):
        result = captured_shell.run_command('shopt -o errexit')
        assert result == 1
        assert captured_shell.get_stdout() == f"{'errexit':<15}\toff\n"

    def test_query_on_rc0(self, captured_shell):
        captured_shell.run_command('set -e')
        result = captured_shell.run_command('shopt -o errexit')
        assert result == 0
        assert captured_shell.get_stdout() == f"{'errexit':<15}\ton\n"

    def test_query_multiple_mixed_rc1(self, captured_shell):
        captured_shell.run_command('set -e')
        result = captured_shell.run_command('shopt -o errexit nounset')
        assert result == 1
        out = captured_shell.get_stdout().splitlines()
        assert out[0].endswith('on') and out[0].startswith('errexit')
        assert out[1].endswith('off') and out[1].startswith('nounset')

    def test_query_unknown_name(self, captured_shell):
        result = captured_shell.run_command('shopt -o nosuchopt')
        assert result == 1
        # -o mode: "invalid option name" (NOT "invalid shell option name").
        assert 'nosuchopt: invalid option name' in captured_shell.get_stderr()
        assert captured_shell.get_stdout() == ""

    def test_shopt_table_name_rejected_in_o_mode(self, captured_shell):
        # extglob lives in the shopt table, not the set -o table (bash).
        result = captured_shell.run_command('shopt -o extglob')
        assert result == 1
        assert 'extglob: invalid option name' in captured_shell.get_stderr()

    def test_set_o_name_rejected_without_o(self, captured_shell):
        """GREEN CONTROL (passes on base a0fbca20): guards that adding the
        -o mode did not leak set -o names into the plain shopt table."""
        result = captured_shell.run_command('shopt -s errexit')
        assert result == 1
        assert ('errexit: invalid shell option name'
                in captured_shell.get_stderr())

    def test_full_list_rc0_matches_set_o(self, captured_shell):
        result = captured_shell.run_command('shopt -o')
        assert result == 0
        shopt_out = captured_shell.get_stdout()
        assert f"{'errexit':<15}\toff" in shopt_out
        captured_shell.clear_output()
        captured_shell.run_command('set -o')
        # bash keeps `shopt -o` and `set -o` identical, line for line.
        assert captured_shell.get_stdout() == shopt_out

    def test_quiet_query_rc_only(self, captured_shell):
        assert captured_shell.run_command('shopt -qo errexit') == 1
        assert captured_shell.get_stdout() == ""
        captured_shell.run_command('set -e')
        assert captured_shell.run_command('shopt -qo errexit') == 0
        assert captured_shell.run_command('shopt -oq errexit') == 0  # cluster order

    def test_quiet_unknown_name_still_reports(self, captured_shell):
        result = captured_shell.run_command('shopt -qo nosuch')
        assert result == 1
        assert 'nosuch: invalid option name' in captured_shell.get_stderr()


class TestShoptSetOToggle:
    def test_so_sets_errexit(self, captured_shell):
        result = captured_shell.run_command('shopt -so errexit')
        assert result == 0
        assert captured_shell.state.options['errexit'] is True

    def test_uo_unsets_braceexpand(self, captured_shell):
        result = captured_shell.run_command('shopt -uo braceexpand')
        assert result == 0
        assert captured_shell.state.options['braceexpand'] is False

    def test_split_and_reversed_flag_forms(self, captured_shell):
        for form in ('shopt -s -o errexit', 'shopt -o -s errexit',
                     'shopt -os errexit'):
            captured_shell.run_command('set +e')
            assert captured_shell.run_command(form) == 0, form
            assert captured_shell.state.options['errexit'] is True, form

    def test_dollar_dash_reflects(self, captured_shell):
        captured_shell.run_command('shopt -so errexit')
        captured_shell.run_command('case $- in *e*) echo has_e;; esac')
        assert 'has_e' in captured_shell.get_stdout()

    def test_toggle_unknown_name_rc0_quirk(self, captured_shell):
        # bash quirk, probe-pinned: `shopt -so nosuch; echo $?` prints 0
        # (the message is still emitted). The shopt-table path returns 1.
        result = captured_shell.run_command('shopt -so nosuchopt')
        assert result == 0
        assert 'nosuchopt: invalid option name' in captured_shell.get_stderr()

    def test_toggle_partial_invalid_applies_valid(self, captured_shell):
        result = captured_shell.run_command('shopt -so errexit nosuch')
        assert result == 0
        assert captured_shell.state.options['errexit'] is True

    def test_so_vi_couples_edit_mode_like_set_o(self, captured_shell):
        assert captured_shell.run_command('shopt -so vi') == 0
        assert captured_shell.state.edit_mode == 'vi'
        assert captured_shell.state.options['vi'] is True
        assert captured_shell.state.options['emacs'] is False


class TestShoptSetOReusable:
    def test_po_single_off(self, captured_shell):
        result = captured_shell.run_command('shopt -po errexit')
        assert result == 1  # rc reflects state, like the display form
        assert captured_shell.get_stdout() == 'set +o errexit\n'

    def test_po_single_on(self, captured_shell):
        captured_shell.run_command('set -e')
        result = captured_shell.run_command('shopt -po errexit')
        assert result == 0
        assert captured_shell.get_stdout() == 'set -o errexit\n'

    def test_po_split_form(self, captured_shell):
        assert captured_shell.run_command('shopt -p -o errexit') == 1
        assert captured_shell.get_stdout() == 'set +o errexit\n'

    def test_po_full_list_matches_set_plus_o(self, captured_shell):
        assert captured_shell.run_command('shopt -po') == 0
        shopt_out = captured_shell.get_stdout()
        captured_shell.clear_output()
        captured_shell.run_command('set +o')
        assert captured_shell.get_stdout() == shopt_out

    def test_pso_lists_enabled_reusable(self, captured_shell):
        assert captured_shell.run_command('shopt -pso') == 0
        out = captured_shell.get_stdout()
        assert 'set -o braceexpand' in out
        assert '+o' not in out  # only the enabled subset


class TestShoptFlagGrammar:
    def test_sq_cluster_sets_silently(self, captured_shell):
        assert captured_shell.run_command('shopt -sq extglob') == 0
        assert captured_shell.get_stdout() == ""
        assert captured_shell.state.options['extglob'] is True

    def test_s_and_u_conflict(self, captured_shell):
        for form in ('shopt -s -u extglob', 'shopt -su extglob'):
            result = captured_shell.run_command(form)
            assert result == 1, form
            assert ('cannot set and unset shell options simultaneously'
                    in captured_shell.get_stderr())
            captured_shell.clear_output()

    def test_flag_after_operand_is_an_operand(self, captured_shell):
        # bash: parsing stops at the first operand; the later -s is a (bad)
        # option NAME, and extglob is queried, not set.
        result = captured_shell.run_command('shopt extglob -s')
        assert result == 1
        assert f"{'extglob':<15}\toff" in captured_shell.get_stdout()
        assert '-s: invalid shell option name' in captured_shell.get_stderr()
        assert captured_shell.state.options['extglob'] is False

    def test_bad_flag_usage_line_rc2(self, captured_shell):
        result = captured_shell.run_command('shopt -z')
        assert result == 2
        err = captured_shell.get_stderr()
        assert '-z: invalid option' in err
        assert 'usage: shopt [-pqsu] [-o] [optname ...]' in err

    def test_bare_s_lists_enabled(self, captured_shell):
        captured_shell.run_command('shopt -s extglob')
        captured_shell.clear_output()
        assert captured_shell.run_command('shopt -s') == 0
        out = captured_shell.get_stdout()
        assert f"{'extglob':<15}\ton" in out
        assert 'dotglob' not in out  # disabled options filtered out

    def test_bare_u_lists_disabled(self, captured_shell):
        assert captured_shell.run_command('shopt -u') == 0
        out = captured_shell.get_stdout()
        assert f"{'dotglob':<15}\toff" in out
        assert 'expand_aliases' not in out  # enabled-by-default, filtered

    def test_bare_so_lists_enabled_set_o(self, captured_shell):
        assert captured_shell.run_command('shopt -so') == 0
        out = captured_shell.get_stdout()
        assert f"{'braceexpand':<15}\ton" in out
        assert 'errexit' not in out

    def test_ps_lists_enabled_reusable(self, captured_shell):
        assert captured_shell.run_command('shopt -ps') == 0
        out = captured_shell.get_stdout()
        assert 'shopt -s expand_aliases' in out
        assert 'shopt -u' not in out

    def test_pq_quiet_wins(self, captured_shell):
        # -q suppresses -p's output; rc still reflects state.
        assert captured_shell.run_command('shopt -pq extglob') == 1
        assert captured_shell.get_stdout() == ""

    def test_bare_q_rc0(self, captured_shell):
        assert captured_shell.run_command('shopt -q') == 0
        assert captured_shell.run_command('shopt -qo') == 0
        assert captured_shell.get_stdout() == ""

    def test_shopt_table_partial_invalid_applies_valid_rc1(self, captured_shell):
        result = captured_shell.run_command('shopt -s extglob nosuch')
        assert result == 1
        assert captured_shell.state.options['extglob'] is True
        assert ('nosuch: invalid shell option name'
                in captured_shell.get_stderr())

    def test_double_dash_ends_flags(self, captured_shell):
        """GREEN CONTROL (passes on base a0fbca20): `--` handling survived
        the flag-parser rewrite."""
        assert captured_shell.run_command('shopt -- extglob') == 1
        assert f"{'extglob':<15}\toff" in captured_shell.get_stdout()
