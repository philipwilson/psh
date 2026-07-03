"""Reappraisal #16 Tier-2 BUILTINS-FLAGS cluster regressions.

Secondary flags added to existing builtins, each pinned to bash 5.2:
  [[ -o OPT ]] / [ -o OPT ]  shell-option test
  [[ -R N ]]  / [ -R N ]     nameref test
  unset -vf                  rejected (both flags)
  type consults the hash table
  printf "%()T"              empty time format defaults to %X
  umask -S MODE              sets AND echoes symbolically

exec -a/-c/-l live in test_exec_flags.py; pushd/popd -n and umask -S below
run in a subprocess where a fixed cwd / a process-global umask matter.
"""

import subprocess
import sys


def _run_psh(script):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True,
    )


# --- Item 1: [[ -o OPT ]] / [ -o OPT ] --------------------------------------

class TestShellOptionTest:
    def test_double_bracket_option_set(self, captured_shell):
        assert captured_shell.run_command(
            'set -o errexit; [[ -o errexit ]]') == 0

    def test_double_bracket_option_unset(self, captured_shell):
        assert captured_shell.run_command('[[ -o errexit ]]') == 1

    def test_double_bracket_short_flag_option(self, captured_shell):
        assert captured_shell.run_command('set -f; [[ -o noglob ]]') == 0

    def test_double_bracket_unknown_option_is_false(self, captured_shell):
        # bash: an unknown option name is simply false, not an error.
        assert captured_shell.run_command('[[ -o zzznotanopt ]]') == 1
        assert captured_shell.get_stderr() == ""

    def test_double_bracket_expands_operand(self, captured_shell):
        assert captured_shell.run_command(
            'o=errexit; set -e; [[ -o $o ]]') == 0

    def test_double_bracket_negated(self, captured_shell):
        assert captured_shell.run_command(
            'set +o errexit; [[ ! -o errexit ]]') == 0

    def test_single_bracket_option_set(self, captured_shell):
        assert captured_shell.run_command(
            'set -o errexit; [ -o errexit ]') == 0

    def test_test_builtin_option_set(self, captured_shell):
        assert captured_shell.run_command(
            'set -o errexit; test -o errexit') == 0

    def test_three_arg_or_still_works(self, captured_shell):
        # `-o` in a 3-arg test is still the logical-OR primary, not the
        # option test.
        assert captured_shell.run_command('[ a -o b ]') == 0
        assert captured_shell.run_command('[ "" -o "" ]') == 1


# --- Item 2: [[ -R N ]] / [ -R N ] nameref test ------------------------------

class TestNamerefTest:
    def test_double_bracket_set_nameref(self, captured_shell):
        assert captured_shell.run_command(
            'declare -n r=x; x=1; [[ -R r ]]') == 0

    def test_double_bracket_plain_var_is_false(self, captured_shell):
        assert captured_shell.run_command(
            'declare -n r=x; x=1; [[ -R x ]]') == 1

    def test_double_bracket_empty_nameref_is_false(self, captured_shell):
        assert captured_shell.run_command('declare -n r; [[ -R r ]]') == 1

    def test_double_bracket_target_unset_is_true(self, captured_shell):
        # A nameref with a target counts even if the target is unset (bash).
        assert captured_shell.run_command(
            'declare -n r=nonexist; [[ -R r ]]') == 0

    def test_single_bracket_set_nameref(self, captured_shell):
        assert captured_shell.run_command(
            'declare -n r=x; x=1; [ -R r ]') == 0

    def test_test_builtin_set_nameref(self, captured_shell):
        assert captured_shell.run_command(
            'declare -n r=x; x=1; test -R r') == 0

    def test_missing_name_is_false(self, captured_shell):
        assert captured_shell.run_command('[[ -R nope ]]') == 1


# --- Item 5: unset -vf rejected ----------------------------------------------

