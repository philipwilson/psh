"""Executor-side command hashing: table population, hit counts, and the
stale-path semantics (bash 5.2, probe-verified 2026-06-13).

ExternalExecutionStrategy consults shell.state.command_hash PARENT-side
before forking: a remembered path is exec'd directly; a miss does one
PATH walk, remembers the result (hits=1) and execs it. By default a
stale remembered path is exec'd blindly and fails 127 ("No such file or
directory" naming the path) — bash does NOT re-search PATH unless
``shopt -s checkhash`` is set, in which case the stale entry is dropped
and PATH searched afresh.
"""

import os
import stat


def _make_cmd(directory: str, name: str, output: str) -> str:
    path = os.path.join(directory, name)
    with open(path, 'w') as f:
        f.write(f'#!/bin/sh\necho {output}\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IRUSR)
    return path


class TestExecutionPopulatesTable:
    def test_running_external_command_hashes_it(
            self, isolated_shell_with_temp_dir):
        """bash: the first run remembers the path with ONE hit."""
        shell = isolated_shell_with_temp_dir
        shell.run_command('ls > /dev/null')
        table = shell.state.command_hash
        assert 'ls' in table
        entries = {name: hits for name, _path, hits in table.entries()}
        assert entries['ls'] == 1

    def test_hits_increment_per_use(self, isolated_shell_with_temp_dir):
        """bash: `ls; ls; ls; hash` shows 3 hits."""
        shell = isolated_shell_with_temp_dir
        for _ in range(3):
            shell.run_command('ls > /dev/null')
        entries = {name: hits for name, _path, hits
                   in shell.state.command_hash.entries()}
        assert entries['ls'] == 3

    def test_hashed_path_is_used_over_earlier_path_dirs(
            self, isolated_shell_with_temp_dir):
        """Once remembered, the table wins: a same-named command added
        EARLIER in PATH is not seen until the table is cleared (bash)."""
        shell = isolated_shell_with_temp_dir
        cwd = shell.state.variables['PWD']
        d1, d2 = os.path.join(cwd, 'd1'), os.path.join(cwd, 'd2')
        os.mkdir(d1)
        os.mkdir(d2)
        _make_cmd(d2, 'hcmd', 'SECOND')
        shell.run_command(f'export PATH="{d1}:{d2}:$PATH"')

        out = os.path.join(cwd, 'out.txt')
        shell.run_command(f'hcmd > {out}')
        with open(out) as f:
            assert f.read().strip() == 'SECOND'

        # A new hcmd earlier on PATH is shadowed by the hashed one...
        _make_cmd(d1, 'hcmd', 'FIRST')
        shell.run_command(f'hcmd > {out}')
        with open(out) as f:
            assert f.read().strip() == 'SECOND'

        # ...until hash -r forgets it.
        shell.run_command('hash -r')
        shell.run_command(f'hcmd > {out}')
        with open(out) as f:
            assert f.read().strip() == 'FIRST'


class TestStalePathSemantics:
    def test_default_stale_path_fails_127(self, isolated_shell_with_temp_dir):
        """bash default (checkhash off): the stale path is exec'd blindly
        and fails 127, even though a fallback exists later in PATH."""
        shell = isolated_shell_with_temp_dir
        cwd = shell.state.variables['PWD']
        d1, d2 = os.path.join(cwd, 'd1'), os.path.join(cwd, 'd2')
        os.mkdir(d1)
        os.mkdir(d2)
        first = _make_cmd(d1, 'scmd', 'ONE')
        _make_cmd(d2, 'scmd', 'TWO')
        shell.run_command(f'export PATH="{d1}:{d2}:$PATH"')

        assert shell.run_command('scmd > /dev/null') == 0
        os.unlink(first)
        rc = shell.run_command('scmd > /dev/null')
        assert rc == 127
        # The stale entry stays (and its hit still counted — bash)
        entries = {name: (path, hits) for name, path, hits
                   in shell.state.command_hash.entries()}
        assert entries['scmd'] == (first, 2)

    def test_checkhash_reverifies_and_researches(
            self, isolated_shell_with_temp_dir):
        """shopt -s checkhash: a stale entry is dropped parent-side and
        PATH searched afresh — the later copy runs (bash)."""
        shell = isolated_shell_with_temp_dir
        cwd = shell.state.variables['PWD']
        d1, d2 = os.path.join(cwd, 'd1'), os.path.join(cwd, 'd2')
        os.mkdir(d1)
        os.mkdir(d2)
        first = _make_cmd(d1, 'ccmd', 'ONE')
        second = _make_cmd(d2, 'ccmd', 'TWO')
        shell.run_command('shopt -s checkhash')
        shell.run_command(f'export PATH="{d1}:{d2}:$PATH"')

        out = os.path.join(cwd, 'out.txt')
        assert shell.run_command(f'ccmd > {out}') == 0
        os.unlink(first)
        assert shell.run_command(f'ccmd > {out}') == 0
        with open(out) as f:
            assert f.read().strip() == 'TWO'
        entries = {name: path for name, path, _hits
                   in shell.state.command_hash.entries()}
        assert entries['ccmd'] == second
