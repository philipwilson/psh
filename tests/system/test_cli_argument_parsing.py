"""psh's own flags must not be stolen from operand positions (reappraisal #15 I1).

parse_args used to strip option flags from ANYWHERE in argv (args.remove), so
`psh script.sh -i --norc foo` gave the script only `foo`, and `--parser bar`
as a -c operand killed psh itself with exit 2. Like bash, option parsing must
stop at the first non-option operand (the script name or the -c command
string); `--` (or the historical lone `-`) ends options explicitly.

All expectations here were pinned against bash 5.2 (tmp/truth_table_r15_i.py).
"""
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, 'PYTHONPATH': str(REPO_ROOT)}


def run_psh(*args, stdin_input=None, cwd=None):
    return subprocess.run([sys.executable, '-m', 'psh', *args],
                          capture_output=True, text=True, timeout=10,
                          input=stdin_input, cwd=cwd, env=ENV)


def make_args_script(tmp_path):
    script = tmp_path / 's_args.sh'
    script.write_text('echo "args:$@ n:$#"\n')
    return str(script)


class TestOperandPositionsPassThrough:
    """Words after the first operand belong to the script/command untouched."""

    def test_script_args_keep_flag_words(self, tmp_path):
        result = run_psh(make_args_script(tmp_path), '-i', '--norc', 'foo')
        assert result.returncode == 0
        assert result.stdout == 'args:-i --norc foo n:3\n'

    def test_c_operands_keep_value_flag_and_value(self):
        # --parser in operand position must not be consumed (this used to
        # make psh itself exit 2 with "unknown parser: bar").
        result = run_psh('-c', 'echo $0 $@', 'x', '--parser', 'bar')
        assert result.returncode == 0
        assert result.stdout == 'x --parser bar\n'
        assert result.stderr == ''

    def test_debug_flag_as_script_arg_is_not_activated(self, tmp_path):
        result = run_psh(make_args_script(tmp_path), '--debug-ast')
        assert result.returncode == 0
        assert result.stdout == 'args:--debug-ast n:1\n'
        assert result.stderr == ''  # no AST debug output

    def test_double_dash_protects_operands(self, tmp_path):
        result = run_psh('--', make_args_script(tmp_path), '-i', 'foo')
        assert result.returncode == 0
        assert result.stdout == 'args:-i foo n:2\n'

    def test_version_as_script_arg_passes_through(self, tmp_path):
        result = run_psh(make_args_script(tmp_path), '--version')
        assert result.returncode == 0
        assert result.stdout == 'args:--version n:1\n'

    def test_c_operand_double_dash_is_dollar0(self):
        # bash: `bash -c 'echo [$0] [$1]' -- a` prints "[--] [a]".
        result = run_psh('-c', 'echo [$0] [$1]', '--', 'a')
        assert result.returncode == 0
        assert result.stdout == '[--] [a]\n'

    def test_c_positional_params(self):
        result = run_psh('-c', 'echo $0:$1:$#', 'name', 'a', 'b')
        assert result.returncode == 0
        assert result.stdout == 'name:a:2\n'


class TestFlagPositionStillWorks:
    """Flags before the first operand are psh's own, as before."""

    def test_norc_consumed_before_script(self, tmp_path):
        result = run_psh('--norc', make_args_script(tmp_path))
        assert result.returncode == 0
        assert result.stdout == 'args: n:0\n'

    def test_debug_ast_active_before_c(self):
        result = run_psh('--debug-ast', '-c', 'echo hi')
        assert result.returncode == 0
        assert 'hi\n' in result.stdout
        assert 'SimpleCommand' in result.stderr  # AST debug fired

    def test_parser_selection_before_c(self):
        result = run_psh('--parser=pc', '-c', 'echo pc-ok')
        assert result.returncode == 0
        assert result.stdout == 'pc-ok\n'

    def test_double_dash_before_c_string(self):
        # bash: `bash -c -- 'echo x0'` runs the command.
        result = run_psh('-c', '--', 'echo x0')
        assert result.returncode == 0
        assert result.stdout == 'x0\n'

    def test_help_after_other_flags(self):
        result = run_psh('--norc', '--help')
        assert result.returncode == 0
        assert 'Usage' in result.stdout


class TestOptionErrors:
    def test_unknown_option_exits_2(self):
        result = run_psh('--bogus')
        assert result.returncode == 2
        assert 'invalid option' in result.stderr

    def test_bare_c_requires_argument(self):
        result = run_psh('-c')
        assert result.returncode == 2
        assert 'option requires an argument' in result.stderr

    def test_value_flag_missing_argument_exits_2(self):
        result = run_psh('--parser')
        assert result.returncode == 2
        assert 'requires an argument' in result.stderr


class TestLoneDashEndsOptions:
    """bash treats a lone `-` as the historical end-of-options marker."""

    def test_dash_reads_stdin(self):
        result = run_psh('-', stdin_input='echo dash\n')
        assert result.returncode == 0
        assert result.stdout == 'dash\n'
        assert result.stderr == ''

    def test_dash_then_script_operand(self, tmp_path):
        result = run_psh('-', make_args_script(tmp_path), 'x')
        assert result.returncode == 0
        assert result.stdout == 'args:x n:1\n'


class TestPosixShortOptions:
    """bash-style POSIX short options (reappraisal #16 Tier-2): psh used to
    reject -e/-u/-x/-v/-n/-f/-C and -s with exit 2. Pinned against bash 5.2."""

    def test_errexit_aborts(self):
        result = run_psh('-e', '-c', 'false; echo REACHED')
        assert result.returncode == 1
        assert 'REACHED' not in result.stdout

    def test_xtrace_traces_to_stderr(self):
        result = run_psh('-x', '-c', ':')
        assert result.returncode == 0
        assert '+ :' in result.stderr

    def test_nounset_errors_on_unset(self):
        result = run_psh('-u', '-c', 'echo $DEFINITELY_UNSET_XYZ')
        assert result.returncode != 0
        assert 'unbound variable' in result.stderr

    def test_noexec_parses_without_running(self):
        result = run_psh('-n', '-c', 'echo NEVER')
        assert result.returncode == 0
        assert result.stdout == ''

    def test_dollar_dash_reflects_set_options(self):
        # $- must contain the letters for the options set on the command line.
        result = run_psh('-e', '-c', 'echo $-')
        assert result.returncode == 0
        assert 'e' in result.stdout.strip()

    def test_cluster_sets_all(self):
        result = run_psh('-eu', '-c', 'echo $-')
        assert result.returncode == 0
        flags = result.stdout.strip()
        assert 'e' in flags and 'u' in flags

    def test_dash_s_reads_stdin_with_positionals(self):
        # -s: read commands from stdin; operands become $1, $2, ...; $0 stays
        # the shell name.
        result = run_psh('-s', 'foo', 'bar',
                         stdin_input='echo "$1/$2/$#"\n')
        assert result.returncode == 0
        assert result.stdout == 'foo/bar/2\n'

    def test_unknown_short_option_exits_2(self):
        result = run_psh('-Z', '-c', ':')
        assert result.returncode == 2
        assert 'invalid option' in result.stderr
