"""Extglob in non-final path components (reappraisal #16, H6 cluster).

``_expand_extglob`` used to run the extglob matcher only on os.path.basename,
so an extglob operator in a leading path component was left literal:
``@(dir1|dir2)/file`` did not expand. bash 5.2 expands each path component as a
pattern, so the walker now does too (extglob, plain glob, and literal
components all handled per level).
"""

import os


def _make_tree(shell):
    for d in ("ed1", "ed2", "xx"):
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "target"), "w").close()


class TestExtglobNonFinalPath:
    def test_alternation_dir_component(
            self, isolated_shell_with_temp_dir, capsys):
        shell = isolated_shell_with_temp_dir
        _make_tree(shell)
        shell.run_command('shopt -s extglob')
        capsys.readouterr()
        shell.run_command('echo @(ed1|ed2)/target')
        out = capsys.readouterr().out.strip().split()
        assert sorted(out) == ["ed1/target", "ed2/target"]

    def test_negation_dir_component(
            self, isolated_shell_with_temp_dir, capsys):
        shell = isolated_shell_with_temp_dir
        _make_tree(shell)
        shell.run_command('shopt -s extglob')
        capsys.readouterr()
        shell.run_command('echo !(xx)/target')
        out = capsys.readouterr().out.strip().split()
        assert sorted(out) == ["ed1/target", "ed2/target"]

    def test_plain_glob_dir_extglob_basename(
            self, isolated_shell_with_temp_dir, capsys):
        shell = isolated_shell_with_temp_dir
        _make_tree(shell)
        shell.run_command('shopt -s extglob')
        capsys.readouterr()
        shell.run_command('echo */@(target)')
        out = capsys.readouterr().out.strip().split()
        assert sorted(out) == ["ed1/target", "ed2/target", "xx/target"]

    def test_extglob_dir_plain_glob_basename(
            self, isolated_shell_with_temp_dir, capsys):
        shell = isolated_shell_with_temp_dir
        _make_tree(shell)
        shell.run_command('shopt -s extglob')
        capsys.readouterr()
        shell.run_command('echo @(ed1|ed2)/tar*')
        out = capsys.readouterr().out.strip().split()
        assert sorted(out) == ["ed1/target", "ed2/target"]

    def test_final_extglob_still_works(
            self, isolated_shell_with_temp_dir, capsys):
        shell = isolated_shell_with_temp_dir
        _make_tree(shell)
        shell.run_command('shopt -s extglob')
        capsys.readouterr()
        shell.run_command('echo ed1/@(target)')
        assert capsys.readouterr().out.strip() == "ed1/target"

    def test_no_match_stays_literal(
            self, isolated_shell_with_temp_dir, capsys):
        shell = isolated_shell_with_temp_dir
        _make_tree(shell)
        shell.run_command('shopt -s extglob')
        capsys.readouterr()
        shell.run_command('echo @(nope|zzz)/target')
        assert capsys.readouterr().out.strip() == "@(nope|zzz)/target"