class TestUnsetBothFlags:
    def test_vf_rejected(self, captured_shell):
        rc = captured_shell.run_command('x=1; unset -vf x')
        assert rc == 1
        assert 'cannot simultaneously' in captured_shell.get_stderr()

    def test_fv_rejected(self, captured_shell):
        assert captured_shell.run_command('x=1; unset -fv x') == 1

    def test_vf_does_not_unset(self, captured_shell):
        captured_shell.run_command('x=survivor; unset -vf x')
        captured_shell.clear_output()
        captured_shell.run_command('echo "[$x]"')
        assert captured_shell.get_stdout() == "[survivor]\n"

    def test_vf_rejected_without_names(self, captured_shell):
        # bash rejects the flag combination regardless of operands.
        assert captured_shell.run_command('unset -vf') == 1


# --- Item 6: type consults the hash table ------------------------------------

class TestTypeConsultsHash:
    def test_type_reports_hashed(self, captured_shell):
        captured_shell.run_command('hash -p /bin/ls xyzls')
        captured_shell.clear_output()
        rc = captured_shell.run_command('type xyzls')
        assert rc == 0
        assert captured_shell.get_stdout() == "xyzls is hashed (/bin/ls)\n"

    def test_type_t_hashed_is_file(self, captured_shell):
        captured_shell.run_command('hash -p /bin/ls xyzls')
        captured_shell.clear_output()
        assert captured_shell.run_command('type -t xyzls') == 0
        assert captured_shell.get_stdout() == "file\n"

    def test_type_p_hashed_prints_path(self, captured_shell):
        captured_shell.run_command('hash -p /bin/ls xyzls')
        captured_shell.clear_output()
        assert captured_shell.run_command('type -p xyzls') == 0
        assert captured_shell.get_stdout() == "/bin/ls\n"

    def test_type_a_ignores_hash(self, captured_shell):
        # `type -a` lists PATH entries only; a hashed-only fake is "not found".
        captured_shell.run_command('hash -p /bin/ls xyzls')
        captured_shell.clear_output()
        assert captured_shell.run_command('type -a xyzls') == 1


# --- Item 7: printf "%()T" empty format --------------------------------------

class TestPrintfEmptyTimeFormat:
    def test_empty_format_epoch_zero(self, captured_shell):
        # Empty time format defaults to %X (bash). Compare against the same
        # strftime psh will produce for epoch 0.
        import time
        expected = time.strftime('%X', time.localtime(0)) + "\n"
        captured_shell.run_command('printf "%()T\\n" 0')
        assert captured_shell.get_stdout() == expected


# --- Item 4 & 8 (subprocess: fixed cwd / process-global umask) --------------

class TestPushdPopdNoCd:
    def test_pushd_n_adds_without_cd(self):
        result = _run_psh('cd /; pushd -n /tmp; dirs; pwd')
        assert result.returncode == 0
        assert result.stdout == "/ /tmp\n/ /tmp\n/\n"

    def test_pushd_n_inserts_below_top(self):
        result = _run_psh('cd /; pushd -n /usr; pushd -n /etc; dirs')
        assert result.returncode == 0
        assert result.stdout == "/ /usr\n/ /etc /usr\n/ /etc /usr\n"

    def test_pushd_n_does_not_validate(self):
        result = _run_psh('cd /; pushd -n /nonexistent12345; echo rc=$?; dirs')
        assert result.returncode == 0
        assert "/ /nonexistent12345" in result.stdout
        assert "rc=0" in result.stdout

    def test_popd_n_removes_below_top(self):
        result = _run_psh(
            'cd /; pushd /tmp >/dev/null; popd -n >/dev/null; dirs; pwd')
        assert result.returncode == 0
        assert result.stdout == "/tmp\n/tmp\n"

    def test_popd_n_empty_stack(self):
        result = _run_psh('cd /; popd -n; echo rc=$?')
        assert "rc=1" in result.stdout
        assert "directory stack empty" in result.stderr


class TestUmaskSymbolicWithMode:
    def test_umask_S_with_octal_mode(self):
        result = _run_psh('umask -S 022')
        assert result.returncode == 0
        assert result.stdout.strip() == "u=rwx,g=rx,o=rx"

    def test_umask_S_actually_sets_mask(self):
        result = _run_psh('umask -S 027; umask')
        assert result.returncode == 0
        # Symbolic echo of the new mask, then the octal reading.
        assert result.stdout == "u=rwx,g=rx,o=\n0027\n"

    def test_umask_plain_mode_silent(self):
        result = _run_psh('umask 022; umask')
        assert result.returncode == 0
        assert result.stdout == "0022\n"
