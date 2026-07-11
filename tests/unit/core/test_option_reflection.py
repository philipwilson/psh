"""SHELLOPTS / BASHOPTS option-reflection variables (task #10).

Behaviour probe-pinned against /opt/homebrew/bin/bash 5.2.26
(tmp/optreflect probe batteries, 2026-07-09):

- $SHELLOPTS is a DYNAMIC colon-joined sorted list of the ENABLED set -o
  options; $BASHOPTS is its shopt-table twin. Both recompute on every read
  (errexit joins after `set -e`, leaves after `set +e`).
- Both are READONLY: assignment fails ("readonly variable") and `unset` is
  refused ("cannot unset: readonly variable"); the shell continues.
- Neither is exported by default. `export SHELLOPTS` works (readonly limits
  the value, not the metadata) and the env entry then TRACKS option changes.
- Inherited via the environment at startup, each listed valid option is
  ENABLED before anything runs and the variable becomes exported
  (declare -rx). Unknown SHELLOPTS names warn; unknown BASHOPTS names are
  silently ignored (bash). bash-only set -o names psh does not implement
  (interactive-comments, keyword, ...) are skipped silently so a psh child
  of a bash parent doesn't spew warnings. (`hashall` is psh's NATIVE name
  since #34 — it imports like any other option, not via an alias.)

The parallel live-bash comparison is the shellopts_* golden cases.
"""

import os
import subprocess
import sys

from psh.core.option_registry import SET_O_OPTION_NAMES


def run_psh(cmd, env_extra=None):
    env = dict(os.environ)
    env.pop('DISPLAY', None)
    env.pop('XAUTHORITY', None)
    env.pop('SHELLOPTS', None)
    env.pop('BASHOPTS', None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, '-m', 'psh', '--norc', '-c', cmd],
                          capture_output=True, text=True, env=env, timeout=15)


def parts(value):
    return value.split(':') if value else []


class TestShelloptsDynamicValue:
    def test_defaults_present_errexit_absent(self, captured_shell):
        captured_shell.run_command('echo "$SHELLOPTS"')
        got = parts(captured_shell.get_stdout().strip())
        assert 'braceexpand' in got and 'hashall' in got
        assert 'errexit' not in got

    def test_errexit_joins_and_leaves(self, captured_shell):
        captured_shell.run_command('set -e')
        captured_shell.run_command('echo "$SHELLOPTS"')
        assert 'errexit' in parts(captured_shell.get_stdout().strip())
        captured_shell.clear_output()
        captured_shell.run_command('set +e')
        captured_shell.run_command('echo "$SHELLOPTS"')
        assert 'errexit' not in parts(captured_shell.get_stdout().strip())

    def test_sorted(self, captured_shell):
        captured_shell.run_command('set -ex')
        captured_shell.run_command('echo "$SHELLOPTS"')
        got = parts(captured_shell.get_stdout().strip())
        assert got == sorted(got)

    def test_only_set_o_names(self, captured_shell):
        captured_shell.run_command('shopt -s extglob')  # shopt table: BASHOPTS
        captured_shell.run_command('echo "$SHELLOPTS"')
        got = parts(captured_shell.get_stdout().strip())
        assert 'extglob' not in got
        assert set(got) <= set(SET_O_OPTION_NAMES)

    def test_bashopts_twin(self, captured_shell):
        captured_shell.run_command('echo "$BASHOPTS"')
        got = parts(captured_shell.get_stdout().strip())
        assert 'expand_aliases' in got and 'extglob' not in got
        captured_shell.clear_output()
        captured_shell.run_command('shopt -s extglob')
        captured_shell.run_command('echo "$BASHOPTS"')
        got = parts(captured_shell.get_stdout().strip())
        assert 'extglob' in got and got == sorted(got)


class TestShelloptsReadonly:
    def test_assignment_refused(self, captured_shell):
        result = captured_shell.run_command('SHELLOPTS=xtrace')
        assert result == 1
        assert 'SHELLOPTS: readonly variable' in captured_shell.get_stderr()
        # The assignment did NOT go through (xtrace still off).
        assert captured_shell.state.options['xtrace'] is False

    def test_unset_refused_still_computed(self, captured_shell):
        result = captured_shell.run_command('unset SHELLOPTS')
        assert result == 1
        assert ('SHELLOPTS: cannot unset: readonly variable'
                in captured_shell.get_stderr())
        captured_shell.clear_output()
        captured_shell.run_command('echo "$SHELLOPTS"')
        assert 'braceexpand' in captured_shell.get_stdout()

    def test_prefix_assignment_reports_and_runs(self, captured_shell):
        # bash: `SHELLOPTS=x cmd` reports the readonly error, skips that one
        # binding, and RUNS the command with status 0.
        result = captured_shell.run_command('SHELLOPTS=xtrace echo RAN')
        assert result == 0
        assert captured_shell.get_stdout() == 'RAN\n'
        assert 'SHELLOPTS: readonly variable' in captured_shell.get_stderr()

    def test_bashopts_assignment_refused(self, captured_shell):
        result = captured_shell.run_command('BASHOPTS=x')
        assert result == 1
        assert 'BASHOPTS: readonly variable' in captured_shell.get_stderr()

    def test_bashopts_unset_refused(self, captured_shell):
        assert captured_shell.run_command('unset BASHOPTS') == 1

    def test_declare_p_shows_readonly(self, captured_shell):
        result = captured_shell.run_command('declare -p SHELLOPTS')
        assert result == 0
        out = captured_shell.get_stdout()
        assert out.startswith('declare -r SHELLOPTS="')
        assert 'braceexpand' in out

    def test_readonly_attr_remove_refused(self, captured_shell):
        result = captured_shell.run_command('declare +r SHELLOPTS')
        assert result == 1
        assert 'SHELLOPTS: readonly variable' in captured_shell.get_stderr()


