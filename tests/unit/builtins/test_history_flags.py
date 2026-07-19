"""Unit tests for the ``history`` builtin's file-sync flags (R18 T2-G).

Previously only ``history [n]`` and ``history -c`` worked; ``-w/-r/-a/-n/-d/-s``
were misreported as "numeric argument required". These pin the new behavior
against what bash does (verified with bash 5.2 while writing them).

Every file operation points HISTFILE at a per-test temp file and passes
``add_to_history=False`` so neither the real ~/.psh_history is touched nor the
issued command pollutes the list under test.
"""



def _run(shell, cmd):
    return shell.run_command(cmd, add_to_history=False)


def _lines(path):
    with open(path) as f:
        return [ln.rstrip('\n') for ln in f if ln.strip()]


class TestStoreAndDisplay:
    def test_store_adds_single_entry(self, captured_shell):
        _run(captured_shell, 'history -s alpha')
        _run(captured_shell, 'history -s beta')
        assert captured_shell.state.history == ['alpha', 'beta']

    def test_store_joins_multiple_args(self, captured_shell):
        _run(captured_shell, 'history -s echo hello world')
        assert captured_shell.state.history == ['echo hello world']

    def test_store_does_not_execute(self, captured_shell):
        _run(captured_shell, 'history -s echo SHOULD_NOT_RUN')
        assert 'SHOULD_NOT_RUN' not in captured_shell.get_stdout()

    def test_display_lists_whole_history(self, captured_shell):
        for i in range(15):
            _run(captured_shell, f'history -s cmd{i}')
        captured_shell.clear_output()
        _run(captured_shell, 'history')
        out = captured_shell.get_stdout()
        # bash lists the WHOLE history by default (not the last 10).
        assert len([ln for ln in out.splitlines() if ln.strip()]) == 15
        assert 'cmd0' in out and 'cmd14' in out

    def test_display_count_limits_to_last_n(self, captured_shell):
        for i in range(15):
            _run(captured_shell, f'history -s cmd{i}')
        captured_shell.clear_output()
        _run(captured_shell, 'history 3')
        out = captured_shell.get_stdout()
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert len(lines) == 3
        assert 'cmd14' in out and 'cmd0' not in out


class TestWriteRead:
    def test_write_then_read_round_trip(self, captured_shell, tmp_path):
        target = str(tmp_path / 'h.txt')
        _run(captured_shell, 'history -s one')
        _run(captured_shell, 'history -s two')
        _run(captured_shell, f'history -w {target}')
        assert _lines(target) == ['one', 'two']

    def test_read_appends_to_existing(self, captured_shell, tmp_path):
        src = tmp_path / 'src.txt'
        src.write_text('fromfile1\nfromfile2\n')
        _run(captured_shell, 'history -s mem')
        _run(captured_shell, f'history -r {src}')
        assert captured_shell.state.history == ['mem', 'fromfile1', 'fromfile2']

    def test_write_truncates(self, captured_shell, tmp_path):
        target = tmp_path / 'h.txt'
        target.write_text('stale1\nstale2\nstale3\n')
        _run(captured_shell, 'history -s only')
        _run(captured_shell, f'history -w {target}')
        assert _lines(str(target)) == ['only']


class TestAppend:
    def test_append_writes_only_new_entries(self, captured_shell, tmp_path):
        target = str(tmp_path / 'a.txt')
        _run(captured_shell, 'history -s e1')
        _run(captured_shell, f'history -a {target}')
        _run(captured_shell, 'history -s e2')
        _run(captured_shell, f'history -a {target}')
        # e1 must not be duplicated by the second append.
        assert _lines(target) == ['e1', 'e2']

    def test_write_then_append_no_duplication(self, captured_shell, tmp_path):
        target = str(tmp_path / 'wa.txt')
        _run(captured_shell, 'history -s x')
        _run(captured_shell, f'history -w {target}')
        _run(captured_shell, f'history -a {target}')
        assert _lines(target) == ['x']


