"""Globstar ``**`` symlink semantics (reappraisal #17 P-MED-1).

bash 4.3+ does NOT descend through symlinked directories during the ``**``
recursive scan: the symlink is listed as a leaf, and symlink loops therefore
cannot hang. Python's ``glob.glob(recursive=True)`` follows symlinks (and
looped forever-ish on ``ln -s ..``), so psh now uses its own walker
(``GlobExpander._expand_globstar``) whenever a bare ``**`` component is
present under ``shopt -s globstar``.

Every expectation here was pinned three-way against bash 5.2
(tmp/probes-r17t2-grabbag/probe_b_globstar.sh — 24 base + 21 corner cases),
including bash's verbatim-prefix quirks: a purely literal prefix keeps its
written form in the zero-directory match (``sub/**`` -> ``sub/``) while an
expanded prefix is a plain joined path (``**/sub/**`` -> ``sub``).
"""

import pytest


@pytest.fixture
def globstar_tree(tmp_path, monkeypatch):
    """a.txt b.txt  sub/{x.txt, deep/z.txt}  symdir->sub  looplink->.
    .hidden/h.txt  filelink.txt->a.txt"""
    (tmp_path / 'a.txt').touch()
    (tmp_path / 'b.txt').touch()
    sub = tmp_path / 'sub'
    (sub / 'deep').mkdir(parents=True)
    (sub / 'x.txt').touch()
    (sub / 'deep' / 'z.txt').touch()
    hidden = tmp_path / '.hidden'
    hidden.mkdir()
    (hidden / 'h.txt').touch()
    (tmp_path / 'symdir').symlink_to('sub')
    (tmp_path / 'looplink').symlink_to('.')
    (tmp_path / 'filelink.txt').symlink_to('a.txt')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _glob(shell, capsys, cmd):
    assert shell.run_command('shopt -s globstar; ' + cmd) == 0
    return capsys.readouterr().out.split()


class TestGlobstarSymlinks:
    def test_bare_globstar_lists_symlinks_as_leaves(self, shell, capsys, globstar_tree):
        # symdir/looplink appear but nothing beneath them (bash 4.3+);
        # looplink -> . would loop forever if followed.
        assert _glob(shell, capsys, 'echo **') == [
            'a.txt', 'b.txt', 'filelink.txt', 'looplink',
            'sub', 'sub/deep', 'sub/deep/z.txt', 'sub/x.txt', 'symdir']

    def test_trailing_slash_matches_dirs_including_symlinks(self, shell, capsys, globstar_tree):
        # `**/` keeps symlinks-to-dirs (the trailing / tests the target)
        # but still does not recurse through them.
        assert _glob(shell, capsys, 'echo **/') == [
            'looplink/', 'sub/', 'sub/deep/', 'symdir/']

    def test_globstar_prefix_skips_symlinked_dirs(self, shell, capsys, globstar_tree):
        # `**` followed by more components continues only into REAL dirs:
        # no symdir/x.txt, no looplink/... (bash).
        assert _glob(shell, capsys, 'echo **/*.txt') == [
            'a.txt', 'b.txt', 'filelink.txt', 'sub/deep/z.txt', 'sub/x.txt']

    def test_explicit_symlink_component_is_followed(self, shell, capsys, globstar_tree):
        # Only the ** scan refuses symlinks; a named symlink component works.
        assert _glob(shell, capsys, 'echo symdir/**') == [
            'symdir/', 'symdir/deep', 'symdir/deep/z.txt', 'symdir/x.txt']

    def test_wildcard_matched_symlink_base_is_followed(self, shell, capsys, globstar_tree):
        # `s*` matches symdir too; as a ** BASE it is opened (bash), and the
        # expanded prefix keeps joined-path form (`sub`, not `sub/`).
        assert _glob(shell, capsys, 'echo s*/**') == [
            'sub', 'sub/deep', 'sub/deep/z.txt', 'sub/x.txt',
            'symdir', 'symdir/deep', 'symdir/deep/z.txt', 'symdir/x.txt']

    def test_loop_symlink_is_safe_and_listed(self, shell, capsys, globstar_tree):
        # looplink -> . : must terminate (bash does) and list the link once.
        assert _glob(shell, capsys, 'echo **/looplink') == ['looplink']

    def test_literal_mid_component_after_globstar(self, shell, capsys, globstar_tree):
        assert _glob(shell, capsys, 'echo **/deep/*') == ['sub/deep/z.txt']
        assert _glob(shell, capsys, 'echo **/z.txt') == ['sub/deep/z.txt']

    def test_globstar_after_symdir_via_literal(self, shell, capsys, globstar_tree):
        # Expanded prefix -> `symdir` (no slash); descendants followed.
        assert _glob(shell, capsys, 'echo **/symdir/**') == [
            'symdir', 'symdir/deep', 'symdir/deep/z.txt', 'symdir/x.txt']