class TestShelloptsExport:
    def test_not_exported_by_default(self, captured_shell):
        assert 'SHELLOPTS' not in captured_shell.state.env
        assert 'BASHOPTS' not in captured_shell.state.env

    def test_export_materializes_and_tracks(self, captured_shell):
        captured_shell.run_command('export SHELLOPTS')
        value = captured_shell.state.env.get('SHELLOPTS', '')
        assert 'braceexpand' in parts(value)
        assert 'errexit' not in parts(value)
        # The exported entry tracks option changes (bash regenerates it).
        captured_shell.run_command('set -e')
        assert 'errexit' in parts(captured_shell.state.env['SHELLOPTS'])
        captured_shell.run_command('set +e')
        assert 'errexit' not in parts(captured_shell.state.env['SHELLOPTS'])

    def test_declare_p_after_export_shows_rx(self, captured_shell):
        captured_shell.run_command('export SHELLOPTS')
        captured_shell.run_command('declare -p SHELLOPTS')
        assert captured_shell.get_stdout().startswith(
            'declare -rx SHELLOPTS="')

    def test_export_n_removes_entry(self, captured_shell):
        captured_shell.run_command('export SHELLOPTS')
        assert 'SHELLOPTS' in captured_shell.state.env
        captured_shell.run_command('export -n SHELLOPTS')
        assert 'SHELLOPTS' not in captured_shell.state.env

    def test_subshell_isolation(self):
        # Subprocess: a forked subshell writes at the fd level, which the
        # captured_shell buffers don't see.
        r = run_psh(
            '(set -e; case ":$SHELLOPTS:" in *:errexit:*) echo in_yes;; esac); '
            'case ":$SHELLOPTS:" in *:errexit:*) echo out_yes;; *) echo out_no;; esac')
        assert r.stdout == 'in_yes\nout_no\n'


