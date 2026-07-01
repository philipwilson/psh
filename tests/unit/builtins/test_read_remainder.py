"""Regression tests for `read` remainder assignment (reappraisal #15 B4).

With more fields than variables, the LAST variable gets the raw remainder
of the line: interior delimiters and spacing preserved verbatim, trailing
unprotected IFS whitespace stripped. Exception, exactly as in bash's read
builtin: when extracting one more word plus its delimiter would consume
the remainder entirely, the last variable gets just that word (so `x:y:`
gives `y` but `x:y::` gives `y::`). psh used to re-join the remaining
fields with IFS[0], collapsing runs of whitespace and dropping trailing
delimiters. Every expected value here was pinned against bash 5.2
(tmp/read_remainder_truth_table.py). Subprocess is used so real OS pipes
drive the fd-level read paths.
"""
import subprocess
import sys


def _psh(script, stdin):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        input=stdin, capture_output=True, text=True)


class TestDefaultIFSRemainder:
    def test_interior_whitespace_runs_preserved(self):
        r = _psh('read x y; echo "[$x][$y]"', '  a  b  c \n')
        assert r.stdout == "[a][b  c]\n"

    def test_tab_preserved_in_remainder(self):
        r = _psh('read x y; echo "[$y]"', 'a b\tc \n')
        assert r.stdout == "[b\tc]\n"

    def test_exact_field_count_no_remainder(self):
        r = _psh('read x y z; echo "[$x][$y][$z]"', '  a  b  c \n')
        assert r.stdout == "[a][b][c]\n"

    def test_trailing_whitespace_only_remainder(self):
        r = _psh('read x y; echo "[$y]"', 'a b   \n')
        assert r.stdout == "[b]\n"

    def test_fewer_fields_than_vars(self):
        r = _psh('read x y; echo "[$x][$y]"', 'a\n')
        assert r.stdout == "[a][]\n"

    def test_single_var_trims_whitespace_only(self):
        r = _psh('read x; echo "[$x]"', '  a b \n')
        assert r.stdout == "[a b]\n"

    def test_eof_partial_line_keeps_remainder_exits_1(self):
        r = _psh('read x y; echo "rc=$? [$x][$y]"', 'a  b  c')
        assert r.stdout == "rc=1 [a][b  c]\n"


class TestNonWhitespaceIFSRemainder:
    """IFS=: — non-whitespace delimiters are data in the remainder."""

    def test_trailing_double_delim_kept(self):
        r = _psh('IFS=: read a b; echo "[$a][$b]"', 'x:y::\n')
        assert r.stdout == "[x][y::]\n"

    def test_single_trailing_delim_dropped(self):
        # One more word + delimiter consumes the rest -> just the word.
        r = _psh('IFS=: read a b; echo "[$a][$b]"', 'x:y:\n')
        assert r.stdout == "[x][y]\n"

    def test_interior_delim_kept(self):
        r = _psh('IFS=: read a b; echo "[$a][$b]"', 'x:y:z\n')
        assert r.stdout == "[x][y:z]\n"

    def test_leading_empty_field(self):
        r = _psh('IFS=: read a b; echo "[$a][$b]"', ':a:b:\n')
        assert r.stdout == "[][a:b:]\n"

    def test_remainder_starts_with_delim(self):
        r = _psh('IFS=: read a b; echo "[$a][$b]"', 'x::y\n')
        assert r.stdout == "[x][:y]\n"

    def test_space_is_data_not_delimiter(self):
        r = _psh('IFS=: read a b; echo "[$a][$b]"', 'x: y\n')
        assert r.stdout == "[x][ y]\n"

    def test_remainder_is_lone_delim_gives_empty(self):
        r = _psh('IFS=: read a b c; echo "[$a][$b][$c]"', 'x:y::\n')
        assert r.stdout == "[x][y][]\n"

    def test_extra_vars_cleared(self):
        r = _psh('IFS=: read x y z; echo "[$x][$y][$z]"', 'a:b\n')
        assert r.stdout == "[a][b][]\n"

    def test_only_delimiters(self):
        r = _psh('IFS=: read a b; echo "[$a][$b]"', '::\n')
        assert r.stdout == "[][]\n"