class TestGlobstarZeroMatchText:
    """bash-verbatim zero-directories match text."""

    def test_literal_prefix_keeps_written_form(self, shell, capsys, globstar_tree):
        assert _glob(shell, capsys, 'echo sub/**') == [
            'sub/', 'sub/deep', 'sub/deep/z.txt', 'sub/x.txt']

    def test_dot_slash_prefix(self, shell, capsys, globstar_tree):
        assert _glob(shell, capsys, 'echo ./**') == [
            './', './a.txt', './b.txt', './filelink.txt', './looplink',
            './sub', './sub/deep', './sub/deep/z.txt', './sub/x.txt',
            './symdir']

    def test_double_slash_kept_verbatim(self, shell, capsys, globstar_tree):
        assert _glob(shell, capsys, 'echo sub//**') == [
            'sub//', 'sub//deep', 'sub//deep/z.txt', 'sub//x.txt']

    def test_expanded_prefix_is_joined_path(self, shell, capsys, globstar_tree):
        # `**/sub/**` -> `sub` (no trailing slash), unlike literal `sub/**`.
        assert _glob(shell, capsys, 'echo **/sub/**') == [
            'sub', 'sub/deep', 'sub/deep/z.txt', 'sub/x.txt']

    def test_double_globstar_collapses(self, shell, capsys, globstar_tree):
        assert _glob(shell, capsys, 'echo sub/**/**') == [
            'sub', 'sub/deep', 'sub/deep/z.txt', 'sub/x.txt']
        assert _glob(shell, capsys, 'echo **/**/*.txt') == [
            'a.txt', 'b.txt', 'filelink.txt', 'sub/deep/z.txt', 'sub/x.txt']

    def test_trailing_slash_restricts_to_dirs(self, shell, capsys, globstar_tree):
        assert _glob(shell, capsys, 'echo sub/**/') == ['sub/', 'sub/deep/']
        assert _glob(shell, capsys, 'echo **/sub/') == ['sub/']


class TestGlobstarOptionInteractions:
    def test_dotglob_descends_hidden_dirs(self, shell, capsys, globstar_tree):
        assert _glob(shell, capsys, 'shopt -s dotglob; echo **') == [
            '.hidden', '.hidden/h.txt', 'a.txt', 'b.txt', 'filelink.txt',
            'looplink', 'sub', 'sub/deep', 'sub/deep/z.txt', 'sub/x.txt',
            'symdir']

    def test_no_dotglob_skips_hidden(self, shell, capsys, globstar_tree):
        assert '.hidden' not in _glob(shell, capsys, 'echo **')

    def test_hidden_literal_prefix_is_scanned(self, shell, capsys, globstar_tree):
        assert _glob(shell, capsys, 'echo .hidden/**') == [
            '.hidden/', '.hidden/h.txt']

    def test_double_star_not_alone_in_component_is_plain(self, shell, capsys, globstar_tree):
        # `a**` is an ordinary `a*` (bash: ** is special only as a whole
        # component); no match -> pattern stays literal.
        assert _glob(shell, capsys, 'echo a**') == ['a.txt']
        assert _glob(shell, capsys, 'echo x**') == ['x**']

    def test_no_match_stays_literal(self, shell, capsys, globstar_tree):
        assert _glob(shell, capsys, 'echo nomatch*/**') == ['nomatch*/**']
        assert _glob(shell, capsys, 'echo a.txt/**') == ['a.txt/**']

    def test_globstar_off_single_level(self, shell, capsys, globstar_tree):
        # WITHOUT globstar, ** behaves like * (no recursion).
        assert shell.run_command('echo **') == 0
        assert capsys.readouterr().out.split() == [
            'a.txt', 'b.txt', 'filelink.txt', 'looplink', 'sub', 'symdir']

    def test_extglob_with_globstar_recurses(self, shell, capsys, globstar_tree):
        # Pre-existing adjacent gap: extglob routing treated ** as a single
        # level; a ** pattern with extglob components now uses the walker.
        # (extglob must be enabled before the pattern is PARSED, hence the
        # separate command.)
        assert shell.run_command('shopt -s globstar extglob') == 0
        assert shell.run_command('echo **/@(x|z).txt') == 0
        assert capsys.readouterr().out.split() == [
            'sub/deep/z.txt', 'sub/x.txt']

    def test_extglob_component_before_globstar(self, shell, capsys, globstar_tree):
        assert shell.run_command('shopt -s globstar extglob') == 0
        assert shell.run_command('echo @(sub|nope)/**') == 0
        assert capsys.readouterr().out.split() == [
            'sub', 'sub/deep', 'sub/deep/z.txt', 'sub/x.txt']
