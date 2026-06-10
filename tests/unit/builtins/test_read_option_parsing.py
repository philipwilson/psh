"""read builtin option-parsing regressions (ground-up reappraisal, v0.276.0).

The old combined-option branch ended with ``break``, abandoning the whole
option loop: ``read -rs -p x v`` treated ``-p x v`` as variable names, and
``read -rs y x`` treated ``-rs`` itself as a variable name. Attached
option arguments (``-rn3``, ``-rp prompt``) were rejected, and ``--`` was
an invalid option. All behaviors below are pinned against bash 5.2.
"""

from io import StringIO


def _feed(monkeypatch, text):
    monkeypatch.setattr('sys.stdin', StringIO(text))


class TestClusteredOptions:
    def test_cluster_then_separate_arg_option(self, shell, capsys, monkeypatch):
        """read -rs -p ... must keep parsing options after the cluster."""
        _feed(monkeypatch, "val\n")
        shell.run_command('read -rs -p "" x')
        shell.run_command('echo "got:$x"')
        assert "got:val" in capsys.readouterr().out

    def test_cluster_then_variable_names(self, shell, capsys, monkeypatch):
        """Variable names after a cluster must not be swallowed."""
        _feed(monkeypatch, "val\n")
        shell.run_command('read -rs y x')
        shell.run_command('echo "y:$y x:$x"')
        assert "y:val x:" in capsys.readouterr().out

    def test_cluster_with_trailing_arg_option(self, shell, capsys, monkeypatch):
        """-rp: p consumes the next word as its argument (bash getopt style)."""
        _feed(monkeypatch, "val\n")
        shell.run_command('read -rp "" x')
        shell.run_command('echo "got:$x"')
        assert "got:val" in capsys.readouterr().out

    def test_cluster_with_attached_value(self, shell, capsys, monkeypatch):
        """-rn3: the rest of the word is the option's value."""
        _feed(monkeypatch, "abcde")
        shell.run_command('read -rn3 x')
        shell.run_command('echo "got:$x"')
        assert "got:abc" in capsys.readouterr().out

    def test_cluster_array_option(self, shell, capsys, monkeypatch):
        _feed(monkeypatch, "a:b\n")
        shell.run_command('IFS=: read -ra arr')
        shell.run_command('echo "${arr[1]}"')
        assert "b" in capsys.readouterr().out


class TestDoubleDashAndErrors:
    def test_double_dash_ends_options(self, shell, capsys, monkeypatch):
        _feed(monkeypatch, "v\n")
        shell.run_command('read -- x')
        shell.run_command('echo "x:$x"')
        assert "x:v" in capsys.readouterr().out

    def test_flag_then_double_dash(self, shell, capsys, monkeypatch):
        _feed(monkeypatch, "v\n")
        shell.run_command('read -r -- x')
        shell.run_command('echo "x:$x"')
        assert "x:v" in capsys.readouterr().out

    def test_invalid_option_exits_2(self, shell, monkeypatch):
        _feed(monkeypatch, "v\n")
        assert shell.run_command('read -z x') == 2

    def test_missing_argument_exits_2(self, shell, monkeypatch):
        _feed(monkeypatch, "")
        assert shell.run_command('read -p') == 2

    def test_invalid_timeout_exits_1(self, shell, monkeypatch):
        """bash exits 1 for bad option values (2 for bad options)."""
        _feed(monkeypatch, "v\n")
        assert shell.run_command('read -t -1 x') == 1

    def test_invalid_count_exits_1(self, shell, monkeypatch):
        _feed(monkeypatch, "abc")
        assert shell.run_command('read -n -1 x') == 1
        assert shell.run_command('read -n xx x') == 1


class TestZeroCount:
    def test_n_zero_reads_nothing_and_succeeds(self, shell, capsys, monkeypatch):
        """bash: read -n 0 reads nothing, sets empty, exits 0."""
        _feed(monkeypatch, "abc")
        rc = shell.run_command('read -n 0 x')
        shell.run_command('echo "rc:$? x:$x"')
        assert rc == 0
        assert "x:" in capsys.readouterr().out