class TestNonWhitespaceIFSSingleVar:
    """The remainder rule applies from the FIRST variable when it is last."""

    def test_interior_and_trailing_delims_kept(self):
        r = _psh('IFS=: read a; echo "[$a]"', 'x:y:\n')
        assert r.stdout == "[x:y:]\n"

    def test_single_trailing_delim_dropped(self):
        r = _psh('IFS=: read a; echo "[$a]"', 'x:\n')
        assert r.stdout == "[x]\n"

    def test_trailing_double_delim_kept(self):
        r = _psh('IFS=: read a; echo "[$a]"', 'x:y::\n')
        assert r.stdout == "[x:y::]\n"

    def test_leading_space_not_ifs_kept(self):
        r = _psh('IFS=: read a; echo "[$a]"', ' x:y\n')
        assert r.stdout == "[ x:y]\n"


class TestMixedIFSRemainder:
    """IFS=': ' — whitespace adjacent to the consumed delimiter is absorbed,
    but interior delimiters and spacing stay verbatim in the remainder."""

    def test_spaced_delims_preserved(self):
        r = _psh("IFS=': ' read x y; echo \"[$x][$y]\"", 'a : b : c\n')
        assert r.stdout == "[a][b : c]\n"

    def test_wide_spacing_preserved(self):
        r = _psh("IFS=': ' read x y; echo \"[$x][$y]\"", 'a  :  b  :  c\n')
        assert r.stdout == "[a][b  :  c]\n"

    def test_ws_delim_then_nonws_in_remainder(self):
        r = _psh("IFS=': ' read x y; echo \"[$x][$y]\"", 'a b : c\n')
        assert r.stdout == "[a][b : c]\n"

    def test_trailing_delim_plus_ws_dropped(self):
        r = _psh("IFS=': ' read x y; echo \"[$x][$y]\"", 'a:b: \n')
        assert r.stdout == "[a][b]\n"

    def test_doubled_delim_kept(self):
        r = _psh("IFS=': ' read x y; echo \"[$x][$y]\"", 'a:b::c\n')
        assert r.stdout == "[a][b::c]\n"


class TestEmptyIFSAndReply:
    def test_empty_ifs_whole_line_to_first_var(self):
        r = _psh('IFS= read x y; echo "[$x][$y]"', 'a b\n')
        assert r.stdout == "[a b][]\n"

    def test_empty_ifs_single_var_verbatim(self):
        r = _psh('IFS= read x; echo "[$x]"', '  a b  \n')
        assert r.stdout == "[  a b  ]\n"

    def test_default_reply_verbatim(self):
        r = _psh('read; echo "[$REPLY]"', '  a  b \n')
        assert r.stdout == "[  a  b ]\n"


class TestBackslashInRemainder:
    def test_escaped_space_preserved_no_r(self):
        r = _psh('read x y; echo "[$y]"', 'a b\\ c d\n')
        assert r.stdout == "[b c d]\n"

    def test_raw_mode_backslash_verbatim(self):
        r = _psh('read -r x y; echo "[$y]"', 'a b\\ c d\n')
        assert r.stdout == "[b\\ c d]\n"

    def test_trailing_escaped_space_survives_trim(self):
        r = _psh('read x y; echo "[$y]"', 'a b\\ \n')
        assert r.stdout == "[b ]\n"

    def test_escaped_delim_is_data(self):
        r = _psh('IFS=: read x y; echo "[$x][$y]"', 'a\\:b:c:d\n')
        assert r.stdout == "[a:b][c:d]\n"


class TestArrayUnaffected:
    """read -a still gets real fields, never a joined remainder."""

    def test_default_ifs_fields(self):
        r = _psh('read -a arr; printf "[%s]" "${arr[@]}"; echo',
                 '  a  b  c \n')
        assert r.stdout == "[a][b][c]\n"

    def test_nonws_ifs_keeps_empty_fields(self):
        r = _psh('IFS=: read -a arr; printf "[%s]" "${arr[@]}"; echo',
                 'x:y::z\n')
        assert r.stdout == "[x][y][][z]\n"