class TestShelloptsEnvImport:
    """Startup import of inherited SHELLOPTS/BASHOPTS (subprocess psh)."""

    def test_activates_listed_options(self):
        r = run_psh('echo "$-"', {'SHELLOPTS': 'xtrace:errexit'})
        assert r.returncode == 0
        flags = r.stdout.strip()
        assert 'e' in flags and 'x' in flags

    def test_xtrace_live_at_startup(self):
        r = run_psh('echo hi', {'SHELLOPTS': 'xtrace'})
        assert r.stdout == 'hi\n'
        assert '+ echo hi' in r.stderr

    def test_errexit_live(self):
        r = run_psh('false; echo unreachable', {'SHELLOPTS': 'errexit'})
        assert r.returncode == 1
        assert r.stdout == ''

    def test_value_regenerated_sorted(self):
        # The inherited raw string is replaced by the live computed value.
        r = run_psh('echo "$SHELLOPTS"', {'SHELLOPTS': 'xtrace:errexit'})
        got = parts(r.stdout.strip())
        assert 'braceexpand' in got and 'errexit' in got and 'xtrace' in got
        assert got == sorted(got)

    def test_imported_is_exported(self):
        r = run_psh('env | grep "^SHELLOPTS="', {'SHELLOPTS': 'errexit'})
        assert r.returncode == 0
        assert 'errexit' in r.stdout

    def test_imported_declare_p_rx(self):
        r = run_psh('declare -p SHELLOPTS', {'SHELLOPTS': 'errexit'})
        assert r.stdout.startswith('declare -rx SHELLOPTS="')

    def test_imported_env_entry_tracks_changes(self):
        r = run_psh('set +e; env | grep "^SHELLOPTS=" | grep -c errexit',
                    {'SHELLOPTS': 'errexit'})
        assert r.stdout.strip() == '0'

    def test_unknown_name_warns_but_continues(self):
        r = run_psh('echo "$-"; echo alive', {'SHELLOPTS': 'bogus:errexit'})
        assert 'bogus: invalid option name' in r.stderr
        assert 'e' in r.stdout.splitlines()[0]
        assert 'alive' in r.stdout

    def test_bash_only_names_silently_accepted(self):
        # A bash parent's exported SHELLOPTS routinely carries hashall (psh's
        # NATIVE name too, since #34) and bash-only names psh does not
        # implement (interactive-comments, ...) — neither must spew a warning.
        r = run_psh('echo "$SHELLOPTS"; echo ok', {
            'SHELLOPTS': 'braceexpand:hashall:interactive-comments'})
        assert r.stderr == ''
        assert 'hashall' in parts(r.stdout.splitlines()[0])
        assert 'ok' in r.stdout

    def test_stale_hashcmds_name_warns(self):
        # After the #34 hashcmds->hashall rename, a stale `hashcmds` in an
        # inherited SHELLOPTS (e.g. exported by an older psh) is UNKNOWN — bash
        # rejects it too ("hashcmds: invalid option name"). psh warns and still
        # enables the valid names, rc 0 (bash-matched, probe 2026-07-10).
        r = run_psh('echo "$SHELLOPTS"; echo alive', {
            'SHELLOPTS': 'braceexpand:hashcmds:history'})
        assert 'hashcmds: invalid option name' in r.stderr
        assert r.returncode == 0
        got = parts(r.stdout.splitlines()[0])
        assert 'braceexpand' in got and 'history' in got
        assert 'alive' in r.stdout

    def test_empty_value_noop(self):
        r = run_psh('echo "$SHELLOPTS"', {'SHELLOPTS': ''})
        assert r.returncode == 0
        assert 'braceexpand' in parts(r.stdout.strip())

    def test_bashopts_import_activates(self):
        r = run_psh('shopt -q extglob; echo rc=$?', {'BASHOPTS': 'extglob'})
        assert r.stdout == 'rc=0\n'

    def test_bashopts_unknown_silently_ignored(self):
        r = run_psh('echo alive', {'BASHOPTS': 'bogus:extglob'})
        assert r.stderr == ''
        assert r.stdout == 'alive\n'

    def test_bashopts_imported_is_exported(self):
        r = run_psh('env | grep -c "^BASHOPTS="', {'BASHOPTS': 'extglob'})
        assert r.stdout.strip() == '1'

    def test_no_env_no_export(self):
        r = run_psh('env | grep -c "^SHELLOPTS="')
        assert r.stdout.strip() == '0'


class TestShelloptsEnvImportEmptySegments:
    """Empty segments warn like bash (v0.674 fixlet F2).

    bash iterates the value with extract_colon_unit, which yields empty
    units for adjacent/leading/trailing colons but NOT like a naive
    split(':'): ':' warns ONCE (not twice), '::' twice, 'errexit::x:' has
    two empties, '' none at all. Probe-pinned (tmp/optreflect/probe3_tip.txt
    b1-b7); message ": invalid option name" on stderr, non-fatal.
    """

    WARN = 'invalid option name'

    def test_middle_empty_warns_once_and_still_activates(self):
        r = run_psh('case ":$SHELLOPTS:" in *:nounset:*) echo on;; esac; echo ok',
                    {'SHELLOPTS': 'errexit::nounset'})
        assert r.stderr.count(self.WARN) == 1
        # The empty middle segment is an empty option NAME; bash location-prefixes
        # this env-import diagnostic with its `line 0` startup sentinel, empty
        # name included: `<$0>: line 0: : invalid option name` (task #21 [#35]).
        assert 'psh: line 0: : invalid option name' in r.stderr
        assert r.stdout == 'on\nok\n'

    def test_trailing_colon_warns_once(self):
        r = run_psh('echo ok', {'SHELLOPTS': 'errexit:'})
        assert r.stderr.count(self.WARN) == 1
        assert r.stdout == 'ok\n'

    def test_leading_colon_warns_once(self):
        r = run_psh('echo ok', {'SHELLOPTS': ':errexit'})
        assert r.stderr.count(self.WARN) == 1

    def test_lone_colon_warns_once_not_twice(self):
        # The naive-split trap: ':' is two empty fields but ONE warning.
        r = run_psh('echo ok', {'SHELLOPTS': ':'})
        assert r.stderr.count(self.WARN) == 1

    def test_double_colon_warns_twice(self):
        r = run_psh('echo ok', {'SHELLOPTS': '::'})
        assert r.stderr.count(self.WARN) == 2

    def test_middle_empty_plus_trailing_warns_twice(self):
        r = run_psh('echo ok', {'SHELLOPTS': 'errexit::nounset:'})
        assert r.stderr.count(self.WARN) == 2

    def test_empty_value_no_warning(self):
        """GREEN CONTROL: an EMPTY value has no units at all."""
        r = run_psh('echo ok', {'SHELLOPTS': ''})
        assert r.stderr == ''

    def test_bashopts_empty_segments_silent(self):
        """GREEN CONTROL: BASHOPTS' unknown-silent rule covers empties."""
        r = run_psh('echo ok', {'BASHOPTS': 'extglob::'})
        assert r.stderr == ''
        assert r.stdout == 'ok\n'