class TestReadNew:
    def test_read_new_only_appends_unread_lines(self, captured_shell, tmp_path):
        histfile = str(tmp_path / '.psh_history')
        captured_shell.state.history_file = histfile
        with open(histfile, 'w') as f:
            f.write('l1\nl2\n')
        _run(captured_shell, 'history -r')            # reads l1, l2
        with open(histfile, 'a') as f:
            f.write('l3\n')                            # another shell appended
        _run(captured_shell, 'history -n')            # only l3 is new
        assert captured_shell.state.history == ['l1', 'l2', 'l3']


class TestDelete:
    def _seed(self, shell):
        for c in ('a', 'b', 'c'):
            _run(shell, f'history -s {c}')

    def test_delete_single(self, captured_shell):
        self._seed(captured_shell)
        _run(captured_shell, 'history -d 2')
        assert captured_shell.state.history == ['a', 'c']

    def test_delete_negative_offset(self, captured_shell):
        self._seed(captured_shell)
        _run(captured_shell, 'history -d -1')
        assert captured_shell.state.history == ['a', 'b']

    def test_delete_range(self, captured_shell):
        self._seed(captured_shell)
        _run(captured_shell, 'history -d 1-2')
        assert captured_shell.state.history == ['c']

    def test_delete_out_of_range(self, captured_shell):
        self._seed(captured_shell)
        rc = _run(captured_shell, 'history -d 9')
        assert rc == 1
        assert 'history position out of range' in captured_shell.get_stderr()
        assert captured_shell.state.history == ['a', 'b', 'c']

    def test_delete_non_numeric(self, captured_shell):
        self._seed(captured_shell)
        rc = _run(captured_shell, 'history -d nope')
        assert rc == 1
        assert 'history position out of range' in captured_shell.get_stderr()


class TestClearResetsMarkers:
    def test_clear_then_append_saves_post_clear_entries(self, captured_shell, tmp_path):
        # Regression guard: clearing must reset the file-sync marker so entries
        # added after the clear still get written (mirrors the -c marker fix).
        target = str(tmp_path / 'h.txt')
        _run(captured_shell, 'history -s before')
        _run(captured_shell, f'history -a {target}')
        _run(captured_shell, 'history -c')
        _run(captured_shell, 'history -s after')
        _run(captured_shell, f'history -a {target}')
        assert _lines(target) == ['before', 'after']


class TestErrors:
    def test_invalid_option(self, captured_shell):
        rc = _run(captured_shell, 'history -z')
        assert rc == 2
        err = captured_shell.get_stderr()
        assert '-z: invalid option' in err
        assert 'usage:' in err

    def test_negative_number_is_invalid_option(self, captured_shell):
        # bash treats '-5' as an invalid option, not "show last 5".
        rc = _run(captured_shell, 'history -5')
        assert rc == 2
        assert '-5: invalid option' in captured_shell.get_stderr()

    def test_non_numeric_operand(self, captured_shell):
        rc = _run(captured_shell, 'history abc')
        assert rc == 1
        assert 'abc: numeric argument required' in captured_shell.get_stderr()

    def test_delete_requires_argument(self, captured_shell):
        rc = _run(captured_shell, 'history -d')
        assert rc == 2
        assert 'option requires an argument' in captured_shell.get_stderr()

    def test_expand_print_plain_word(self, captured_shell):
        # history -p ARG expands ARG and prints the result (bash); a plain word
        # with no reference prints verbatim, rc 0 (campaign I4 wired -p).
        rc = _run(captured_shell, 'history -p something')
        assert rc == 0
        assert captured_shell.get_stdout() == 'something\n'

    def test_expand_print_expands_reference(self, captured_shell):
        # history -p forces expansion regardless of `set +H` (bash).
        _run(captured_shell, 'history -s "echo one two"')
        captured_shell.clear_output()
        rc = _run(captured_shell, 'history -p "!!:$"')
        assert rc == 0
        assert captured_shell.get_stdout() == 'two\n'

    def test_expand_print_failed_reference(self, captured_shell):
        rc = _run(captured_shell, 'history -p "!nope"')
        assert rc == 1
        assert 'event not found' in captured_shell.get_stderr()

    def test_read_missing_file(self, captured_shell, tmp_path):
        rc = _run(captured_shell, f'history -r {tmp_path / "nope.txt"}')
        assert rc == 1
        assert 'cannot access history file' in captured_shell.get_stderr()
